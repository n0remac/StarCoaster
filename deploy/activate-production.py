#!/usr/bin/python3
"""Root-owned, fixed-target release activation. Installed by the administrator."""
import hashlib,json,os,re,shutil,subprocess,sys,tarfile,time,urllib.request
from pathlib import Path,PurePosixPath
def run(*a): subprocess.run(a,check=True)
def unpack(incoming,temp):
 with tarfile.open(incoming,'r:') as archive:
  total=0
  for member in archive:
   name=PurePosixPath(member.name)
   if name.is_absolute() or '..' in name.parts or not (member.isdir() or member.isfile()):
    raise ValueError('Archive must contain only relative regular files and directories')
   dst=temp.joinpath(*name.parts)
   if member.isdir(): dst.mkdir(parents=True,exist_ok=True);continue
   total+=member.size
   if total>8*1024**3: raise ValueError('Release exceeds 8 GiB')
   dst.parent.mkdir(parents=True,exist_ok=True)
   with archive.extractfile(member) as src, dst.open('xb') as out: shutil.copyfileobj(src,out)
   dst.chmod(0o755 if member.mode & 0o111 else 0o644)

def main():
 if os.geteuid()!=0: raise SystemExit('Run through the installed sudo rule')
 if sys.argv[1:]==['--check']:
  print('Production activator ready');sys.exit(0)
 if len(sys.argv)!=2 or not re.fullmatch('[0-9a-f]{40}',sys.argv[1]): raise SystemExit('Expected full Git revision')
 rev=sys.argv[1]
 import fcntl
 with open('/run/lock/starcoaster-deploy.lock','w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  base=Path('/opt/starcoaster')
  release=base/'r'/rev
  if release.exists(): raise SystemExit('Release exists; refusing to overwrite')
  incoming=Path('/home/cameron/starcoaster-incoming')/(rev+'.tar')
  temp=base/'r'/('.staging-'+rev)
  temp.mkdir(mode=0o700)
  try:
   unpack(incoming,temp)
   if (temp/'REVISION').read_text().strip()!=rev: raise ValueError('Revision mismatch')
   for line in (temp/'SHA256SUMS').read_text().splitlines():
    digest,name=line.split('  ',1)
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts: raise ValueError('Unsafe manifest path')
    with (temp/name).open('rb') as stream:
     actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=digest:
     raise ValueError('Release checksum mismatch: '+name)
   for required in ['scripts/run-pi-game.sh','build/world-bridge','build/wasm-server',
                    'upstream/openrct2/src/openrct2/drawing/ImageImporter.h','wasm/manifest.json']:
    if not (temp/required).is_file(): raise ValueError('Missing '+required)
   for directory,_,_ in os.walk(temp): Path(directory).chmod(0o755)
   (temp/'run-data').mkdir(exist_ok=True)
   temp.rename(release)
  except BaseException:
   shutil.rmtree(temp,ignore_errors=True);raise
  runtime=Path('/var/lib/starcoaster/runtime')
  bundles=runtime/'wasm-deploy'
  bundle=hashlib.sha256((release/'wasm/manifest.json').read_bytes()).hexdigest()[:16]
  bundle_dir=bundles/bundle
  if not bundle_dir.exists():
   shutil.copytree(release/'wasm',bundle_dir)
   run('chown','-R','starcoaster:starcoaster',str(bundle_dir))
  run('chown','-R','starcoaster:starcoaster',str(release/'build/openrct2-stage'))
  current=base/'current'
  previous=current.resolve()
  bundle_link=bundles/'current'
  previous_bundle=os.readlink(bundle_link)
  override=Path('/etc/systemd/system/starcoaster.service.d/runtime.conf')
  old_override=override.read_text()
  def select(link,target):
   tmp=link.with_name(link.name+'.next')
   tmp.unlink(missing_ok=True);tmp.symlink_to(target);tmp.replace(link)
  def state():
   return json.load(urllib.request.urlopen('http://127.0.0.1:8091/private/park-session',timeout=5))
  def post(action,payload):
   req=urllib.request.Request('http://127.0.0.1:8091/private/park-session/'+action,
    data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:8091'})
   urllib.request.urlopen(req,timeout=10).close()
  try:
   run('systemctl','stop','starcoaster.service')
   select(current,release);select(bundle_link,bundle)
   override.write_text('[Service]\nBindPaths=\nBindPaths='+str(runtime)+':'+str(release/'run-data')+
    '\nReadWritePaths=\nReadWritePaths=/var/lib/starcoaster'+' '+str(release/'run-data')+' '+str(release/'build/openrct2-stage')+
    '\nEnvironment="LD_LIBRARY_PATH='+str(release/'build/compat')+':'+str(release/'build/bwapi/lib')+'"\n')
   # EnvironmentFile values override Environment directives; update its fixed library path too.
   env=Path('/etc/starcoaster/runtime.env')
   old_env=env.read_text()
   env.write_text(re.sub(r'^LD_LIBRARY_PATH=.*$', 'LD_LIBRARY_PATH='+str(release/'build/compat')+':'+str(release/'build/bwapi/lib'),old_env,flags=re.M))
   run('systemctl','daemon-reload');run('systemctl','start','starcoaster.service')
   for _ in range(30):
    try: s=state();break
    except Exception: time.sleep(1)
   else: raise RuntimeError('HTTP health check failed')
   post('load',{'park':'Electric Fields.SC6','generation':s['generation'],'decision':'discard'})
   for _ in range(150):
    time.sleep(2);s=state()
    if s.get('error'): raise RuntimeError(s['error'])
    if s['phase']=='ready': break
   else: raise RuntimeError('Native startup timed out')
   time.sleep(10)
   if state()['phase']!='ready': raise RuntimeError('Native session did not stay ready')
   post('title',{'generation':s['generation'],'decision':'discard'})
   (base/'previous').unlink(missing_ok=True);(base/'previous').symlink_to(previous)
   print('Production release activated and native startup passed:',rev)
  except BaseException:
   select(current,previous);select(bundle_link,previous_bundle);override.write_text(old_override)
   if 'old_env' in locals(): env.write_text(old_env)
   run('systemctl','daemon-reload');run('systemctl','restart','starcoaster.service')
   print('Activation failed; previous release restored',file=sys.stderr)
   raise

if __name__=='__main__': main()
