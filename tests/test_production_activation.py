import importlib.util
import builtins
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('activate',Path(__file__).resolve().parents[1]/'deploy/activate-production.py')
activate=importlib.util.module_from_spec(spec);spec.loader.exec_module(activate)

class ActivationTests(unittest.TestCase):
    def exercise(self,fail):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def mapped(value):
                p=Path(value)
                if p.is_relative_to(root): return p
                return root/str(p).lstrip('/') if p.is_absolute() else p
            real_open=builtins.open
            def mapped_open(value,*a,**kw):
                if str(value)=='/run/lock/starcoaster-deploy.lock': value=mapped(value)
                return real_open(value,*a,**kw)
            rev='a'*40
            base=mapped('/opt/starcoaster')
            old=base/'r/old';old.mkdir(parents=True)
            (base/'current').symlink_to(old)
            bundles=mapped('/var/lib/starcoaster/runtime/wasm-deploy')
            (bundles/'oldbundle').mkdir(parents=True)
            (bundles/'current').symlink_to('oldbundle')
            override=mapped('/etc/systemd/system/starcoaster.service.d/runtime.conf')
            override.parent.mkdir(parents=True);override.write_text('old override')
            env=mapped('/etc/starcoaster/runtime.env')
            env.parent.mkdir(parents=True);env.write_text('LD_LIBRARY_PATH=/old\n')
            mapped('/run/lock').mkdir(parents=True)
            inbox=mapped('/home/cameron/starcoaster-incoming');inbox.mkdir(parents=True)
            files={
                'REVISION':rev.encode(),
                'scripts/run-pi-game.sh':b'#!/bin/bash\n',
                'build/world-bridge':b'bridge',
                'build/wasm-server':b'server',
                'build/openrct2-stage/marker':b'stage',
                'upstream/openrct2/src/openrct2/drawing/ImageImporter.h':b'palette',
                'wasm/manifest.json':b'{}',
            }
            files['SHA256SUMS']=''.join(hashlib.sha256(v).hexdigest()+'  '+k+'\n' for k,v in files.items()).encode()
            with tarfile.open(inbox/(rev+'.tar'),'w') as archive:
                for name,data in files.items():
                    entry=tarfile.TarInfo(name);entry.size=len(data)
                    archive.addfile(entry,io.BytesIO(data))
            calls=[];reads=0
            def http(request,timeout=None):
                nonlocal reads
                if isinstance(request,str):
                    reads+=1
                    state={'phase':'idle' if reads==1 or fail else 'ready','generation':'test','error':'native failed' if fail and reads>1 else ''}
                    return io.BytesIO(json.dumps(state).encode())
                return io.BytesIO(b'{}')
            with patch.object(activate,'Path',mapped), patch.object(activate.os,'geteuid',return_value=0), patch.object(activate.sys,'argv',['activate',rev]), patch.object(builtins,'open',mapped_open), patch.object(activate,'run',side_effect=lambda *a:calls.append(a)), patch.object(activate.time,'sleep'), patch.object(activate.urllib.request,'urlopen',side_effect=http):
                if fail:
                    with self.assertRaisesRegex(RuntimeError,'native failed'): activate.main()
                else: activate.main()
            if fail:
                self.assertEqual((base/'current').resolve(),old)
                self.assertEqual((bundles/'current').readlink(),Path('oldbundle'))
                self.assertEqual(override.read_text(),'old override')
                self.assertEqual(env.read_text(),'LD_LIBRARY_PATH=/old\n')
                self.assertEqual(calls[-1],('systemctl','restart','starcoaster.service'))
            else:
                self.assertEqual((base/'current').resolve(),base/'r'/rev)
                self.assertEqual((base/'previous').resolve(),old)
                self.assertIn(str(base/'r'/rev/'run-data'),override.read_text())
                self.assertIn(str(base/'r'/rev/'build/compat'),env.read_text())
    def test_success_preserves_previous_release(self): self.exercise(False)
    def test_failed_native_start_restores_release_bundle_and_config(self): self.exercise(True)
if __name__=='__main__': unittest.main()
