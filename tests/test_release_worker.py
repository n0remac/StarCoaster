"""Exercise canonical Git selection, gates, and idempotence with real local repos."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ReleaseWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.origin=self.root/'github';self.origin.mkdir()
        self.builder=self.root/'builder'
        self.trace=self.root/'trace'
        self.deployed=self.root/'deployed'
        self.git(self.origin,'init','-b','main')
        self.git(self.origin,'config','user.name','Release test')
        self.git(self.origin,'config','user.email','release@example.invalid')
        self.write('.gitignore','/run-data/\n/build/\n/upstream/\n')
        self.write('scripts/update-pi-game.sh',(ROOT/'scripts/update-pi-game.sh').read_text(),True)
        self.write('scripts/fetch-upstream.py','pass\n')
        self.write('scripts/test-release-candidate.py','import os,sys;sys.exit(9 if os.environ.get("TEST_BROWSER_FAIL")=="1" else 0)\n')
        self.write('scripts/install-openrct2-local.sh','#!/bin/bash\nexit 0\n',True)
        self.write('scripts/project.sh',"""#!/bin/bash
echo "$1" >> "$TEST_TRACE"
if [[ "$1" == test && "${TEST_FAIL:-0}" == 1 ]]; then exit 9; fi
exit 0
""",True)
        self.write('scripts/deploy-production.sh',"""#!/bin/bash
case "${1:-}" in
 --status) cat "$TEST_DEPLOYED";;
 --check) exit 0;;
 *) git rev-parse HEAD > "$TEST_DEPLOYED"; echo deploy >> "$TEST_TRACE";;
esac
""",True)
        self.git(self.origin,'add','.')
        self.git(self.origin,'commit','-m','initial')
        self.git(self.root,'clone',str(self.origin),str(self.builder))
        self.write('app.txt','new committed application\n')
        self.git(self.origin,'add','app.txt')
        self.git(self.origin,'commit','-m','release')
        self.revision=self.git(self.origin,'rev-parse','HEAD').strip()
        self.env=dict(os.environ,GO_BIN='/bin/true',TEST_TRACE=str(self.trace),
                      TEST_DEPLOYED=str(self.deployed),
                      STARCOASTER_PUSH_REPO=str(self.root/'untrusted-local-receiver'))
    def git(self,cwd,*args):
        return subprocess.check_output(['git',*args],cwd=cwd,text=True,stderr=subprocess.DEVNULL)
    def write(self,name,text,executable=False):
        p=self.origin/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        if executable:p.chmod(0o755)
    def run_worker(self,**env):
        return subprocess.run(['bash','scripts/update-pi-game.sh','--from-push'],cwd=self.builder,
            env=dict(self.env,**env),capture_output=True,text=True,timeout=30)
    def state(self):
        return json.loads((self.builder/'run-data/deployment-status.json').read_text())
    def test_uses_github_revision_even_with_local_push_argument(self):
        result=self.run_worker()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(self.deployed.read_text().strip(),self.revision)
        self.assertEqual(self.state()['status'],'succeeded')
        self.assertEqual(self.trace.read_text().splitlines()[-3:],['test','test-wasm','deploy'])
    def test_failed_tests_never_activate_and_can_retry(self):
        result=self.run_worker(TEST_FAIL='1')
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(self.deployed.exists())
        self.assertEqual(self.state()['status'],'failed')
        self.assertEqual(self.state()['stage'],'tests')
        result=self.run_worker(TEST_FAIL='0')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(self.deployed.read_text().strip(),self.revision)
    def test_failed_browser_gameplay_never_activates(self):
        result=self.run_worker(TEST_BROWSER_FAIL='1')
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(self.deployed.exists())
        self.assertEqual(self.state()['stage'],'browser-gameplay')
        self.assertEqual(self.state()['status'],'failed')
    def test_checks_actual_production_without_rebuilding(self):
        self.deployed.write_text(self.revision+'\n')
        result=self.run_worker()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse(self.trace.exists())
        self.assertEqual(self.state()['stage'],'complete')

if __name__=='__main__':unittest.main()
