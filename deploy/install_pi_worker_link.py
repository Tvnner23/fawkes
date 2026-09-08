"""Install only a preaccepted exact private Worker startup bundle, no resume.

The task-local canonical adoption entry validates the actual acceptance receipt
and integrated source before calling this installer. This does not create one.
"""
from pathlib import Path
import hashlib,json,os,stat,subprocess,tempfile
from pi_worker_link import ROOT,THREAD,UNIT,EXE,SHA,private_dir,private_file,lock_file,validate_binding
FILES=('pi_worker_link.py','fawkes-console-worker-app-server.service','Run-Fawkes-Worker.ps1','Install-Fawkes-Worker-Startup.ps1')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def effective_unit(unit_path,allow_missing=False):
 props=subprocess.check_output(['systemctl','--user','show',UNIT,'--property=LoadState','--property=ActiveState','--property=FragmentPath','--property=DropInPaths','--property=ExecStart'],timeout=5).decode()
 values=dict(line.split('=',1) for line in props.splitlines() if '=' in line)
 if values.get('DropInPaths')!='':raise PermissionError('Unreviewed or unknown effective unit overrides; preserved')
 if allow_missing and values.get('LoadState')=='not-found' and values.get('ActiveState')=='inactive' and values.get('FragmentPath')=='' and values.get('ExecStart')=='':return
 expected='/home/tvnner/fawkes/.venv/bin/python'
 prefix='{ path='+expected+' ; argv[]='+expected+' -B /home/tvnner/.local/share/fawkes-worker-link/pi_worker_link.py server ; ignore_errors=no ;'
 if values.get('LoadState')!='loaded' or values.get('FragmentPath')!=str(unit_path) or not values.get('ExecStart','').startswith(prefix) or values['ExecStart'].count('{')!=1:raise PermissionError('Effective service command/source differs; no activation')
def write_once(path,body):
 if path.exists() or path.is_symlink():
  private_file(path)
  if path.is_symlink() or not path.is_file() or path.read_bytes()!=body:raise PermissionError('Preserve differing existing startup file')
  return
 fd,tmp=tempfile.mkstemp(prefix='.worker-startup-',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as f:os.fchmod(f.fileno(),0o600);f.write(body);f.flush();os.fsync(f.fileno())
  os.link(tmp,path)
 finally:os.unlink(tmp)
def install(source,binding):
 source=Path(source)
 validate_binding(binding)
 if set(binding.get('files',{}))!=set(FILES) or sha(EXE)!=SHA:raise PermissionError('Unexpected startup bundle')
 for name in FILES:
  if (source/name).is_symlink() or sha(source/name)!=binding['files'][name]:raise PermissionError('Reviewed startup bytes differ')
 ROOT.mkdir(mode=0o700,exist_ok=True);private_dir(ROOT)
 fd=lock_file(ROOT/'installation.lock')
 try:
  unit_path=Path.home()/'.config/systemd/user'/UNIT
  unit_path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
  if unit_path.is_symlink() or (unit_path.exists() and unit_path.read_bytes()!=(source/UNIT).read_bytes()):raise PermissionError('Do not overwrite another systemd unit')
  # Refresh manager configuration, without starting/stopping any unit, so a
  # disk drop-in cannot be hidden by stale cached manager properties.
  subprocess.run(['systemctl','--user','daemon-reload'],check=True,timeout=15)
  effective_unit(unit_path,allow_missing=True)
  # Validate every preexisting destination before any adoption write.
  targets={ROOT/name:(source/name).read_bytes() for name in FILES}
  targets[ROOT/'accepted-binding.json']=(json.dumps(binding,sort_keys=True,indent=2)+'\n').encode()
  targets[unit_path]=(source/UNIT).read_bytes()
  for target,body in targets.items():
   if target.exists() or target.is_symlink():
    private_file(target)
    if target.read_bytes()!=body:raise PermissionError('Preserve differing prior adoption')
  for name in FILES:write_once(ROOT/name,(source/name).read_bytes())
  write_once(ROOT/'accepted-binding.json',(json.dumps(binding,sort_keys=True,indent=2)+'\n').encode())
  write_once(unit_path,(source/UNIT).read_bytes())
  subprocess.run(['systemctl','--user','daemon-reload'],check=True,timeout=15)
  effective_unit(unit_path)
  private_file(unit_path)
  if unit_path.read_bytes()!=(source/UNIT).read_bytes():raise PermissionError('Unit changed before activation')
  subprocess.run(['systemctl','--user','enable','--now',UNIT],check=True,timeout=25)
  return {'startup_installed':True,'thread_resumed':False,'provider_prompt_sent':False,'approval_decision_sent':False,'unit':UNIT,'thread_id':THREAD,'model_configured':'gpt-6-astra','effort_configured':'xhigh'}
 finally:os.close(fd)
