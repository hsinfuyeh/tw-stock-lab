import importlib.util
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import io
import os

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/state_archive.py'
spec=importlib.util.spec_from_file_location('state_archive',SCRIPT)
archive_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive_module)


class StateArchiveTests(unittest.TestCase):
    def test_fast_archive_preserves_every_included_byte_and_exclusions(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'source';(root/'raw').mkdir(parents=True);(root/'snapshots').mkdir()
            (root/'research.sqlite3').write_bytes(bytes(range(256))*100)
            (root/'raw/evidence.json').write_text('{"原始":"證據"}',encoding='utf-8')
            (root/'update.lock').write_text('lock');(root/'market-bundles.json').write_text('duplicate')
            (root/'snapshots/old.json').write_text('duplicate snapshot')
            fast=Path(temp)/'fast.tar.gz';small=Path(temp)/'small.tar.gz'
            archive_module.pack_state(fast,root=root)
            archive_module.pack_state(small,root=root,compresslevel=9)
            with tarfile.open(fast) as reader,tarfile.open(small) as reference:
                names=reader.getnames();self.assertEqual(names,reference.getnames())
                self.assertEqual(set(names),{'data/research.sqlite3','data/raw/evidence.json'})
                for name in names:
                    self.assertEqual(reader.extractfile(name).read(),reference.extractfile(name).read())
            destination=Path(temp)/'restore';destination.mkdir()
            result=subprocess.run([sys.executable,'-X','utf8',str(SCRIPT),'restore',str(fast)],cwd=destination,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((destination/'data/research.sqlite3').read_bytes(),(root/'research.sqlite3').read_bytes())

    def test_restore_rejects_escaping_member_before_any_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            filename=Path(temp)/'unsafe.tar.gz'
            with tarfile.open(filename,'w:gz') as archive:
                info=tarfile.TarInfo('../escape.txt');info.size=3;archive.addfile(info,io.BytesIO(b'bad'))
            result=subprocess.run([sys.executable,str(SCRIPT),'restore',str(filename)],cwd=temp,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((Path(temp)/'data').exists())

    def test_local_hardlinked_files_remain_safely_restorable_regular_members(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'source';root.mkdir();original=root/'original.json';original.write_bytes(b'public evidence')
            try: os.link(original,root/'second.json')
            except OSError as error: self.skipTest('Filesystem does not support hard links: '+str(error))
            filename=Path(temp)/'linked.tar.gz';archive_module.pack_state(filename,root=root)
            with tarfile.open(filename) as reader:
                self.assertTrue(all(member.isfile() for member in reader.getmembers()))
            destination=Path(temp)/'restore';destination.mkdir()
            result=subprocess.run([sys.executable,str(SCRIPT),'restore',str(filename)],cwd=destination,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((destination/'data/second.json').read_bytes(),original.read_bytes())

if __name__=='__main__': unittest.main()
