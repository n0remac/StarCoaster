#!/usr/bin/env python3
"""Exercise normal browser gameplay against an isolated release candidate."""
import json,os,signal,socket,subprocess,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
artifacts=ROOT/'build/release-browser'
artifacts.mkdir(parents=True,exist_ok=True)
ports=[18095,11853,41110,41111,41112]
for port in ports:
 with socket.socket() as sock: sock.bind(('127.0.0.1',port))
env=dict(os.environ,RCT2_DATA_DIR=os.environ.get('RCT2_DATA_DIR','/home/pi/games/rct2'),
 STARCRAFT_DATA_DIR=os.environ.get('STARCRAFT_DATA_DIR','/home/pi/games/starcraft'),
 WASM_LISTEN_ADDRESS='127.0.0.1:18095',OPENRCT2_PORT='11853',
 STARCOASTER_BRIDGE_PORT='41110',BRIDGE_OPENBW_PORT='41111',BRIDGE_CONTROLLER_PORT='41112',
 BRIDGE_LAUNCH_CLIENT='0',WASM_LIVE_URL='http://127.0.0.1:18095/',
 WASM_LIVE_PROFILE=str(ROOT/'build/release-browser-profile'),
 WASM_PERF_ARTIFACTS=str(artifacts),WASM_NORMAL_HANDOFF='1',WASM_HANDOFF_ALLOW_READY='1',
 WASM_LIVE_CAMERA='1',WASM_AUTO_ORDER='1',WASM_DEFENSE_CONFIGURE='1',
 WASM_DEFENSE_BUILD='1',WASM_DEFENSE_NO_WAVE='1',
 WASM_LIVE_BOOT_TIMEOUT_MS='600000',WASM_LIVE_DURATION_MS='30000')
subprocess.run(['bash','scripts/deploy-wasm.sh'],env=env,check=True)
with (artifacts/'supervisor.log').open('w') as log:
 host=subprocess.Popen(['bash','scripts/run-pi-game.sh'],env=env,stdout=log,
                       stderr=subprocess.STDOUT,start_new_session=True)
 try:
  for _ in range(60):
   if host.poll() is not None: raise RuntimeError('Candidate host exited; inspect supervisor.log')
   try:
    with urllib.request.urlopen(env['WASM_LIVE_URL']+'private/park-session',timeout=2) as r:
     json.load(r)
    break
   except Exception:time.sleep(1)
  else:raise RuntimeError('Candidate HTTP startup timed out')
  subprocess.run(['node','browser/live-test.mjs'],env=env,check=True,timeout=1200)
  report=json.loads((artifacts/'runtime.json').read_text())
  assert report['outcome']=='passed',report['outcome']
  assert report['metrics'].get('actorMoveLatencyMs') is not None
  assert report['metrics']['websocketFramesOut']>0
  print('Release candidate passed browser construction, training, and movement')
 finally:
  if host.poll() is None:
   host.send_signal(signal.SIGTERM)
   try:host.wait(timeout=360)
   except subprocess.TimeoutExpired:
    os.killpg(host.pid,signal.SIGKILL);host.wait()
