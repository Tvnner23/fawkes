"""Bounded private Pi state and the companion's one fixed shutdown operation.

No HTTP listener, credential store or arbitrary shell command. Companion calls
this only for its own main-frame local hold intent. Never run it on the PC.
"""
from pathlib import Path
import fcntl,hashlib,json,os,re,stat,subprocess,tempfile,time

KEYS=frozenset({'fawkes-worker-page-v1','fawkes-console-update-retry-v1',
                'fawkes-native-worker-selection-v1','fawkes-worker-notice-baseline-v1','fawkes-objective-notices-v1'})
MAX_BYTES=192000
UUID=re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$')
THREAD='01a06f22-5b47-72c1-9b9c-b70157913436'
class SaveError(Exception):pass

def strict_json(text):
 def pairs(rows):
  result={}
  for key,value in rows:
   if key in result:raise SaveError('Duplicate stored field')
   result[key]=value
  return result
 try:return json.loads(text,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(SaveError('Non-finite stored value')))
 except (ValueError,TypeError) as error:raise SaveError('Malformed stored JSON') from error

def text(value,maximum=512,*,empty=False):
 return isinstance(value,str) and (empty or bool(value)) and len(value.encode('utf-8'))<=maximum and '\0' not in value
def fields(value,required,optional=()):
 return isinstance(value,dict) and set(required)<=set(value)<=set(required)|set(optional)
def hex64(value):return isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None
def notice_key(value,worker_only=False):
 if not text(value,4096):return False
 v=strict_json(value)
 if not isinstance(v,list):return False
 if len(v)==4:return v[0]==THREAD and text(v[1]) and text(v[2]) and hex64(v[3])
 if worker_only or len(v)!=3 or not text(v[0]) or v[1] not in {'needs_you','complete'}:return False
 return (v[2] is None or hex64(v[2])) if v[1]=='needs_you' else text(v[2])
def validate_storage(key,body):
 v=strict_json(body);valid=False
 if key=='fawkes-worker-page-v1':
  valid=fields(v,['draft'],['pendingReply','pendingCopy']) and isinstance(v['draft'],str)
  if valid and v.get('pendingReply') is not None:
   p=v['pendingReply'];valid=fields(p,['thread_id','reply_id','text']) and p['thread_id']==THREAD and isinstance(p['reply_id'],str) and UUID.fullmatch(p['reply_id']) and text(p['text'],16000)
  if valid and v.get('pendingCopy') is not None:
   p=v['pendingCopy'];valid=fields(p,['thread_id','message_id','content_sha256','idempotency_key']) and p['thread_id']==THREAD and text(p['message_id']) and hex64(p['content_sha256']) and isinstance(p['idempotency_key'],str) and p['idempotency_key'].startswith('worker-final-') and UUID.fullmatch(p['idempotency_key'][13:])
 elif key=='fawkes-native-worker-selection-v1':
  valid=fields(v,['thread_id','request_key','action_sha256','choice_id','submission_id']) and v['thread_id']==THREAD and all(hex64(v[k]) for k in ['request_key','action_sha256','choice_id']) and isinstance(v['submission_id'],str) and UUID.fullmatch(v['submission_id'])
 elif key=='fawkes-console-update-retry-v1':
  valid=fields(v,['key','campaign_id']) and text(v['key'],256) and re.fullmatch('console-browser-[A-Za-z0-9_.:-]+',v['key']) and (v['campaign_id'] is None or text(v['campaign_id']))
 elif key=='fawkes-worker-notice-baseline-v1':
  valid=fields(v,['thread','key']) and v['thread']==THREAD and (v['key'] is None or notice_key(v['key'],True))
 elif key=='fawkes-objective-notices-v1':
  valid=isinstance(v,list) and len(v)<=128 and all(notice_key(k) for k in v)
 if not valid:raise SaveError('Stored structure or Worker identity differs: '+key)

def pi_identity():
 model=Path('/proc/device-tree/model').read_bytes().rstrip(b'\0')
 if not model.startswith(b'Raspberry Pi '):raise SaveError('Shutdown is available only on the Pi')
 boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
 if not re.fullmatch(r'[a-f0-9-]{36}',boot):raise SaveError('Pi boot identity unavailable')
 return boot

