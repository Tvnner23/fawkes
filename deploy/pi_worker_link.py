"""Pinned same-thread startup, no prompt or automatic permission decision.

Installed only through the exact accepted rollout. The server may start empty;
the native terminal owns resume. An existing standalone owner is never stopped.
"""
from pathlib import Path
import fcntl,hashlib,json,os,socket,stat,struct,subprocess,sys,time

THREAD='01a06f22-5b47-72c1-9b9c-b70157913436'
REPO=Path('/home/tvnner/fawkes')
REC=Path('/home/tvnner/.local/state/fawkes/console-preview-recovery-20260909')
ROOT=Path('/home/tvnner/.local/share/fawkes-worker-link')
SOCKET=Path('/home/tvnner/.codex/app-server-control/app-server-control.sock')
EXE=Path('/usr/local/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex')
SHA='56ef98ab4032d317ab26e9b5e5a175650717351edb16ed9cde0cb6d1734d62da'
UNIT='fawkes-console-worker-app-server.service'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def private_dir(p):
 s=p.lstat()
 if not stat.S_ISDIR(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)&0o077:
  raise PermissionError('Worker control directory must remain private')
def lock_file(path):
 fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 s=os.fstat(fd)
 if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)&0o077:
  os.close(fd);raise PermissionError('Worker lock ownership differs')
 try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BaseException:os.close(fd);raise
 return fd
def validate_binding(v):
 import re
 if not isinstance(v,dict) or set(v)!={'commit','snapshot','receipt','files','thread_id','model','effort'} or (v['thread_id'],v['model'],v['effort'])!=(THREAD,'gpt-6-astra','xhigh'):raise PermissionError('Worker identity/model binding differs')
 for key,pattern in [('commit','[a-f0-9]{40}'),('snapshot','candidate-snapshot-[a-f0-9]{64}'),('receipt','[a-f0-9]{64}')]:
  if not isinstance(v[key],str) or not re.fullmatch(pattern,v[key]):raise PermissionError('Missing accepted subject')
 if not isinstance(v['files'],dict) or set(v['files'])!={'pi_worker_link.py','fawkes-console-worker-app-server.service','Run-Fawkes-Worker.ps1','Install-Fawkes-Worker-Startup.ps1'}:raise PermissionError('Unexpected startup files')
 if any(not isinstance(d,str) or not re.fullmatch('[a-f0-9]{64}',d) for d in v['files'].values()):raise PermissionError('Invalid startup digest')
def private_file(p):
 s=p.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)&0o077:raise PermissionError('Worker file ownership/mode differs')
def verified_binding():
 private_dir(ROOT)
 p=ROOT/'accepted-binding.json';s=p.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)&0o077:raise PermissionError('Worker adoption binding differs')
 v=json.loads(p.read_text())
 validate_binding(v)
 for name,digest in v['files'].items():
  p=ROOT/name
  private_file(p)
  if sha(p)!=digest:raise PermissionError('Accepted startup bytes changed')
 if sha(EXE)!=SHA:raise PermissionError('Installed Codex executable changed')
 return v
def same_thread_owners(proc=Path('/proc')):
 found=[]
 for p in proc.iterdir():
  if not p.name.isdigit():continue
  try:args=(p/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
  except (OSError,PermissionError):continue
  if THREAD.encode() in args and any(b'codex' in a for a in args[:3]):found.append(int(p.name))
 return found
def server_args():return [str(EXE),'app-server','--listen','unix://'+str(SOCKET)]
def archive_stale_socket(path=SOCKET):
 """Called with the old handover lock by the exclusive systemd service start."""
 private_dir(path.parent)
 try:node=path.lstat()
 except FileNotFoundError:return None
 if not stat.S_ISSOCK(node.st_mode) or node.st_uid!=os.getuid():raise PermissionError('Unexpected socket node; preserved')
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
  s.settimeout(1)
  try:s.connect(str(path))
  except ConnectionRefusedError:pass
  else:raise PermissionError('A live socket owner exists; no second server')
 current=path.lstat()
 if (current.st_dev,current.st_ino,current.st_mode,current.st_uid)!=(node.st_dev,node.st_ino,node.st_mode,node.st_uid):raise PermissionError('Socket changed during reconciliation')
 destination=path.with_name('stale-'+str(node.st_ino)+'-'+str(time.time_ns())+'.sock')
 os.rename(path,destination)
 if destination.lstat().st_ino!=node.st_ino:raise PermissionError('Socket archive changed; stop for reconciliation')
 return destination
def verify_server():
 private_dir(SOCKET.parent)
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
  peer.settimeout(2);peer.connect(str(SOCKET))
  pid,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
  owner=subprocess.check_output(['systemctl','--user','show',UNIT,'--property=MainPID','--value'],timeout=5).decode().strip()
  if uid!=os.getuid() or str(pid)!=owner or sha(Path(f'/proc/{pid}/exe'))!=SHA:raise PermissionError('Unexpected Worker server owner')
  if Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').split(b'\0')!=[a.encode() for a in server_args()]:raise PermissionError('Worker server arguments differ')
 return pid
def remote_args():
 return [str(EXE),'resume',THREAD,'--remote','unix://'+str(SOCKET),'--cd',str(REPO),
  '--sandbox','workspace-write','--ask-for-approval','on-request','--add-dir',str(REC),
  '--model','gpt-6-astra','-c','model_reasoning_effort="xhigh"']
def main():
 verified_binding()
 if sys.argv[1:] == ['server']:
  SOCKET.parent.mkdir(mode=0o700,exist_ok=True);private_dir(SOCKET.parent)
  fd=lock_file(SOCKET.parent/'fawkes-handover.lock')
  archive_stale_socket()
  # Keep the startup lock until exec; FD_CLOEXEC releases it in the pinned
  # server process. systemd owns that process and its bounded restart policy.
  os.execv(str(EXE),server_args())
 elif sys.argv[1:] == ['attach']:
  if not sys.stdin.isatty() or not sys.stdout.isatty():raise PermissionError('Use the native interactive Worker terminal')
  fd=lock_file(ROOT/'client.lock')
  if same_thread_owners():os.close(fd);return 75
  subprocess.run(['systemctl','--user','start',UNIT],check=True,timeout=20)
  deadline=time.monotonic()+20
  while True:
   try:verify_server();break
   except (OSError,subprocess.SubprocessError):
    if time.monotonic()>=deadline:raise
    time.sleep(.2)
  if same_thread_owners():os.close(fd);return 75
  os.set_inheritable(fd,True)
  os.execv(str(EXE),remote_args())
 else:raise ValueError('server|attach only')
if __name__=='__main__':
 try:sys.exit(main() or 0)
 except (PermissionError,ValueError):
  print('Worker startup binding/ownership needs reconciliation; no thread or prompt was started.',file=sys.stderr);sys.exit(78)
