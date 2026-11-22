import ast,hashlib,importlib.util,json,plistlib,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).resolve().parents[1]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class SQCCMSourceTests(unittest.TestCase):
    def test_production_behavior_and_resources_frozen(self):
        receipt=json.loads((P/'docs/upstream-source.json').read_text());checked=0
        for name,item in receipt['files'].items():
            if name.endswith(('.m','.h','.plist','.png')):
                self.assertEqual(hashlib.sha256((P/name).read_bytes()).hexdigest(),item['sha256'],name);checked+=1
        self.assertEqual(checked,19)
    def test_old_builder_archived_and_unreachable(self):
        rec=json.loads((P/'docs/upstream-source.json').read_text())
        self.assertEqual(hashlib.sha256((P/'docs/legacy-build-native.py.txt').read_bytes()).hexdigest(),rec['files']['scripts/build-native.py']['sha256'])
        text=(P/'scripts/build-native.py').read_text();self.assertIn('os.execv',text);self.assertNotIn('GLIBC_LOADER',text)
    def test_all_python_parse(self):
        paths=list((P/'scripts').glob('*.py'))+list((P/'tests').rglob('*.py'))
        self.assertGreaterEqual(len(paths),8)
        for path in paths:ast.parse(path.read_text(),filename=str(path))
    def test_toolchain_static(self):
        tool=load('sqccm_toolchain',P/'scripts/toolchain.py');self.assertEqual(tool.static_errors(P),[])
    def test_actions_path_priority_matches_current_process(self):
        tool=load('sqccm_path_toolchain',P/'scripts/toolchain.py')
        import os
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'github-path'
            paths=['/verified/make','/verified/dpkg','/theos/bin']
            with patch.dict(os.environ,{'PATH':'/usr/bin','GITHUB_PATH':str(target)}):
                tool.activate_paths(paths)
                self.assertEqual(os.environ['PATH'].split(':')[:3],paths)
                actions=[]
                for line in target.read_text().splitlines():actions.insert(0,line)
                self.assertEqual(actions,paths)
    def test_package_version_identity_and_dependencies(self):
        control=dict(x.split(': ',1) for x in (P/'control').read_text().splitlines() if ': ' in x)
        self.assertEqual(control['Package'],'com.saoqiang.ccmedia');self.assertEqual(control['Version'],'3.1415926-2')
        self.assertIn('roothide',control['Depends'].split(', '));self.assertEqual(control['Architecture'],'iphoneos-arm64e')
        out=subprocess.check_output([sys.executable,P/'scripts/package_version.py'],text=True);self.assertEqual(out.strip(),control['Version'])
    def test_bundle_and_loader_identity(self):
        ids=set()
        for i in range(1,7):
            s='' if i==1 else str(i);info=plistlib.loads((P/('Module/Resources'+s)/'Info.plist').read_bytes())
            self.assertEqual(info['CFBundleIdentifier'],'com.saoqiang.ccmedia.module'+s)
            self.assertEqual(info['NSPrincipalClass'],'SQCCMMediaModule'+str(i));ids.add(info['CFBundleIdentifier'])
        self.assertEqual(len(ids),6)
        e=plistlib.loads((P/'layout/Library/PreferenceLoader/Preferences/SaoqiangCCMedia.plist').read_bytes())['entry']
        self.assertEqual(e['detail'],'SQCCMPreferencesController')
    def test_scheme_rejected_before_any_build(self):
        for args in (['rootless'],['rootful'],['roothide','extra']):
            r=subprocess.run(['sh',str(P/'build.sh'),*args],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0);self.assertIn('Only the original RootHide',r.stderr)
    def test_ui_resource_copies_are_originals(self):
        for name in ['Root.plist','Icon.png','ListIcon.png','ListIcon@2x.png','ListIcon@3x.png']:
            self.assertEqual((P/'tests/ui'/name).read_bytes(),(P/'Preferences/Resources'/name).read_bytes())
    def test_no_production_hook_added(self):
        for base in ['Module','Preferences','Shared']:
            for path in (P/base).rglob('*'):
                if path.suffix in ('.m','.h'):self.assertNotIn('MSHook',path.read_text())

class SQCCMUIRunnerUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.ui=load('sqccm_ui_runner',P/'tests/ui/run_panel_tests.py')
    def result(self):return {'status':'PASS','runToken':'current','checks':10,'completedCases':8,'failures':[],'mode':'real-uikit-public-frameworks-test-only-preferences-substitute'}
    def test_accept_complete_current_result(self):self.assertEqual(self.ui.validate_result(self.result(),'current')['checks'],10)
    def test_reject_empty_stale_and_failures(self):
        for changes in [{'checks':0},{'checks':True},{'completedCases':7},{'runToken':'old'},{'status':'FAIL'},{'failures':['broken']},{'mode':'static'}]:
            with self.subTest(changes=changes),self.assertRaises(RuntimeError):self.ui.validate_result(dict(self.result(),**changes),'current')
    def test_mocked_command_assembly_and_resources(self):
        calls=[]
        def checked(args,**kw):
            if '--show-sdk-version' in args:return '18.5'
            if '--show-sdk-path' in args:return '/selected/Simulator.sdk'
            return '/selected/clang'
        with tempfile.TemporaryDirectory() as tmp,patch.object(self.ui,'checked',side_effect=checked),patch.object(self.ui,'streamed',side_effect=lambda cmd,*a,**k:calls.append(cmd)),patch.object(self.ui.platform,'machine',return_value='arm64'),patch.object(self.ui.shutil,'which',return_value='/usr/bin/codesign'):
            root=Path(tmp);app=self.ui.compile_app(root,root,'abcd')
            self.assertTrue((app/'Root.plist').is_file());self.assertTrue((app/'Icon.png').is_file())
        compile_calls=[x for x in calls if '-c' in x];self.assertEqual(len(compile_calls),3)
        self.assertTrue(any(str(self.ui.PREFERENCES) in list(map(str,c)) for c in compile_calls))
        self.assertTrue(all('arm64-apple-ios15.0-simulator' in c for c in compile_calls))
        self.assertTrue(all('-DSQCCM_TEST_RUN_TOKEN=@"abcd"' in c for c in compile_calls))
    def test_runtime_choice_excludes_newer_than_sdk(self):
        runtimes={'runtimes':[{'identifier':'com.apple.CoreSimulator.SimRuntime.iOS-18-5','version':'18.5','isAvailable':True},{'identifier':'com.apple.CoreSimulator.SimRuntime.iOS-26-0','version':'26.0','isAvailable':True}]}
        devices={'devices':{r['identifier']:[{'name':'iPhone 16','isAvailable':True,'deviceTypeIdentifier':'iphone16'}] for r in runtimes['runtimes']}}
        self.assertEqual(self.ui.choose_simulator('18.5',runtimes,devices)[2],'18.5')
