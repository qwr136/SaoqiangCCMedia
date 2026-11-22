#!/usr/bin/env python3
"""Locked toolchain preparation, verification and build receipts. Python stdlib only.
Never installs a tweak, runs package scripts, changes iOS settings or starts a release.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

# Also works when imported by tests with importlib, outside scripts/ on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compatible_packaging

SHA = re.compile(r'[0-9a-f]{40}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def run(argv, cwd=None):
    return subprocess.check_output([str(x) for x in argv], cwd=cwd, text=True,
                                   stderr=subprocess.PIPE, timeout=240).strip()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def blob_hash(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def compatible_tools(lock):
    return lock['policy'].get('tool_versions', 'locked') == 'compatible'


def python_selector(lock):
    return lock['compatibility']['python']['selector'] if compatible_tools(lock) else lock['python_version']


def load_lock(project):
    path = Path(project) / 'toolchain-lock.json'
    d = json.loads(path.read_text(encoding='utf-8'))
    require(d.get('schema') == 1 and type(d['schema']) is int, 'unsupported toolchain lock schema')
    for section in ('platform', 'actions', 'theos', 'sdk', 'packaging', 'policy'):
        require(isinstance(d.get(section), dict), 'missing lock section: ' + section)
    require(d['policy']['mismatch'] == 'fail', 'version mismatches must fail')
    for repo in ('theos', 'sdk'):
        require(SHA.fullmatch(d[repo]['commit']), 'unfixed ' + repo + ' commit')
        require(d[repo]['repository'].startswith('https://github.com/'), 'unsupported source endpoint')
    require(SHA.fullmatch(d['sdk']['tree']), 'SDK tree must be fixed')
    for value in list(d['theos']['submodules'].values()) + list(d['sdk']['metadata_blobs'].values()):
        require(SHA.fullmatch(value), 'source hash must be fixed')
    require(re.fullmatch(r'\d+\.\d+\.\d+', d['python_version']), 'Python version must be exact')
    require(re.fullmatch(r'\d+\.\d+(?:\.\d+)?', d['platform']['xcode_version']), 'Xcode version must be exact')
    for action in d['actions'].values():
        require(re.fullmatch(r'[\w.-]+/[\w./-]+@[0-9a-f]{40}', action), 'unfixed action: ' + action)
    require(d['packaging'], 'packaging tools are not locked')
    require(d['policy'].get('tool_versions', 'locked') in ('locked', 'compatible'), 'unsupported tool version policy')
    if compatible_tools(d):
        compatible_packaging.validate_compatibility(d)
        selector = d['compatibility']['python']['selector']
        require(re.fullmatch(r'\d+\.\d+', selector), 'compatible Python selector must name a minor series')
        require(d['compatibility']['python']['min'].startswith(selector+'.'), 'Python selector differs from compatibility range')
        require(compatible_packaging.version_in_range(d['platform']['xcode_version'], d['compatibility']['xcode']), 'Xcode baseline outside compatibility range')
        require(compatible_packaging.version_in_range(d['python_version'], d['compatibility']['python']), 'Python baseline outside compatibility range')
    return d


def project_meta(project):
    return json.loads((Path(project)/'tweak.json').read_text())


def is_native_project(project):
    return project_meta(project).get('target_type') == 'dylib'


def project_module(project, relative, name):
    path = Path(project)/relative
    require(path.is_file(), 'missing project checker: '+relative)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def static_errors(project):
    project = Path(project)
    try:
        lock = load_lock(project)
        meta = json.loads((project/'tweak.json').read_text())
        sdk = lock['sdk']
        require(meta['sdk_version'] == sdk['target_version'], 'manifest SDK differs from lock')
        require(sdk['directory'] == 'iPhoneOS' + meta['sdk_version'] + '.sdk', 'SDK directory differs from target')
        native = meta.get('target_type') == 'dylib'
        require(meta.get('target_type', 'deb') in ('deb', 'dylib'), 'unsupported artifact type')
        if native:
            require(meta.get('scheme') == 'trollfools' and meta.get('architecture') == 'arm64', 'invalid native dylib target')
            checker = project_module(project, 'tests/source_checks.py', 'native_source_policy')
            require(not checker.check_project(project, meta), 'TrollFools source/manifest policy differs')
        else:
            build = (project/(meta['name']+'Build.mk')).read_text()
            active_build = '\n'.join(line.split('#', 1)[0] for line in build.splitlines())
            require(('iphone:clang:' + sdk['target_version'] + ':') in active_build, 'Build.mk SDK differs from lock')
            minimum = meta.get('minimum_ios')
            if meta.get('template_version'):
                require(isinstance(minimum, str) and re.fullmatch(r'\d+\.\d+(?:\.\d+)?', minimum)
                        and int(minimum.split('.')[0]) >= 15, 'minimum iOS must be 15 or newer')
                require(re.findall(r'^\s*TARGET\s*[:?+]?=\s*(\S+)\s*$', active_build, re.M) ==
                        ['iphone:clang:'+sdk['target_version']+':'+minimum], 'Build.mk minimum iOS differs from manifest')
        require((project/'scripts/toolchain.py').is_file(), 'toolchain checker missing')
        require((project/'scripts/locked_packaging.py').is_file(), 'packaging installer missing')
        require((project/'scripts/compatible_packaging.py').is_file(), 'compatible packaging checker missing')
        wrapper = '\n'.join(line for line in (project/'build.sh').read_text().splitlines()
                            if not line.lstrip().startswith('#'))
        require('scripts/toolchain.py verify' in wrapper, 'local build wrapper misses lock verification')
        verification = re.search(r'^\s*python3\s+scripts/toolchain\.py\s+verify(?:\s|$)', wrapper, re.M)
        make_calls = list(re.finditer(r'(?:^|[;&|])\s*(?:[\w./-]*/)?(?:gmake|make)\s', wrapper, re.M))
        build_calls = list(re.finditer(r'^\s*python3\s+scripts/build_dylib\.py(?:\s|$)', wrapper, re.M)) if native else make_calls
        require(verification and build_calls and all(verification.start() < call.start() for call in build_calls),
                'lock verification must run before every make command or dylib build')
        if not meta.get('github_actions'):
            return []
        text = '\n'.join(line for line in (project/'.github/workflows/build.yml').read_text().splitlines()
                         if not line.lstrip().startswith('#'))
        uses = re.findall(r'^\s*-?\s*uses:\s*(\S+)', text, re.M)
        require(uses and all(a in lock['actions'].values() for a in uses), 'workflow action differs from lock')
        required_actions = ('checkout', 'setup_python', 'upload_artifact') if native else ('checkout', 'setup_python', 'cache', 'upload_artifact')
        for key in required_actions:
            require(lock['actions'][key] in uses, 'workflow missing locked action: ' + key)
        require('latest-stable' not in text and 'ubuntu-latest' not in text, 'workflow uses a rolling latest selector')
        require(re.search(r'runs-on:\s*'+re.escape(lock['platform']['runner'])+r'\s*$', text, re.M), 'runner differs from lock')
        for needle in ('THEOS_COMMIT: '+lock['theos']['commit'],
                       'SDK_COMMIT: '+sdk['commit'],
                       "python-version: '"+python_selector(lock)+"'"):
            require(needle in text, 'workflow missing policy value: ' + needle)
        if compatible_tools(lock):
            require(not re.search(r'^\s*DEVELOPER_DIR:', text, re.M), 'compatible workflow must select DEVELOPER_DIR at runtime')
            require('toolchain.py select-xcode --github-env' in text, 'workflow missing compatible DEVELOPER_DIR selection')
            require('${{ steps.toolchain_host.outputs.cache_key }}' in text, 'cache must include observed host tools')
            require("hashFiles('toolchain-lock.json')" in text, 'cache missing lock hashFiles')
            require(text.index('toolchain.py select-xcode --github-env') < text.index("hashFiles('toolchain-lock.json')"), 'Xcode selection must precede cache restore')
        else:
            require('DEVELOPER_DIR: '+lock['platform']['developer_dir'] in text, 'workflow missing locked DEVELOPER_DIR')
        for needle in ('toolchain.py prepare', 'toolchain.py verify', 'toolchain.py receipt',
                       "hashFiles('toolchain-lock.json')", '${{ runner.arch }}', 'timeout-minutes:'):
            require(needle in text, 'workflow missing gate: ' + needle)
        return []
    except (OSError, ValueError, KeyError, TypeError) as e:
        return ['Toolchain lock: ' + str(e)]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def clean_repo(repo, expected):
    require(run(['git', 'rev-parse', 'HEAD'], repo) == expected, 'source checkout commit mismatch: '+str(repo))
    require(not run(['git', 'status', '--porcelain', '--untracked-files=no'], repo),
            'source checkout has tracked modifications: '+str(repo))


def checkout(repository, commit, destination, sparse=None):
    destination = Path(destination)
    if not (destination/'.git').exists():
        if destination.exists():
            require(not any(destination.iterdir()), 'refusing to initialize source checkout over nonempty path: '+str(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        run(['git', 'init', str(destination)])
        run(['git', 'remote', 'add', 'origin', repository], destination)
        run(['git', 'fetch', '--depth', '1', '--filter=blob:none', 'origin', commit], destination)
        if sparse:
            run(['git', 'sparse-checkout', 'init', '--cone'], destination)
            run(['git', 'sparse-checkout', 'set', sparse], destination)
        run(['git', 'checkout', '--detach', commit], destination)
    clean_repo(destination, commit)
    return destination


def verify_sources(lock, theos, sdk_source):
    theos, sdk_source = Path(theos), Path(sdk_source)
    clean_repo(theos, lock['theos']['commit'])
    submodules = run(['git', 'submodule', 'status', '--recursive'], theos).splitlines()
    require(submodules and all(re.match(r'^\s*[0-9a-f]{40}\s', line) for line in submodules), 'uninitialized or changed submodules')
    actual = {line.strip().split()[1]: line.strip().split()[0] for line in submodules}
    for path, commit in lock['theos']['submodules'].items():
        require(actual.get(path) == commit, 'Theos submodule mismatch: '+path)
        clean_repo(theos/path, commit)
    clean_repo(sdk_source, lock['sdk']['commit'])
    sdk = lock['sdk']
    source = sdk_source/sdk['directory']
    require(run(['git', 'rev-parse', 'HEAD:'+sdk['directory']], sdk_source) == sdk['tree'], 'SDK tree mismatch')
    require(not run(['git', 'status', '--porcelain', '--untracked-files=all', '--', sdk['directory']], sdk_source),
            'SDK contains modified or extra files')
    installed = theos/'sdks'/sdk['directory']
    require(installed.is_dir() and installed.resolve() == source.resolve(), 'Theos SDK does not point to verified checkout')
    evidence = {}
    for name, expected in sdk['metadata_blobs'].items():
        raw = (source/name).read_bytes()
        require(blob_hash(raw) == expected, 'SDK metadata hash mismatch: '+name)
        value = plistlib.loads(raw) if name.endswith('.plist') else json.loads(raw)
        require(value['Version'] == sdk['internal_version'], 'SDK internal version mismatch')
        evidence[name] = {'blob': expected, 'version': value['Version']}
    require((theos/'vendor/include/roothide.h').is_file(), 'pinned RootHide header missing')
    require((theos/'vendor/include/Preferences/PSListController.h').is_file(), 'pinned Preferences headers missing')
    return {'theos_commit': lock['theos']['commit'], 'submodules': actual,
            'sdk_commit': sdk['commit'], 'sdk_tree': sdk['tree'], 'sdk_metadata': evidence}


def parse_xcode(text):
    match = re.fullmatch(r'Xcode (\d+\.\d+(?:\.\d+)?)\nBuild version ([A-Za-z0-9]+)', text)
    require(match, 'unrecognized Xcode version/build output')
    return match.group(1), match.group(2)


def verify_platform(lock):
    p = lock['platform']
    require(platform.system() == p['os'], 'locked builds require '+p['os'])
    require(platform.machine() == p['architecture'], 'host architecture differs from lock')
    os_version = run(['sw_vers', '-productVersion'])
    require(os_version.split('.')[0] == p['macos_major'], 'macOS major differs from lock')
    developer = os.environ.get('DEVELOPER_DIR', '')
    if compatible_tools(lock) and not developer:
        developer = run(['xcode-select', '-p'])
    require(developer.startswith('/') and developer.endswith('/Contents/Developer') and
            not any(c in developer for c in '\r\n\0'), 'invalid DEVELOPER_DIR')
    xcode = run(['xcodebuild', '-version'])
    clang = run(['xcrun', '--sdk', 'iphoneos', 'clang', '--version'])
    python = platform.python_version()
    if compatible_tools(lock):
        version, build = parse_xcode(xcode)
        require(compatible_packaging.version_in_range(version, lock['compatibility']['xcode']), 'Xcode outside compatible range')
        require(re.search(r'Apple clang version \d+(?:\.\d+)+ \(clang-[0-9.]+\)', clang), 'unrecognized Apple clang compiler')
        require(compatible_packaging.version_in_range(python, lock['compatibility']['python']), 'Python outside compatible range')
    else:
        require(developer == p['developer_dir'], 'DEVELOPER_DIR differs from lock')
        require(xcode == 'Xcode '+p['xcode_version']+'\nBuild version '+p['xcode_build'], 'Xcode version/build differs from lock')
        require('(clang-'+p['clang_build']+')' in clang, 'Apple clang build differs from lock')
        require(python == lock['python_version'], 'Python differs from lock')
    return {'system': platform.system(), 'architecture': platform.machine(), 'macos': os_version,
            'os_build': run(['sw_vers','-buildVersion']), 'xcode': xcode, 'clang': clang,
            'python': python, 'developer_dir': developer,
            'tool_version_policy': lock['policy'].get('tool_versions', 'locked'),
            'runner_image': os.environ.get('ImageVersion', ''), 'runner_os': os.environ.get('RUNNER_OS', ''),
            'runner_arch': os.environ.get('RUNNER_ARCH', '')}


def select_xcode(lock, github_env=False):
    """Prefer the selected compatible Xcode; otherwise inspect installed Xcode apps.
    Does not change global xcode-select or install/upgrade any developer tools.
    """
    require(platform.system() == lock['platform']['os'], 'Xcode selection requires macOS')
    require(platform.machine() == lock['platform']['architecture'], 'Xcode host architecture mismatch')
    if compatible_tools(lock):
        current = os.environ.get('DEVELOPER_DIR')
        if not current:
            current = run(['xcode-select', '-p'])
        candidates = [Path(current)] + sorted(
            (path/'Contents/Developer' for path in Path('/Applications').glob('Xcode*.app')),
            reverse=True)
    else:
        candidates = [Path(lock['platform']['developer_dir'])]
    original = os.environ.get('DEVELOPER_DIR')
    selected, evidence, last_error = None, None, ''
    try:
        seen = set()
        for candidate in candidates:
            directory = str(candidate.resolve())
            if directory in seen or not candidate.is_dir():
                continue
            seen.add(directory)
            try:
                require(not any(c in directory for c in '\r\n\0'), 'invalid Xcode path')
                os.environ['DEVELOPER_DIR'] = directory
                evidence = verify_platform(lock)
                selected = directory
                break
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                last_error = str(error)
        require(selected is not None, 'no installed Xcode satisfies tool policy: '+last_error)
        if github_env:
            require(os.environ.get('GITHUB_ENV') and os.environ.get('GITHUB_OUTPUT'), 'GitHub output files missing')
            fingerprint = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
            with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as stream:
                stream.write('DEVELOPER_DIR='+selected+'\n')
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
                stream.write('cache_key='+fingerprint+'\n')
            write_json('reports/xcode-selection.json', evidence)
        return selected
    finally:
        if original is None:
            os.environ.pop('DEVELOPER_DIR', None)
        else:
            os.environ['DEVELOPER_DIR'] = original


def fetch_verified(url, expected, destination):
    destination = Path(destination)
    if destination.exists():
        require(digest(destination) == expected, 'cached download checksum mismatch')
        return destination
    require(url.startswith('https://'), 'download must use HTTPS')
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'xiaofei-toolchain-lock/1'})
    temp = destination.with_suffix(destination.suffix+'.partial')
    try:
        with urllib.request.urlopen(request, timeout=90) as response, temp.open('wb') as output:
            shutil.copyfileobj(response, output)
        require(digest(temp) == expected, 'download checksum mismatch')
        temp.replace(destination)
    finally:
        if temp.exists(): temp.unlink()
    return destination


def packaging_bin_paths(lock):
    if compatible_tools(lock):
        return compatible_packaging.packaging_bin_paths(lock)
    p = lock['packaging']['packages']
    base = Path('/opt/homebrew/Cellar')
    paths = [base/'make'/p['make']['version']/'libexec/gnubin']
    paths += [base/name/p[name]['version']/'bin' for name in lock['packaging']['install_order']]
    return paths


def install_packaging(lock, cache):
    if compatible_tools(lock):
        return compatible_packaging.install_packaging(lock, cache)
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted',
            'automatic packaging installation is restricted to disposable GitHub-hosted runners')
    core = lock['packaging']['homebrew_core']
    tap = Path('/opt/homebrew/Library/Taps/homebrew/homebrew-core')
    # Only a disposable hosted runner may move its preinstalled core tap.
    # User work and normal local installations are never reset by this script.
    if (tap/'.git').exists() and run(['git','rev-parse','HEAD'],tap) != core['commit']:
        require(not run(['git','status','--porcelain'],tap), 'runner core tap is dirty')
        run(['git','fetch','--depth','1','origin',core['commit']],tap)
        run(['git','checkout','--detach',core['commit']],tap)
    checkout(core['repository'], core['commit'], tap)
    script = Path(__file__).with_name('locked_packaging.py')
    subprocess.run([sys.executable,str(script),'--lock','toolchain-lock.json','--cache',str(cache),
                    '--receipt','reports/packaging-install.json','--install','--replace-existing'],check=True)


def verify_packaging(lock):
    if compatible_tools(lock):
        return compatible_packaging.verify_packaging(lock)
    script = Path(__file__).with_name('locked_packaging.py')
    result = Path('reports/packaging-current.json')
    subprocess.run([sys.executable,str(script),'--lock','toolchain-lock.json','--verify-only',
                    '--receipt',str(result)],check=True)
    evidence = json.loads(result.read_text())
    base = Path('/opt/homebrew/Cellar')
    pkgs = lock['packaging']['packages']
    commands = {'make':base/'make'/pkgs['make']['version']/'bin/gmake',
                'dpkg-deb':base/'dpkg'/pkgs['dpkg']['version']/'bin/dpkg-deb',
                'xz':base/'xz'/pkgs['xz']['version']/'bin/xz',
                'ldid':base/'ldid'/pkgs['ldid']['version']/'bin/ldid',
                'perl':base/'perl'/pkgs['perl']['version']/'bin/perl'}
    evidence['commands'] = {}
    for name,path in commands.items():
        require(shutil.which(name) and Path(shutil.which(name)).resolve() == path.resolve(),
                'PATH command differs from locked tool: '+name)
        evidence['commands'][name]={'path':str(path),'sha256':digest(path)}
    return evidence


def locations():
    root = Path(os.environ.get('TOOLCHAIN_ROOT', '/tmp/xiaofei-toolchain'))
    return root, Path(os.environ.get('THEOS', str(root/'theos'))), root/'sdks'


def activate_paths(paths):
    """Keep verified tools first both now and after Actions prepends each line."""
    paths = [str(path) for path in paths]
    if os.environ.get('GITHUB_PATH'):
        with open(os.environ['GITHUB_PATH'], 'a') as stream:
            for path in reversed(paths):
                stream.write(path+'\n')
    os.environ['PATH'] = os.pathsep.join(paths + [os.environ.get('PATH', '')])


def prepare(project, lock):
    verify_platform(lock)
    root, theos, sdk_source = locations()
    checkout(lock['theos']['repository'], lock['theos']['commit'], theos)
    run(['git', 'submodule', 'update', '--init', '--recursive'], theos)
    checkout(lock['sdk']['repository'], lock['sdk']['commit'], sdk_source, lock['sdk']['directory'])
    link = theos/'sdks'/lock['sdk']['directory']
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists() and not link.is_symlink():
        link.symlink_to(sdk_source/lock['sdk']['directory'], target_is_directory=True)
    verify_sources(lock, theos, sdk_source)
    # Pure App injection uses Apple's compiler/codesign, not jailbreak packaging.
    if is_native_project(project):
        print('Prepared fixed source/SDK for native dylib; no Homebrew packaging installed')
        return
    # Source/SDK remain immutable; packaging follows the selected bounded policy.
    install_packaging(lock, root/'downloads')
    package_bins = packaging_bin_paths(lock)
    activate_paths(package_bins + [theos/'bin'])
    print('Prepared exact Theos/SDK and packaging tools')


def verify(project, lock):
    host = verify_platform(lock)
    root, theos, sdk_source = locations()
    source = verify_sources(lock, theos, sdk_source)
    if is_native_project(project):
        package = {'status': 'not-required', 'reason': 'native Apple dylib uses no deb packaging or jailbreak libraries'}
    else:
        package = verify_packaging(lock)
        require(shutil.which('make') and Path(shutil.which('make')).resolve() ==
                Path(package['commands']['make']['path']).resolve(), 'PATH make is not the locked GNU make')
    return {'status':'verified', 'lock_sha256':digest(Path(project)/'toolchain-lock.json'),
            'tool_version_policy':lock['policy'].get('tool_versions', 'locked'),
            'compatibility':lock.get('compatibility', {}) if compatible_tools(lock) else {},
            'host':host, 'sources':source, 'packaging':package}


def receipt(project, lock, output):
    evidence = verify(project, lock)
    project = Path(project).resolve()
    source_sha = run(['git', 'rev-parse', 'HEAD'], project)
    meta = project_meta(project)
    if meta.get('target_type') == 'dylib':
        artifact = project/'artifacts'/(meta['name']+'.dylib')
        require(not artifact.is_symlink(), 'receipt dylib must not be a symlink')
        require(sorted((project/'artifacts').glob('*.dylib')) == [artifact], 'receipt requires exactly this project dylib')
        inspector = project_module(project, 'tests/verify_dylib.py', 'native_artifact_verifier')
        entry = inspector.inspect_dylib(artifact, meta)
        evidence.update({'source_sha': source_sha, 'source_ref': os.environ.get('GITHUB_REF', ''),
                         'repository': os.environ.get('GITHUB_REPOSITORY', ''),
                         'run_id': os.environ.get('GITHUB_RUN_ID', ''),
                         'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
                         'workflow_ref': os.environ.get('GITHUB_WORKFLOW_REF', ''),
                         'scheme': 'trollfools', 'target_type': 'dylib', 'version': meta.get('version'),
                         'artifacts': [entry], 'packages': [],
                         'validation': 'Native compile and static dylib inspection; signature trust/load/device untested'})
        write_json(output, evidence)
        print('Saved verified native build receipt:', output)
        return
    control = {}
    for line in (project/'control').read_text().splitlines():
        if ':' in line and not line[0].isspace():
            key, value = line.split(':', 1); control[key] = value.strip()
    packages = sorted((project/'packages').glob('*.deb'))
    require(packages, 'no deb exists for receipt')
    entries = []
    for deb in packages:
        fields = {}
        for key in ('Package','Version','Architecture','Depends'):
            fields[key] = run(['dpkg-deb','-f',str(deb),key])
        require(fields['Package'] == control['Package'] and fields['Version'] == control['Version'],
                'receipt package does not match this build')
        entries.append({'filename':deb.name,'size':deb.stat().st_size,'sha256':digest(deb), 'control':fields})
    # Fixed allowlist only: never serialize the environment or credentials.
    evidence.update({'source_sha':source_sha, 'source_ref':os.environ.get('GITHUB_REF',''),
                     'repository':os.environ.get('GITHUB_REPOSITORY',''),
                     'run_id':os.environ.get('GITHUB_RUN_ID',''),
                     'run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT',''),
                     'workflow_ref':os.environ.get('GITHUB_WORKFLOW_REF',''),
                     'scheme':json.loads((project/'tweak.json').read_text())['scheme'],
                     'packages':entries,'validation':'Source gates and real compile/package inspection; device untested'})
    write_json(output,evidence)
    print('Saved verified build receipt:', output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('static','select-xcode','prepare','verify','receipt'))
    parser.add_argument('--github-env', action='store_true', help='export selected Xcode and cache fingerprint to GitHub output files')
    parser.add_argument('--project',default='.')
    parser.add_argument('--output',default='reports/toolchain-verification.json')
    args = parser.parse_args()
    try:
        errors = static_errors(args.project)
        require(not errors, '\n'.join(errors))
        lock = load_lock(args.project)
        if args.command == 'static':
            print('PASS toolchain lock, workflow and build-wrapper consistency')
        elif args.command == 'select-xcode': print(select_xcode(lock, args.github_env))
        elif args.command == 'prepare': prepare(args.project,lock)
        elif args.command == 'verify':
            write_json(args.output,verify(args.project,lock))
            print('PASS actual host, source hashes, SDK and packaging tool versions')
        else: receipt(args.project,lock,args.output)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as e:
        print('ERROR: '+str(e),file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
