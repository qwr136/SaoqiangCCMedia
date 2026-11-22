#!/usr/bin/env python3
"""Observe compatible Homebrew tools; never claim their downloads are byte-pinned.

Installation is restricted to disposable GitHub-hosted runners. Verification is
read-only and requires trusted homebrew/core receipts and the audited PATH.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

PREFIX = Path('/opt/homebrew')
CELLAR = PREFIX / 'Cellar'
ROOTS = ('make', 'ldid', 'xz', 'dpkg')
COMMANDS = {'make': ('make', 'bin/gmake'), 'ldid': ('ldid', 'bin/ldid'),
            'xz': ('xz', 'bin/xz'), 'dpkg-deb': ('dpkg', 'bin/dpkg-deb')}
_SPEC = importlib.util.spec_from_file_location(
    '_compatible_locked_helpers', Path(__file__).with_name('locked_packaging.py'))
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*(?:_[0-9]+)?', value):
        raise ValueError('invalid numeric Homebrew version')
    base, _, revision = value.partition('_')
    parts = tuple(int(x) for x in base.split('.'))
    while len(parts) > 1 and parts[-1] == 0:
        parts = parts[:-1]
    return parts, int(revision or 0)


def _compare(a, b):
    left, lr = _version(a)
    right, rr = _version(b)
    size = max(len(left), len(right))
    left += (0,) * (size - len(left))
    right += (0,) * (size - len(right))
    return ((left, lr) > (right, rr)) - ((left, lr) < (right, rr))


def version_in_range(value, spec):
    try:
        if not isinstance(spec, dict) or _compare(spec['min'], spec['max_exclusive']) >= 0:
            return False
        return _compare(value, spec['min']) >= 0 and _compare(value, spec['max_exclusive']) < 0
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def validate_compatibility(lock):
    try:
        if lock['policy'].get('tool_versions', 'locked') != 'compatible':
            raise ValueError('compatible packaging requires explicit compatible policy')
        compat = lock['compatibility']
        specs = [('xcode', compat['xcode']), ('python', compat['python'])]
        packages = compat['packaging']
        if not isinstance(packages, dict) or set(packages) != set(ROOTS):
            raise ValueError('compatibility packaging must declare exactly the four root tools')
        specs += list(packages.items())
        for name, spec in specs:
            if not isinstance(spec, dict) or not version_in_range(spec.get('min'), spec):
                raise ValueError('invalid compatibility range: ' + name)
        selector = compat['python'].get('selector')
        if not isinstance(selector, str) or not re.fullmatch(r'[0-9]+\.[0-9]+', selector):
            raise ValueError('Python selector must be a major.minor series')
        if not compat['python']['min'].startswith(selector + '.'):
            raise ValueError('Python selector differs from minimum series')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('missing or invalid compatibility policy') from error


def packaging_bin_paths(lock):
    validate_compatibility(lock)
    return [PREFIX / 'opt/make/libexec/gnubin', PREFIX / 'opt/ldid/bin',
            PREFIX / 'opt/xz/bin', PREFIX / 'opt/dpkg/bin', PREFIX / 'opt/dpkg/libexec/bin']


def _environment():
    # In particular discard custom API/bottle domains and NO_INSTALL_FROM_API.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('DYLD_', 'HOMEBREW_'))}
    for key in ('HOMEBREW_NO_AUTO_UPDATE', 'HOMEBREW_NO_INSTALL_UPGRADE',
                'HOMEBREW_NO_INSTALL_CLEANUP', 'HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK',
                'HOMEBREW_NO_ANALYTICS', 'HOMEBREW_NO_ENV_HINTS'):
        env[key] = '1'
    env['LC_ALL'] = 'C'
    return env


def _run(args, env, check=True):
    proc = subprocess.run([str(a) for a in args], env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    if check and proc.returncode:
        # Do not serialize arbitrary command output/environment into errors.
        raise ValueError('tool command failed: ' + str(args[0]))
    return proc


def _sha(path):
    return _HELPERS.file_sha(path)


def _context():
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('compatible packaging requires native macOS ARM64')
    brew = shutil.which('brew')
    expected = PREFIX / 'bin/brew'
    if (not brew or not expected.is_file() or Path(brew).resolve() != expected.resolve()
            or PREFIX not in expected.resolve().parents):
        raise ValueError('trusted native Homebrew executable missing from PATH')
    env = _environment()
    if _run([brew, '--prefix'], env).stdout.strip() != str(PREFIX):
        raise ValueError('unexpected Homebrew prefix')
    if _run([brew, '--cellar'], env).stdout.strip() != str(CELLAR):
        raise ValueError('unexpected Homebrew Cellar')
    version = _run([brew, '--version'], env).stdout.strip()
    return str(expected), env, {'manager': 'Homebrew', 'version': version,
                               'path': str(expected.resolve()), 'sha256': _sha(expected),
                               'tap': 'homebrew/core', 'metadata_status': 'rolling-observed'}


def _name(value):
    if isinstance(value, str) and value.startswith('homebrew/core/'):
        value = value[len('homebrew/core/'):]
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9+_.@-]*', value):
        raise ValueError('dependency is not a trusted core formula name')
    return value


def _info(brew, env, name):
    name = _name(name)
    try:
        data = json.loads(_run([brew, 'info', '--json=v2', 'homebrew/core/' + name], env).stdout)
        formulas = data['formulae']
        if len(formulas) != 1:
            raise ValueError('ambiguous Homebrew formula')
        info = formulas[0]
        if (info.get('name') != name or info.get('tap') != 'homebrew/core'
                or info.get('full_name') not in (name, 'homebrew/core/' + name)):
            raise ValueError('formula does not originate from homebrew/core: ' + name)
        if not isinstance(info.get('installed'), list):
            raise ValueError('missing installed formula metadata: ' + name)
        return info
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('invalid Homebrew formula metadata: ' + name) from error


def _entry_version(entry):
    value = entry.get('pkg_version', entry.get('version'))
    # Dependencies may use date/tag versions (for example ca-certificates).
    # Only root tools participate in numeric compatibility comparisons.
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+_-]*', value)
            or value in ('.', '..')):
        raise ValueError('invalid installed Homebrew version')
    revision = entry.get('revision', 0)
    if type(revision) is not int or revision < 0:
        raise ValueError('invalid Homebrew revision')
    return value + ('_' + str(revision) if revision and '_' not in value else '')


def _observe(name, info, missing=False):
    opt = PREFIX / 'opt' / name
    if not opt.exists() and not opt.is_symlink():
        if missing and not info['installed']:
            return None
        raise ValueError('installed core formula has no active opt keg: ' + name)
    keg = opt.resolve(strict=True)
    if keg.parent != CELLAR / name:
        raise ValueError('opt resolves outside expected Cellar formula: ' + name)
    version = keg.name
    _entry_version({'version': version})
    entries = [e for e in info['installed'] if _entry_version(e) == version]
    if len(entries) != 1:
        raise ValueError('active keg is absent from Homebrew installed metadata: ' + name)
    tab = keg / 'INSTALL_RECEIPT.json'
    formula = keg / '.brew' / (name + '.rb')
    if not tab.is_file() or not formula.is_file():
        raise ValueError('missing installed receipt/formula: ' + name)
    for path in (tab, formula):
        if keg not in path.resolve(strict=True).parents:
            raise ValueError('installed metadata escapes keg: ' + name)
    try:
        receipt = json.loads(tab.read_text())
        source = receipt['source']
        if source.get('tap') != 'homebrew/core' or source.get('spec', 'stable') != 'stable':
            raise ValueError('installed keg is not stable homebrew/core: ' + name)
        dependencies = receipt.get('runtime_dependencies', entries[0].get('runtime_dependencies'))
        if not isinstance(dependencies, list):
            raise ValueError('missing actual runtime dependency receipt: ' + name)
        deps = sorted(set(_name(d['full_name']) for d in dependencies))
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError('invalid installed receipt: ' + name) from error
    return {'version': version, 'keg': str(keg), 'dependencies': deps,
            'formula_sha256': _sha(formula), 'install_receipt_sha256': _sha(tab),
            'source': {'tap': 'homebrew/core', 'full_name': info['full_name'],
                       'tap_git_head': source.get('tap_git_head'), 'spec': 'stable',
                       'poured_from_bottle': receipt.get('poured_from_bottle', False),
                       'formula_metadata_sha256': hashlib.sha256(
                           json.dumps(info, sort_keys=True).encode()).hexdigest()}}


def _root_range(lock, name, value):
    if not version_in_range(value, lock['compatibility']['packaging'][name]):
        raise ValueError('root tool outside compatible range: ' + name + ' ' + value)


def _closure(name, packages):
    seen = set()
    def visit(current, active):
        if current in active:
            raise ValueError('cyclic installed runtime dependency graph')
        for dep in packages[current]['dependencies']:
            if dep not in seen:
                visit(dep, active | {current})
                seen.add(dep)
    visit(name, set())
    return seen


def _discover(lock, brew, env):
    packages, pending = {}, list(ROOTS)
    while pending:
        name = pending.pop(0)
        if name in packages:
            continue
        if len(packages) >= 256:
            raise ValueError('runtime dependency closure exceeds safety limit')
        observed = _observe(name, _info(brew, env, name))
        if name in ROOTS:
            _root_range(lock, name, observed['version'])
        packages[name] = observed
        pending.extend(observed['dependencies'])
    for name in packages:
        _closure(name, packages)
    return packages


def _owned(path, kegs):
    try:
        return _HELPERS.owned(path, kegs)
    except (RuntimeError, OSError) as error:
        raise ValueError('library resolves outside observed dependency closure: ' + str(path)) from error


def _system_path(path):
    return '..' not in Path(path).parts and path.startswith(('/usr/lib/', '/System/Library/'))


def _dependencies(path, env, kegs, allowed):
    output = _run(['/usr/bin/otool', '-L', path], env).stdout
    names = [line.strip().split(' (compatibility version', 1)[0]
             for line in output.splitlines() if line.startswith(('\t', ' '))]
    resolved = []
    for dep in names:
        if _system_path(dep):
            continue
        if '@@HOMEBREW_' in dep:
            raise ValueError('unrelocated Mach-O dependency')
        if dep.startswith('@loader_path/'):
            target = path.parent / dep[len('@loader_path/'):]
        elif dep.startswith('@rpath/'):
            text = _run(['/usr/bin/otool', '-l', path], env).stdout
            paths = re.findall(r'cmd LC_RPATH\n.*?\n\s*path (.*?) \(offset', text, re.S)
            candidates = [Path(p.replace('@loader_path', str(path.parent))) / dep[len('@rpath/'):]
                          for p in paths if '@executable_path' not in p]
            found = [p for p in candidates if p.exists()]
            if not found:
                raise ValueError('unresolved @rpath dependency: ' + dep)
            target = found[0]
        elif dep.startswith('/'):
            target = Path(dep)
        else:
            raise ValueError('unsupported Mach-O dependency: ' + dep)
        owner, real = _owned(target, kegs)
        if owner not in allowed:
            raise ValueError('Mach-O dependency outside declared runtime closure: ' + owner)
        resolved.append({'load_command': dep, 'package': owner, 'resolved': str(real)})
    return resolved


def _commands(packages):
    result = {}
    for command, (name, suffix) in COMMANDS.items():
        keg = Path(packages[name]['keg'])
        expected = keg / suffix
        if command == 'dpkg-deb' and not expected.is_file():
            expected = keg / 'libexec/bin/dpkg-deb'
        path = shutil.which(command)
        if not path or not expected.is_file():
            raise ValueError('required compatible command missing from PATH: ' + command)
        real = Path(path).resolve(strict=True)
        if real != expected.resolve(strict=True) or keg not in real.parents:
            raise ValueError('PATH command differs from observed compatible keg: ' + command)
        result[command] = {'path': str(real), 'path_entry': str(path),
                           'sha256': _sha(real), 'version': packages[name]['version'], 'package': name}
    return result


def _audit(packages, commands, env):
    kegs = {name: Path(pkg['keg']) for name, pkg in packages.items()}
    evidence = {'mach_o': {}, 'runtime_smoke': {}}
    for name, keg in kegs.items():
        allowed = _closure(name, packages) | {name}
        for path in _HELPERS.macho_files(keg):
            dependencies = _dependencies(path, env, kegs, allowed)
            sign = _run(['/usr/bin/codesign', '--verify', '--strict', path], env, check=False)
            if sign.returncode:
                raise ValueError('Mach-O signature verification failed: ' + str(path))
            evidence['mach_o'][str(path)] = {'sha256': _sha(path), 'dependencies': dependencies,
                                            'codesign_verified': True}
    for command, data in commands.items():
        args = [data['path']] + ([] if command == 'ldid' else ['--version'])
        proc = _run(args, dict(env, DYLD_PRINT_LIBRARIES='1'), check=False)
        if proc.returncode not in ((0, 1) if command == 'ldid' else (0,)):
            raise ValueError('compatible binary smoke failed: ' + command)
        if 'Library not loaded' in proc.stdout:
            raise ValueError('compatible loader smoke failed: ' + command)
        reported_version = data['version']
        version_source = 'installed-core-receipt'
        if command != 'ldid':
            patterns = {'make': r'^GNU Make ([0-9]+(?:\.[0-9]+)+)',
                        'xz': r'^xz \(XZ Utils\) ([0-9]+(?:\.[0-9]+)+)',
                        'dpkg-deb': r'backend version ([0-9]+(?:\.[0-9]+)+)'}
            match = re.search(patterns[command], proc.stdout, re.M)
            if not match or _compare(match.group(1), data['version'].split('_')[0]) != 0:
                raise ValueError('binary version differs from installed core receipt: ' + command +
                                 '; expected=' + data['version'] + '; parsed=' +
                                 (match.group(1) if match else '<no match>') +
                                 '; path=' + data['path'] + '; output=' + proc.stdout[-6000:])
            reported_version = match.group(1)
            version_source = 'binary-and-installed-core-receipt'
        loaded = re.findall(r'^dyld\[[0-9]+\]:[^\n]*?(/[^\n]+)', proc.stdout, re.M)
        if not loaded:
            raise ValueError('dyld smoke produced no library evidence: ' + command)
        actual = []
        allowed = _closure(data['package'], packages) | {data['package']}
        for entry in loaded:
            entry = entry.strip()
            if _system_path(entry):
                actual.append({'resolved': entry, 'system': True})
                continue
            owner, real = _owned(Path(entry), kegs)
            if owner not in allowed:
                raise ValueError('dyld loaded a library outside root runtime closure: ' + owner)
            actual.append({'package': owner, 'resolved': str(real)})
        evidence['runtime_smoke'][command] = {'returncode': proc.returncode,
                                              'version': reported_version, 'version_source': version_source,
                                              'loaded_libraries': actual, 'output': proc.stdout}
    return evidence


def _unchanged(packages, commands, evidence):
    for name, pkg in packages.items():
        keg = Path(pkg['keg'])
        if ((PREFIX / 'opt' / name).resolve(strict=True) != keg
                or _sha(keg / '.brew' / (name + '.rb')) != pkg['formula_sha256']
                or _sha(keg / 'INSTALL_RECEIPT.json') != pkg['install_receipt_sha256']):
            raise ValueError('installed closure changed during audit: ' + name)
    for path, info in evidence['mach_o'].items():
        if _sha(path) != info['sha256']:
            raise ValueError('Mach-O changed during audit: ' + path)
    for command, info in commands.items():
        if (Path(info['path_entry']).resolve(strict=True) != Path(info['path'])
                or _sha(info['path']) != info['sha256']):
            raise ValueError('command changed during audit: ' + command)


def verify_packaging(lock):
    validate_compatibility(lock)
    brew, env, source = _context()
    packages = _discover(lock, brew, env)
    commands = _commands(packages)
    evidence = _audit(packages, commands, env)
    _unchanged(packages, commands, evidence)
    evidence.update({'status': 'compatible-verified', 'packages': packages, 'commands': commands,
                     'dependency_closure': {n: p['dependencies'] for n, p in packages.items()},
                     'source': source, 'tool_versions': 'compatible',
                     'guarantee': 'Observed core formula receipts, installed bytes and runtime resolutions; '
                                  'not immutable download hashes or a reproducible VM image.'})
    return evidence


def install_packaging(lock, cache):
    """Only install missing roots, with no upgrade/uninstall/reset of existing tools."""
    validate_compatibility(lock)
    if (os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'):
        raise ValueError('automatic installation requires disposable GitHub-hosted runner')
    brew, env, _ = _context()
    existing, missing = {}, []
    # Preflight ALL roots before the first installation. Never use a different tap
    # or silently install the next major/minor when current core has moved ahead.
    for name in ROOTS:
        info = _info(brew, env, name)
        current = _observe(name, info, missing=True)
        if current is not None:
            _root_range(lock, name, current['version'])
            existing[name] = current
        else:
            stable = info.get('versions', {}).get('stable')
            candidate = _entry_version({'version': stable, 'revision': info.get('revision', 0)})
            _root_range(lock, name, candidate)
            missing.append(name)
    for name in missing:
        _run([brew, 'install', '--formula', '--force-bottle', 'homebrew/core/' + name], env)
    for name in ROOTS:
        current = _observe(name, _info(brew, env, name))
        _root_range(lock, name, current['version'])
        if name in existing:
            for key in ('version', 'keg', 'formula_sha256', 'install_receipt_sha256'):
                if current[key] != existing[name][key]:
                    raise ValueError('Homebrew unexpectedly modified an existing compatible root: ' + name)
    # cache is intentionally unused: compatible mode does not pretend to maintain
    # the strict baseline's bottle-byte cache. The caller prepares PATH then verifies.
