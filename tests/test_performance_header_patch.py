"""The performance header must be creatable in a fresh upstream checkout."""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class PerformanceHeaderPatchTest(unittest.TestCase):
    def test_new_header_applies_and_reverses_without_preexisting_file(self):
        text=(ROOT/'openrct2-patches/0022-performance-instrumentation.patch').read_text()
        marker='diff --git a/src/openrct2/paint/BridgePerformance.h '
        part=marker+text.split(marker,1)[1]
        part=part.split('\ndiff --git ',1)[0]+'\n'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            patch=root/'header.patch';patch.write_text(part)
            subprocess.run(['git','-C',str(root),'apply',str(patch)],check=True,capture_output=True)
            header=root/'src/openrct2/paint/BridgePerformance.h'
            self.assertIn('namespace BridgePerf',header.read_text())
            subprocess.run(['git','-C',str(root),'apply','--reverse',str(patch)],check=True,capture_output=True)
            self.assertFalse(header.exists())
if __name__=='__main__':unittest.main()
