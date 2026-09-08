"""Reviewed, fixed Pi-only sudoers installation; run via native sudo authentication.

This root helper changes one fixed drop-in, never global sudoers or any command
permission besides tvnner -> root /usr/bin/systemctl poweroff. No wildcards.
"""
from pathlib import Path
import hashlib,json,os,pwd,re,stat,subprocess,sys,tempfile

DIRECTORY=Path('/etc/sudoers.d')
TARGET=DIRECTORY/'fawkes-pi-console-shutdown'
RULE=b'tvnner ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff\n'
SYSTEMCTL_SHA256='c0bf88b71f719b6b92dd22857f0e554ed63c2f0dc35961e36da06fada1aa84a2'

def policy_bytes(operation):
 if not isinstance(operation,str) or not re.fullmatch('[a-f0-9]{64}',operation):raise ValueError('Exact rollout operation required')
 return ('# Fawkes Pi console shutdown; operation '+operation+'\n').encode('ascii')+RULE

def verified_existing(path,policy):
 info=path.lstat()
 if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o440:
  raise PermissionError('Existing Pi shutdown policy identity differs')
 if path.read_bytes()!=policy:raise PermissionError('Existing Pi shutdown policy/operation differs')
 return (info.st_dev,info.st_ino)

def withdraw(policy,expected):
 # First move the pathname atomically into a fresh, private root-owned archive.
 # Never unlink TARGET after a prior check: an administrator may replace it.
 archive=Path(tempfile.mkdtemp(prefix='.fawkes-power-rollback-',dir=DIRECTORY))
 saved=archive/'policy';os.rename(TARGET,saved)
 try:
  if verified_existing(saved,policy)!=expected:raise PermissionError('Policy inode changed')
 except BaseException:
  # Restore the actual moved object only if the public name remains free.
  # If a newer object occupies it, keep BOTH; never overwrite or delete either.
  try:os.link(saved,TARGET,follow_symlinks=False)
  except FileExistsError:pass
  for path in (archive,DIRECTORY):
   fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
   try:os.fsync(fd)
   finally:os.close(fd)
  raise PermissionError('Policy changed during rollback; preserved at '+str(saved))
 fd=os.open(archive,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
 if TARGET.exists() or TARGET.is_symlink():raise PermissionError('Administrator replacement preserved; withdrawn policy at '+str(saved))
 return str(saved)

def verify_platform():
 if os.geteuid()!=0 or pwd.getpwnam('tvnner').pw_uid!=1000:raise PermissionError('Expected authenticated root owner and Pi user')
 if not Path('/proc/device-tree/model').read_bytes().startswith(b'Raspberry Pi 4 Model B Rev 1.5'):
  raise PermissionError('The reviewed Pi model differs')
 info=DIRECTORY.lstat()
 if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise PermissionError('Policy directory is not root-protected')
 binary=Path('/usr/bin/systemctl');info=binary.lstat()
 if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022 or hashlib.sha256(binary.read_bytes()).hexdigest()!=SYSTEMCTL_SHA256:
  raise PermissionError('Reviewed normal shutdown binary changed')

def apply(action,operation):
 if action not in {'install','rollback','verify','verify-absent'}:raise ValueError('Expected bounded policy operation')
 verify_platform()
 policy=policy_bytes(operation);changed=False;archive=None
 if TARGET.exists() or TARGET.is_symlink():
  if action=='verify-absent':raise PermissionError('A policy now exists; absence is not verified')
  expected=verified_existing(TARGET,policy)
  if action=='rollback':archive=withdraw(policy,expected);changed=True
 elif action=='install':
  fd,name=tempfile.mkstemp(prefix='.fawkes-power-',dir=DIRECTORY)
  try:
   with os.fdopen(fd,'wb') as f:os.fchmod(f.fileno(),0o440);f.write(policy);f.flush();os.fsync(f.fileno())
   result=subprocess.run(['/usr/sbin/visudo','-c','-f',name],check=False,capture_output=True,timeout=10)
   if result.returncode:raise ValueError('Fixed shutdown policy did not validate')
   # Exclusive link: a racing administrator's policy must never be overwritten.
   os.link(name,TARGET);changed=True
  finally:os.unlink(name)
 elif action=='verify':raise PermissionError('The installed policy is absent')
 if TARGET.exists():verified_existing(TARGET,policy)
 directory=os.open(DIRECTORY,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(directory)
 finally:os.close(directory)
 return {'action':action,'operation_id':operation,'changed':changed,'path':str(TARGET),'policy_sha256':hashlib.sha256(policy).hexdigest(),'withdrawn_policy_archive':archive,'policy_present':TARGET.exists(),
  'grant':'tvnner -> root: /usr/bin/systemctl poweroff only','shutdown_executed':False}

if __name__=='__main__':
 if len(sys.argv)!=3:raise SystemExit('Expected install/rollback and exact operation ID')
 print(json.dumps(apply(sys.argv[1],sys.argv[2])))
