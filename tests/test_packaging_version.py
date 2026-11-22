import importlib.util,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'scripts'))
import compatible_packaging as cp
class SQCCMPackagingVersionTests(unittest.TestCase):
    def audit(self,version_line):
        packages={'dpkg':{'keg':'/verified/dpkg','dependencies':[]}}
        commands={'dpkg-deb':{'path':'/verified/dpkg/bin/dpkg-deb','version':'1.23.12','package':'dpkg'}}
        stdout='dyld[12]: /usr/lib/libSystem.B.dylib\n'+version_line+'\n'
        with patch.object(cp._HELPERS,'macho_files',return_value=[]),patch.object(cp,'_run',return_value=subprocess.CompletedProcess([],0,stdout=stdout)):
            return cp._audit(packages,commands,{})
    def test_system_interpreter_only_exact_paths(self):
        for path in ('/bin/bash','/bin/sh','/usr/bin/perl','/usr/lib/libSystem.B.dylib'):
            self.assertTrue(cp._system_runtime_image(path))
        for path in ('/tmp/bash','/bin/bash.dylib','/bin/../tmp/bash','/opt/homebrew/lib/unknown.dylib'):
            self.assertFalse(cp._system_runtime_image(path))
    def test_native_darwin_dpkg_banner(self):
        r=self.audit('dpkg-deb version 1.23.12 (darwin-arm64)')
        self.assertEqual(r['runtime_smoke']['dpkg-deb']['version'],'1.23.12')
    def test_debian_backend_banner(self):
        self.assertEqual(self.audit('Debian \'dpkg-deb\' package archive backend version 1.23.12 (arm64).')['runtime_smoke']['dpkg-deb']['version'],'1.23.12')
    def test_wrong_version_and_wrong_command_rejected(self):
        for text in ['dpkg-deb version 1.23.11 (darwin-arm64)','xz version 1.23.12','unrelated backend version 1.23.12']:
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'binary version differs'):self.audit(text)
