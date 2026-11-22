import importlib.util,io,tarfile,unittest
from pathlib import Path
from verify_deb import require_strong_roothide
P=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('normalize',P/'scripts/normalize_package.py');normalize=importlib.util.module_from_spec(s);s.loader.exec_module(normalize)
class SQCCMPackageTests(unittest.TestCase):
    def test_require_strong_roothide(self):
        target='@loader_path/.jbroot/usr/lib/libroothide.dylib'
        require_strong_roothide([(0xc,target)])
        for commands in ([],[(0x80000018,target)],[(0xc,target),(0x80000018,target)]):
            with self.subTest(commands=commands),self.assertRaises(ValueError):require_strong_roothide(commands)
    def test_owner_normalization_retains_payload_and_modes(self):
        raw=io.BytesIO();payload=b'signed payload bytes\x00'
        with tarfile.open(fileobj=raw,mode='w') as tf:
            info=tarfile.TarInfo('./Library/Prefs/binary');info.size=len(payload);info.mode=0o755;info.uid=501;info.gid=20;tf.addfile(info,io.BytesIO(payload))
        converted,owners=normalize.normalize_tar(raw.getvalue())
        self.assertEqual(owners[0]['uid'],501)
        with tarfile.open(fileobj=io.BytesIO(converted)) as tf:
            item=tf.next();self.assertEqual((item.uid,item.gid,item.mode),(0,0,0o755));self.assertEqual(tf.extractfile(item).read(),payload)
    def test_owner_normalization_rejects_links(self):
        raw=io.BytesIO()
        with tarfile.open(fileobj=raw,mode='w') as tf:
            info=tarfile.TarInfo('bad');info.type=tarfile.SYMTYPE;info.linkname='/etc/passwd';tf.addfile(info)
        with self.assertRaises(ValueError):normalize.normalize_tar(raw.getvalue())
    def test_ar_container_roundtrip(self):
        result=normalize.make_ar([('debian-binary',b'2.0\n'),('data.tar.gz',b'123')])
        self.assertTrue(result.startswith(b'!<arch>\n'));self.assertEqual(len(result),(8+60+4+60+4))
