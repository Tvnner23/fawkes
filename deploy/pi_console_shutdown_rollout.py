"""Exact reviewed Pi companion/policy rollout via Tanner's native SSH session.

Receives a prepared payload in memory, not a password. No shutdown is performed.
The existing PC application/Git/accepted-preview owners remain separate gates.
"""
from pathlib import Path
import base64,fcntl,hashlib,json,math,os,stat,subprocess,tempfile,time

ROOT=Path('/home/tvnner/.local/share/fawkes-pi-console')
OLD_FILES={'supervisor.py','matrix_idle.js','accepted-console.json'}
NEW_FILES=OLD_FILES|{'pi_shutdown_state.py','pi_shutdown_browser.py','pi_console_idle_hold.js','pi_console_power_policy.py'}
def sha(b):return hashlib.sha256(b).hexdigest()
def durable(path,value):
 body=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
 fd,temp=tempfile.mkstemp(prefix='.power-rollout-',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as f:os.fchmod(f.fileno(),0o600);f.write(body);f.flush();os.fsync(f.fileno())
  os.replace(temp,path)
  directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(directory)
  finally:os.close(directory)
 finally:
  if os.path.exists(temp):os.unlink(temp)
 if path.read_bytes()!=body:raise OSError('Rollout state read-back differs')
def decode(value):
 if set(value)!={'base64','sha256','byte_length'}:raise ValueError('Exact file record required')
 body=base64.b64decode(value['base64'],validate=True)
 if len(body)>256000 or len(body)!=value['byte_length'] or sha(body)!=value['sha256']:raise ValueError('Exact postimage differs')
 return body
def validate(payload):
 if set(payload)!={'action','files','preimages','snapshot','commit','acceptance_receipt','policy','linked_install_operation'}:raise ValueError('Exact rollout fields required')
 action=payload['action']
 if action not in {'install','rollback'}:raise ValueError('Unexpected operation')
 expected=NEW_FILES if action=='install' else OLD_FILES
 if set(payload['files'])!=expected or set(payload['preimages'])!=expected:raise ValueError('Unexpected file scope')
 import re
 for key,length in [('commit',40),('acceptance_receipt',64)]:
  if not isinstance(payload[key],str) or not re.fullmatch('[a-f0-9]{'+str(length)+'}',payload[key]):raise ValueError('Invalid subject binding')
 if not re.fullmatch('candidate-snapshot-[a-f0-9]{64}',payload['snapshot']):raise ValueError('Invalid snapshot')
 files={name:decode(value) for name,value in payload['files'].items()}
 if json.loads(files['accepted-console.json'])!={'candidate_snapshot_id':payload['snapshot']}:raise ValueError('Pi marker differs')
 policy=decode(payload['policy'])
 if action=='install' and policy!=files['pi_console_power_policy.py']:raise ValueError('Root helper differs from accepted product')
 if action=='rollback' and not re.fullmatch('[a-f0-9]{64}',payload['linked_install_operation'] or ''):raise ValueError('Rollback requires exact install lineage')
 return files,policy
def policy_action(source,action,operation):
 # The root helper has one fixed path/rule and checks the actual inspected Pi.
 r=subprocess.run(['/usr/bin/sudo','-n','/usr/bin/python3','-c',source.decode('utf-8'),action,operation],capture_output=True,text=True,timeout=20)
 if r.returncode:raise PermissionError('Fixed Pi power-policy operation failed; native sudo authentication may be required')
 value=json.loads(r.stdout)
 if value.get('action')!=action or value.get('operation_id')!=operation or value.get('shutdown_executed') is not False:raise ValueError('Power policy return differs')
 return value
def preimages(files,payload):
 for name,body in files.items():
  path=ROOT/name
  if path.is_symlink():raise ValueError('Symlink companion target refused')
  if path.exists():
   info=path.stat()
   if not stat.S_ISREG(info.st_mode) or info.st_uid!=1000 or info.st_mode&0o022:raise ValueError('Unexpected companion file owner/mode')
   if sha(path.read_bytes()) not in {payload['preimages'][name],sha(body)}:raise ValueError('Companion preimage changed: '+name)
  elif payload['preimages'][name] is not None:raise ValueError('Required companion preimage missing')
def write_file(path,body):
 mode=stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
 fd,temp=tempfile.mkstemp(prefix='.accepted-power-',dir=ROOT)
 try:
  with os.fdopen(fd,'wb') as f:os.fchmod(f.fileno(),mode);f.write(body);f.flush();os.fsync(f.fileno())
  os.replace(temp,path)
 finally:
  if os.path.exists(temp):os.unlink(temp)
 if path.read_bytes()!=body:raise OSError('Installed file read-back differs')
def ready(snapshot,not_before,env):
 status_path=Path(env['XDG_RUNTIME_DIR'])/'fawkes-pi-console/status.json';observed={}
 for _ in range(45):
  try:observed=json.loads(status_path.read_text())
  except (OSError,ValueError):pass
  stamp=observed.get('time')
  if (observed.get('state')=='READY' and type(stamp) in (int,float) and math.isfinite(stamp)
      and not_before<=stamp<=time.time()+2 and observed.get('browser_observation')=={
      'origin':'http://127.0.0.1:8791','path':'/dev-console','context':'ACCEPTED:'+snapshot,'projection':'live'}):return observed
  time.sleep(2)
 raise RuntimeError('No fresh exact Pi browser observation; retain rollback journal')
def run(payload):
 os.umask(0o077)
 if os.getuid()!=1000 or not Path('/proc/device-tree/model').read_bytes().startswith(b'Raspberry Pi 4 Model B Rev 1.5'):
  raise PermissionError('Expected authenticated ordinary Pi user/model')
 files,policy=validate(payload)
 if ROOT.is_symlink() or not ROOT.is_dir() or ROOT.stat().st_uid!=1000:raise PermissionError('Companion installation owner differs')
 operation=sha(json.dumps(payload,sort_keys=True,separators=(',',':')).encode())
 journal_path=ROOT/('power-rollout-'+operation+'.json')
 lock=os.open(ROOT/'power-rollout.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 try:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if journal_path.exists():
   old=json.loads(journal_path.read_text())
   if old.get('state')!='completed':raise RuntimeError('Prior interrupted rollout requires explicit journal reconciliation, not replay')
   preimages(files,payload)
   if any((ROOT/name).read_bytes()!=body for name,body in files.items()):raise RuntimeError('Completed rollout no longer matches')
   # Reconcile current root-owned policy, not the old journal's success. This
   # is read-only and may need native sudo authentication again after its cache
   # expires; it never reinstalls a missing/changed policy or restarts services.
   subprocess.run(['/usr/bin/sudo','-v','-p','Pi sudo password (native terminal only):\n'],check=True,timeout=180)
   mode='verify' if payload['action']=='install' else 'verify-absent'
   policy_now=policy_action(policy,mode,operation if payload['action']=='install' else payload['linked_install_operation'])
   env={**os.environ,'XDG_RUNTIME_DIR':'/run/user/1000','DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus'}
   observed=ready(payload['snapshot'],time.time()-10,env)
   active=subprocess.run(['/usr/bin/systemctl','--user','is-active','--quiet','fawkes-pi-console.service'],env=env,timeout=10).returncode==0
   if not active:raise RuntimeError('Previously completed rollout is not currently active')
   return {**old['result'],'companion_observation':observed,'service_active':True,'policy_result':policy_now,'duplicate_reconciled_without_restart':True}
  preimages(files,payload)
  backup=ROOT/('accepted-power-backup-'+time.strftime('%Y%m%dT%H%M%S')+'-'+operation[:12]);backup.mkdir(mode=0o700)
  for name in files:
   p=ROOT/name
   if p.exists():
    import shutil
    shutil.copy2(p,backup/name)
  journal={'operation_id':operation,'state':'prepared','action':payload['action'],'snapshot':payload['snapshot'],
   'commit':payload['commit'],'acceptance_receipt':payload['acceptance_receipt'],'backup':str(backup),
   'prior_files':{name:sha((ROOT/name).read_bytes()) if (ROOT/name).exists() else None for name in files},'policy_created':False}
  durable(journal_path,journal)
  try:
   if payload['action']=='install':
    # Password is entered only at the remote native tty. It is never read by
    # Python, supplied in a URL/argument or retained in our evidence.
    subprocess.run(['/usr/bin/sudo','-v','-p','Pi sudo password (native terminal only):\n'],check=True,timeout=180)
    result=policy_action(policy,'install',operation);journal['policy_created']=result['changed'];journal['policy_result']=result
    durable(journal_path,journal)
   else:
    linked=ROOT/('power-rollout-'+payload['linked_install_operation']+'.json')
    if linked.is_symlink() or not linked.exists():raise ValueError('Missing exact install journal')
    prior=json.loads(linked.read_text())
    if prior.get('action')!='install' or prior.get('operation_id')!=payload['linked_install_operation']:raise ValueError('Install lineage differs')
    # The policy itself is tagged with this exact operation. A crash after
    # its creation but before journaling must not leave an untracked grant;
    # remove only the matching bytes/tag, without inventing a prior receipt.
    subprocess.run(['/usr/bin/sudo','-v','-p','Pi sudo password (native terminal only):\n'],check=True,timeout=180)
    journal['policy_result']=policy_action(policy,'rollback',payload['linked_install_operation']);durable(journal_path,journal)
   for name,body in files.items():write_file(ROOT/name,body)
   directory=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY)
   try:os.fsync(directory)
   finally:os.close(directory)
   journal['state']='files_installed';durable(journal_path,journal)
   env={**os.environ,'XDG_RUNTIME_DIR':'/run/user/1000','DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus'}
   not_before=math.ceil(time.time())
   subprocess.run(['/usr/bin/systemctl','--user','restart','fawkes-pi-console.service'],env=env,check=True,timeout=20)
   observation=ready(payload['snapshot'],not_before,env)
   active=subprocess.run(['/usr/bin/systemctl','--user','is-active','--quiet','fawkes-pi-console.service'],env=env).returncode==0
   if not active:raise RuntimeError('Pi companion not active')
   result={'snapshot':payload['snapshot'],'commit':payload['commit'],'acceptance_receipt':payload['acceptance_receipt'],
    'operation_id':operation,'installed_files':{name:sha((ROOT/name).read_bytes()) for name in files},'service_active':active,
    'fresh_accepted_ready':True,'companion_observation':observation,'rollback_directory':str(backup),'policy_result':journal.get('policy_result'),
    'actual_physical_shutdown_verified':False,'provider_calls':0,'credential_retained':False,'pc_shutdown_requested':False,'shutdown_requested':False}
   journal.update(state='completed',result=result);durable(journal_path,journal)
   return result
  except BaseException as error:
   journal.update(state='failed_retained_for_reconciliation',failure_type=type(error).__name__)
   durable(journal_path,journal)
   raise
 finally:os.close(lock)