def normalized(value):
 if not isinstance(value,dict) or set(value)!={'storage','page','scroll'}:raise SaveError('Invalid console state')
 storage=value['storage']
 if not isinstance(storage,dict) or not set(storage)<=KEYS:raise SaveError('Unapproved storage key')
 if any(not isinstance(v,str) for v in storage.values()):raise SaveError('Invalid storage value')
 for key,body in storage.items():validate_storage(key,body)
 if not isinstance(value['page'],str) or value['page'] not in {'0','1','2','3','4','unknown'}:raise SaveError('Invalid page')
 scroll=value['scroll']
 if not isinstance(scroll,dict) or not set(scroll)<={'console','worker'}:raise SaveError('Invalid scroll state')
 if any(type(v) not in (int,float) or not 0<=v<=10000000 for v in scroll.values()):raise SaveError('Invalid scroll offset')
 body=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
 if len(body)>MAX_BYTES:raise SaveError('Console state exceeds save limit')
 return value

class LocalShutdown:
 def __init__(self,root,*,runner=subprocess.run,identity=pi_identity):
  self.root=Path(root);self.runner=runner;self.identity=identity
  self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
  info=self.root.lstat()
  if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:raise SaveError('Private state directory required')
  self.saved=self.root/'console-state.json';self.intent=self.root/'shutdown-intent.json'
  self.requests=self.root/'requests';self.requests.mkdir(mode=0o700,exist_ok=True)
  info=self.requests.lstat()
  if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:raise SaveError('Private request directory required')
 def durable(self,path,value):
  body=(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n').encode()
  if len(body)>MAX_BYTES+4096:raise SaveError('Record too large')
  fd,name=tempfile.mkstemp(prefix='.save-',dir=path.parent)
  try:
   with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
   os.replace(name,path)
   directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
   try:os.fsync(directory)
   finally:os.close(directory)
  finally:
   if os.path.exists(name):os.unlink(name)
  if path.read_bytes()!=body:raise SaveError('State read-back differs')
 def save(self,value,thread_id):
  value=normalized(value)
  if thread_id!=THREAD:raise SaveError('Invalid conversation binding')
  self.durable(self.saved,{'version':1,'thread_id':thread_id,'saved_at':time.time(),'state':value})
 def restore(self,thread_id):
  if not self.saved.exists():return None
  if self.saved.is_symlink() or self.saved.stat().st_size>MAX_BYTES+4096:raise SaveError('Invalid saved state')
  value=strict_json(self.saved.read_text())
  if value.get('version')!=1 or value.get('thread_id')!=thread_id:raise SaveError('Saved conversation differs')
  return normalized(value['state'])
 def shutdown(self,request_id,value,thread_id):
  if not isinstance(request_id,str) or not UUID.fullmatch(request_id):raise SaveError('Invalid local hold identity')
  lock_path=self.root/'shutdown.lock'
  fd=os.open(lock_path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
  try:
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   return self._shutdown(request_id,value,thread_id)
  finally:os.close(fd)
 def _shutdown(self,request_id,value,thread_id):
  boot=self.identity() # A Linux/Windows PC must never run the power command.
  request=self.requests/(request_id+'.json')
  if request.exists() or request.is_symlink():raise SaveError('This hold was already consumed')
  if self.intent.exists():
   if self.intent.is_symlink() or self.intent.stat().st_size>4096:raise SaveError('Invalid prior shutdown record')
   old=json.loads(self.intent.read_text())
   if old.get('boot_id')==boot and old.get('state') in {'requesting','requested'}:raise SaveError('Shutdown already requested; no replay')
  self.save(value,thread_id)
  record={'request_id':request_id,'boot_id':boot,'state':'requesting','created_at':time.time(),'state_sha256':hashlib.sha256(self.saved.read_bytes()).hexdigest()}
  self.durable(request,record)
  self.durable(self.intent,record)
  try:
   result=self.runner(['/usr/bin/sudo','-n','/usr/bin/systemctl','poweroff'],check=False,capture_output=True,timeout=10)
  except (OSError,subprocess.TimeoutExpired):
   # Ambiguous command outcome must not be retried automatically.
   return {'state':'unknown','message':'Shutdown request outcome is unknown; do not retry automatically.'}
  if result.returncode:
   try:
    self.durable(request,{**record,'state':'failed','returncode':result.returncode})
    self.durable(self.intent,{**record,'state':'failed','returncode':result.returncode})
   except (OSError,SaveError):return {'state':'unknown','message':'Shutdown command returned an error; its result could not be saved. Do not retry automatically.'}
   return {'state':'failed','message':'Pi shutdown was not accepted. Your draft was saved.'}
  try:
   self.durable(request,{**record,'state':'requested','acknowledged_at':time.time()})
   self.durable(self.intent,{**record,'state':'requested','acknowledged_at':time.time()})
  except (OSError,SaveError):return {'state':'unknown','message':'Shutdown was requested; final status could not be saved.'}
  return {'state':'requested','message':'Shutting down…'}
