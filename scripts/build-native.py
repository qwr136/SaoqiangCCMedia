#!/usr/bin/env python3
"""Native RootHide arm64e build. Only Python's standard library is required.

Full build: python3 scripts/build-native.py
Separate phases: --compile-only, then --link-only, then --package-only.
--check only validates resources and local tool paths; it never compiles/links.
Environment: CLANG, SDKROOT, THEOS_INCLUDE, ROOTHIDE_INCLUDE, ROOTHIDE_LIB,
TOOLCHAIN_ROOT, GLIBC_RUNTIME, GLIBC_LOADER, LD, LDID, DPKG_DEB,
EXTRA_CFLAGS, EXTRA_LDFLAGS, BUILD_DIR, DEB_OUTPUT, SOURCE_DATE_EPOCH.
LD_COMMAND may replace the entire linker invocation (shell-style words).
The SDK directory is labelled 16.5 locally; its actual version is read from
SDKSettings.plist (currently 16.4), never inferred from the directory name.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = '3.1415926'
PACKAGE = 'com.saoqiang.ccmedia'
DEPLOYMENT = '15.0'
BASE = Path('/var/minis/workspace/ios-build')
LOADER = Path('Library/PreferenceLoader/Preferences/SaoqiangCCMedia.plist')
MODULE_FRAMEWORKS = ['Foundation', 'UIKit', 'AVFoundation', 'ImageIO',
                     'QuartzCore', 'CoreMedia', 'CoreGraphics', 'ControlCenterUIKit']
PREFS_FRAMEWORKS = ['Foundation', 'UIKit', 'PhotosUI', 'Photos',
                    'UniformTypeIdentifiers', 'AVFoundation', 'ImageIO',
                    'CoreMedia', 'CoreGraphics', 'Preferences']
TARGETS = []
for index in range(1, 7):
    suffix = '' if index == 1 else str(index)
    TARGETS.append(dict(name='SaoqiangCCMedia' + suffix, index=index,
        source='Module/SQCCMModule.m', resources='Module/Resources' + suffix,
        install='Library/ControlCenter/Bundles', frameworks=MODULE_FRAMEWORKS))
TARGETS.append(dict(name='SaoqiangCCMediaPrefs', index=None,
    source='Preferences/SQCCMPreferences.m', resources='Preferences/Resources',
    install='Library/PreferenceBundles', frameworks=PREFS_FRAMEWORKS))


def log(message):
    print(message, flush=True)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_plist(path):
    return plistlib.loads(path.read_bytes())


def read_control(path):
    return dict(line.split(': ', 1) for line in path.read_text().splitlines()
                if line and not line.startswith((' ', '\t')))


def check_resources():
    control = read_control(ROOT / 'control')
    for key, expected in [('Package', PACKAGE), ('Version', VERSION),
                          ('Architecture', 'iphoneos-arm64e')]:
        require(control.get(key) == expected, f'control {key} must be {expected}')
    expected_loaders = [ROOT / 'layout' / LOADER]
    actual_loaders = sorted((ROOT / 'layout').rglob('*.plist'))
    require(actual_loaders == expected_loaders, 'Keep exactly the original PreferenceLoader entry in layout')
    entry = read_plist(expected_loaders[0])['entry']
    require(entry['bundle'] == 'SaoqiangCCMediaPrefs' and
            entry['detail'] == 'SQCCMPreferencesController', 'Incorrect PreferenceLoader target')
    for target in TARGETS:
        info = read_plist(ROOT / target['resources'] / 'Info.plist')
        name, index = target['name'], target['index']
        require(info['CFBundleExecutable'] == name and info['CFBundleName'] == name,
                f'{name}: bundle/executable mismatch')
        require(info['CFBundleShortVersionString'] == VERSION and info['CFBundleVersion'] == VERSION,
                f'{name}: inconsistent version')
        principal = f'SQCCMMediaModule{index}' if index else 'SQCCMPreferencesController'
        suffix = '' if index == 1 else str(index)
        identifier = PACKAGE + ('.module' + suffix if index else '.preferences')
        require(info['NSPrincipalClass'] == principal and info['CFBundleIdentifier'] == identifier,
                f'{name}: incorrect principal class or upgrade identity')
        if index:
            require(info['CFBundleDisplayName'] == f'骚强媒体 {index}' and
                    info.get('CCSGetModuleSizeAtRuntime') is True,
                    f'{name}: missing label/runtime size policy')
    items = read_plist(ROOT / 'Preferences/Resources/Root.plist')['items']
    keyed = {item['key']: item for item in items if 'key' in item}
    require(set(keyed)=={'customName','enabled','width','height','contentMode','noMargin','pixelArt','sound','opacity','deviceStyle','cornerRadius'},'Unexpected keys')
    for key,item in keyed.items():
        require(item.get('get')=='readPreferenceValue:' and item.get('set')=='setPreferenceValue:specifier:',f'{key}: accessors')
    for key in ('width','height'):
        require(keyed[key]['min']==1 and keyed[key]['max']==4,'Grid slider range')
    require(keyed['contentMode']['validValues']==[1,2,3],'Content mode values')


def settings(args):
    def envpath(key, fallback):
        return Path(os.environ.get(key, str(fallback))).expanduser().resolve()
    toolchain = envpath('TOOLCHAIN_ROOT', '/tmp/ccmedia-toolchain-new/linux/iphone')
    runtime = envpath('GLIBC_RUNTIME', '/tmp/ccmedia-glibc239/root/usr/lib/aarch64-linux-gnu')
    build = Path(args.build_dir or os.environ.get('BUILD_DIR', ROOT / 'artifacts/native-roothide-3.1415926')).expanduser().resolve()
    require(build not in (ROOT, ROOT.parent, Path('/')), 'BUILD_DIR must be a dedicated artifact directory')
    config = dict(build=build, stage=build / 'stage', objects=build / 'objects',
        sdk=envpath('SDKROOT', BASE / 'theos-repo/sdks/iPhoneOS16.5.sdk'),
        clang=os.environ.get('CLANG', '/tmp/ccmedia-clang-modern'),
        include=envpath('THEOS_INCLUDE', BASE / 'theos-repo/vendor/include'),
        rh_include=envpath('ROOTHIDE_INCLUDE', '/tmp/ccmedia-rh-headers'),
        rh_lib=envpath('ROOTHIDE_LIB', '/tmp/ccmedia-rh-lib'),
        ldid=os.environ.get('LDID', str(BASE / 'probe/ldid-src/ldid')),
        dpkg=os.environ.get('DPKG_DEB', 'dpkg-deb'),
        extra_cflags=shlex.split(os.environ.get('EXTRA_CFLAGS', '')),
        extra_ldflags=shlex.split(os.environ.get('EXTRA_LDFLAGS', '')),
        output=Path(args.output or os.environ.get('DEB_OUTPUT', ROOT / 'delivery/SaoqiangCCMedia-3.1415926-roothide.deb')).expanduser().resolve())
    config['ld'] = shlex.split(os.environ['LD_COMMAND']) if os.environ.get('LD_COMMAND') else [
        str(envpath('GLIBC_LOADER', runtime / 'ld-linux-aarch64.so.1')),
        '--library-path', str(runtime) + ':' + str(toolchain / 'lib'),
        os.environ.get('LD', str(toolchain / 'bin/ld'))]
    if (config['sdk'] / 'SDKSettings.plist').is_file():
        config['sdk_version'] = str(read_plist(config['sdk'] / 'SDKSettings.plist')['Version'])
    else:
        config['sdk_version'] = None
    require(not config['output'].is_relative_to(config['stage']), 'DEB_OUTPUT cannot be inside staging')
    return config


def executable(command):
    require(bool(shutil.which(str(command))), f'Executable missing: {command}')


def check_tools(config, phase):
    if phase in ('compile', 'link', 'check'):
        require(config['sdk_version'], f'SDKSettings.plist missing: {config["sdk"]}')
        require((config['rh_include'] / 'roothide.h').is_file(), 'ROOTHIDE_INCLUDE/roothide.h missing')
        require((config['include'] / 'Preferences/PSListController.h').is_file(), 'THEOS_INCLUDE Preferences headers missing')
    if phase in ('compile', 'check'):
        executable(config['clang'])
    if phase in ('link', 'check'):
        executable(config['ld'][0])
        if '--library-path' in config['ld']:
            require(Path(config['ld'][-1]).is_file(), 'Native linker missing')
        executable(config['ldid'])
        require(any((config['rh_lib'] / ('libroothide' + ext)).is_file()
                    for ext in ('.tbd', '.dylib', '.a')), 'ROOTHIDE_LIB lacks libroothide')
    if phase in ('package', 'check'):
        executable(config['dpkg'])


def run(command):
    log('  $ ' + shlex.join(map(str, command)))
    subprocess.run(list(map(str, command)), check=True)


def compile_command(config, target):
    command = [config['clang'], '-target', 'arm64e-apple-ios' + DEPLOYMENT,
        '-isysroot', str(config['sdk']), '-I' + str(config['include']),
        '-I' + str(config['rh_include']), '-DTHEOS_PACKAGE_SCHEME_ROOTHIDE=1',
        '-fobjc-arc', '-fblocks', '-fno-modules', '-Os', '-Wall', '-Wextra',
        '-Wno-unused-parameter']
    if target['index']:
        command.append('-DSQCCM_MODULE_INDEX=' + str(target['index']))
    return command + config['extra_cflags'] + ['-c', str(ROOT / target['source']),
            '-o', str(config['objects'] / (target['name'] + '.o'))]


def inputs(config):
    paths = [ROOT / 'Module/SQCCMModule.m', ROOT / 'Preferences/SQCCMPreferences.m']
    paths += sorted((ROOT / 'Shared').glob('*.h'))
    return dict(files={str(path.relative_to(ROOT)): digest(path) for path in paths},
                commands=[compile_command(config, target) for target in TARGETS])


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def compile_all(config):
    check_tools(config, 'compile')
    config['objects'].mkdir(parents=True, exist_ok=True)
    manifest = config['build'] / 'compile.json'
    manifest.unlink(missing_ok=True)
    snapshot = inputs(config)
    for number, target in enumerate(TARGETS, 1):
        log(f'[{number}/7] Compile {target["name"]}')
        run(compile_command(config, target))
    require(snapshot == inputs(config), 'Sources changed during compilation; rerun --compile-only')
    objects = {target['name'] + '.o': digest(config['objects'] / (target['name'] + '.o')) for target in TARGETS}
    write_json(manifest, dict(version=VERSION, inputs=snapshot, objects=objects))
    log('Compile complete: all seven arm64e objects recorded.')


def verify_macho(path):
    raw = path.read_bytes()
    require(len(raw) >= 32, f'{path}: truncated Mach-O')
    magic, cpu, subtype, filetype, ncmds, sizeofcmds = struct.unpack_from('<6I', raw)
    require(magic == 0xfeedfacf and cpu == 0x0100000c and subtype == 0x80000002,
            f'{path}: expected thin arm64e subtype 0x80000002, got {subtype:#010x}')
    require(filetype == 8, f'{path}: expected MH_BUNDLE')
    signature = False
    offset = 32
    for _ in range(ncmds):
        cmd, length = struct.unpack_from('<II', raw, offset)
        require(length >= 8 and offset + length <= len(raw), f'{path}: invalid load command')
        if cmd == 0x1d:
            start, size = struct.unpack_from('<II', raw, offset + 8)
            signature = size > 0 and start + size <= len(raw)
        offset += length
    require(signature, f'{path}: LC_CODE_SIGNATURE missing or empty')


def expected_stage_files():
    result = {str(LOADER),str(LOADER.with_name('SaoqiangCCMedia.png'))}
    for target in TARGETS:
        bundle = Path(target['install']) / (target['name'] + '.bundle')
        result.update(str(bundle / name) for name in [target['name'], 'Info.plist'])
        if target['index'] is None:
            result.update(str(bundle / n) for n in ['Root.plist','Icon.png','ListIcon.png','ListIcon@2x.png','ListIcon@3x.png'])
    return result


def verify_stage(config):
    stage = config['stage']
    require(stage.is_dir(), 'No staging directory; run --link-only first')
    actual = set()
    for path in stage.rglob('*'):
        require(not path.is_symlink(), f'Unexpected symlink in staging: {path}')
        if path.is_file():
            actual.add(str(path.relative_to(stage)))
    require(actual == expected_stage_files(),
            f'Staging differs from whitelist: extra={sorted(actual - expected_stage_files())}, missing={sorted(expected_stage_files() - actual)}')
    for target in TARGETS:
        bundle = stage / target['install'] / (target['name'] + '.bundle')
        verify_macho(bundle / target['name'])
        for resource in ['Info.plist'] + ([] if target['index'] else ['Root.plist', 'Icon.png','ListIcon.png','ListIcon@2x.png','ListIcon@3x.png']):
            require((bundle / resource).read_bytes() == (ROOT / target['resources'] / resource).read_bytes(),
                    f'{bundle}: resource changed since link; rerun --link-only')
    require((stage / LOADER).read_bytes() == (ROOT / 'layout' / LOADER).read_bytes(), 'Loader changed since link')


def link_all(config):
    check_tools(config, 'link')
    manifest = config['build'] / 'compile.json'
    require(manifest.is_file(), 'No compile manifest; run --compile-only first')
    state = json.loads(manifest.read_text())
    require(state['inputs'] == inputs(config), 'Sources/compiler options changed; rerun --compile-only')
    for name, checksum in state['objects'].items():
        require(digest(config['objects'] / name) == checksum, f'Object changed: {name}; rerun --compile-only')
    stage = config['stage']
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for number, target in enumerate(TARGETS, 1):
        name = target['name']
        log(f'[{number}/7] Link/sign {name}')
        bundle = stage / target['install'] / (name + '.bundle')
        bundle.mkdir(parents=True)
        resources = ['Info.plist'] + ([] if target['index'] else ['Root.plist', 'Icon.png','ListIcon.png','ListIcon@2x.png','ListIcon@3x.png'])
        for resource in resources:
            shutil.copyfile(ROOT / target['resources'] / resource, bundle / resource)
        binary = bundle / name
        command = config['ld'] + ['-bundle', '-arch', 'arm64e', '-platform_version',
            'ios', DEPLOYMENT, config['sdk_version'], '-syslibroot', str(config['sdk']),
            '-F' + str(config['sdk'] / 'System/Library/PrivateFrameworks'),
            '-L' + str(config['rh_lib']), '-lroothide', '-lSystem', '-lobjc',
            '-o', str(binary), str(config['objects'] / (name + '.o'))]
        for framework in target['frameworks']:
            command.extend(['-framework', framework])
        run(command + config['extra_ldflags'])
        run([config['ldid'], '-Hsha256', '-S', '-Cadhoc', str(binary)])
        binary.chmod(0o755)
        verify_macho(binary)
        log(f'  Verified {name}: arm64e subtype=0x80000002; code signature present')
    loader = stage / LOADER
    loader.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'layout' / LOADER, loader)
    shutil.copyfile(ROOT/'layout'/LOADER.with_name('SaoqiangCCMedia.png'),loader.with_name('SaoqiangCCMedia.png'))
    verify_stage(config)
    write_json(config['build'] / 'linked.json', dict(version=VERSION,
        inputs=state['inputs'], files={name: digest(stage / name) for name in sorted(expected_stage_files())}))
    log('Link/sign complete: exactly six CC bundles, one prefs bundle, one loader.')


def package(config):
    check_tools(config, 'package')
    verify_stage(config)
    state = json.loads((config['build'] / 'linked.json').read_text())
    require(state['inputs'] == inputs(config), 'Sources/options changed since link; rebuild first')
    for name, checksum in state['files'].items():
        require(digest(config['stage'] / name) == checksum, f'Staged file changed: {name}')
    # A fresh package root avoids old drafts, stale resources and prior DEBIAN files.
    package_root = config['build'] / 'package-root'
    if package_root.exists():
        shutil.rmtree(package_root)
    shutil.copytree(config['stage'], package_root)
    debian = package_root / 'DEBIAN'
    debian.mkdir()
    shutil.copyfile(ROOT / 'control', debian / 'control')
    epoch = int(os.environ.get('SOURCE_DATE_EPOCH', '1700000000'))
    for path in [package_root] + sorted(package_root.rglob('*')):
        path.chmod(0o755 if path.is_dir() or path.name in {t['name'] for t in TARGETS} else 0o644)
        os.utime(path, (epoch, epoch))
    config['output'].parent.mkdir(parents=True, exist_ok=True)
    temporary = config['output'].with_suffix('.deb.tmp')
    log('Package 3.1415926: whitelist verified (18 data files, no draft payloads)')
    previous = os.environ.get('SOURCE_DATE_EPOCH')
    os.environ['SOURCE_DATE_EPOCH'] = str(epoch)
    try:
        run([config['dpkg'], '--root-owner-group', '-Zxz', '-b', str(package_root), str(temporary)])
    finally:
        if previous is None:
            os.environ.pop('SOURCE_DATE_EPOCH', None)
        else:
            os.environ['SOURCE_DATE_EPOCH'] = previous
    temporary.replace(config['output'])
    log(f'Complete: {config["output"]} ({config["output"].stat().st_size} bytes)')
    log('SHA256: ' + digest(config['output']))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--compile-only', action='store_true', help='Compile all seven objects without linking')
    group.add_argument('--link-only', action='store_true', help='Link/sign existing verified objects; do not package')
    group.add_argument('--package-only', action='store_true', help='Package existing signed staging; no compiler/linker invocation')
    group.add_argument('--check', action='store_true', help='Check tools and resources only')
    parser.add_argument('--build-dir', help='Artifact directory (or BUILD_DIR)')
    parser.add_argument('--output', help='Output deb path (or DEB_OUTPUT)')
    args = parser.parse_args()
    config = settings(args)
    check_resources()
    log('RootHide native arm64e 3.1415926: six CC modules + one preferences bundle')
    log(f'SDKROOT={config["sdk"]}; actual SDK version={config["sdk_version"]}')
    log('Artifacts: ' + str(config['build']))
    if args.check:
        check_tools(config, 'check')
        log('Resource/tool checks passed; no compiler or linker was run.')
        return
    if args.package_only:
        package(config)
    elif args.link_only:
        link_all(config)
    elif args.compile_only:
        compile_all(config)
    else:
        compile_all(config)
        link_all(config)
        package(config)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        log('ERROR: ' + str(error))
        sys.exit(1)
