import importlib.util
import io
import os
import subprocess
from pathlib import Path
import tarfile
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('activate',Path(__file__).resolve().parents[1]/'deploy/activate-production.py')
activate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(activate)

class ArchiveTests(unittest.TestCase):
    def extract(self,name,kind=tarfile.REGTYPE,duplicate=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            archive=root/'input.tar'
            output=root/'release';output.mkdir()
            with tarfile.open(archive,'w') as tar:
                member=tarfile.TarInfo(name);member.type=kind
                member.linkname='/etc/passwd'
                member.size=2 if kind==tarfile.REGTYPE else 0
                tar.addfile(member,io.BytesIO(b'ok') if member.size else None)
                if duplicate: tar.addfile(member,io.BytesIO(b'ok'))
            activate.unpack(archive,output)
            if kind==tarfile.REGTYPE:
                self.assertEqual((output/name).read_bytes(),b'ok')
    def test_packager_flattens_symbolic_and_hard_links_for_safe_extractor(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            stage=root/'stage';stage.mkdir()
            (stage/'original').write_bytes(b'scenario contents')
            os.link(stage/'original',stage/'hardlink')
            (stage/'symlink').symlink_to('original')
            archive=root/'release.tar'
            script=Path(__file__).resolve().parents[1]/'scripts/package-production-archive.sh'
            subprocess.run(['bash',str(script),str(stage),str(archive)],check=True)
            output=root/'output';output.mkdir()
            activate.unpack(archive,output)
            for name in ('original','hardlink','symlink'):
                self.assertEqual((output/name).read_bytes(),b'scenario contents')
                self.assertFalse((output/name).is_symlink())

    def test_regular_file(self): self.extract('build/server')
    def test_parent_escape(self):
        with self.assertRaises(ValueError): self.extract('../outside')
    def test_absolute_path(self):
        with self.assertRaises(ValueError): self.extract('/outside')
    def test_symlink(self):
        with self.assertRaises(ValueError): self.extract('link',tarfile.SYMTYPE)
    def test_hardlink(self):
        with self.assertRaises(ValueError): self.extract('link',tarfile.LNKTYPE)
    def test_duplicate(self):
        with self.assertRaises(FileExistsError): self.extract('file',duplicate=True)
if __name__=='__main__': unittest.main()
