import importlib.util,json,os,pathlib,sys,tempfile,unittest
from unittest.mock import patch,Mock
P=pathlib.Path(__file__).resolve().parents[1]/'deploy'
sys.path.insert(0,str(P))
import pi_worker_link as link
import install_pi_worker_link as installer
class Install(unittest.TestCase):
 def properties(self,unit):return ('LoadState=loaded\nActiveState=inactive\nFragmentPath='+str(unit)+'\nDropInPaths=\nExecStart={ path=/home/tvnner/fawkes/.venv/bin/python ; argv[]=/home/tvnner/fawkes/.venv/bin/python -B /home/tvnner/.local/share/fawkes-worker-link/pi_worker_link.py server ; ignore_errors=no ; start_time=[n/a] ; }\n').encode()
 def binding(self):return {'commit':'a'*40,'snapshot':'candidate-snapshot-'+'b'*64,'receipt':'c'*64,'thread_id':link.THREAD,'model':'gpt-6-astra','effort':'xhigh','files':{n:installer.sha(P/n) for n in installer.FILES}}
 def test_complete_binding(self):link.validate_binding(self.binding())
 def test_invalid_binding_fails_before_write(self):
  for k in ['commit','snapshot','receipt','thread_id','model','effort','files']:
   v=self.binding();v[k]=None
   with self.subTest(k=k),patch.object(installer,'write_once') as write,self.assertRaises(PermissionError):installer.install(P,v)
   write.assert_not_called()
 def test_write_once_idempotent_not_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'file';installer.write_once(p,b'accepted');ino=p.stat().st_ino
   installer.write_once(p,b'accepted');self.assertEqual(ino,p.stat().st_ino)
   with self.assertRaises(PermissionError):installer.write_once(p,b'different')
   self.assertEqual(p.read_bytes(),b'accepted')
 def test_existing_insecure_or_symlink_refused(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'file';p.write_bytes(b'x');p.chmod(0o644)
   with self.assertRaises(PermissionError):installer.write_once(p,b'x')
   p.unlink();p.symlink_to(pathlib.Path(d)/'missing')
   with self.assertRaises(PermissionError):installer.write_once(p,b'x')
 def test_install_and_duplicate_no_resume(self):
  with tempfile.TemporaryDirectory() as d:
   base=pathlib.Path(d);root=base/'worker';unit=base/'.config/systemd/user'/link.UNIT
   with patch.object(installer,'ROOT',root),patch.object(pathlib.Path,'home',return_value=base),patch.object(installer.subprocess,'check_output',side_effect=lambda *a,**k:self.properties(unit) if unit.exists() else b'LoadState=not-found\nActiveState=inactive\nFragmentPath=\nDropInPaths=\nExecStart=\n'),patch.object(installer.subprocess,'run') as run:
    one=installer.install(P,self.binding());two=installer.install(P,self.binding())
   self.assertFalse(one['thread_resumed']);self.assertFalse(two['provider_prompt_sent']);self.assertEqual(unit.read_bytes(),(P/link.UNIT).read_bytes())
   self.assertFalse(any('resume' in x.args[0] for x in run.call_args_list))
 def test_unknown_running_server_refused(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d)/'worker'
   with patch.object(installer,'ROOT',root),patch.object(pathlib.Path,'home',return_value=pathlib.Path(d)),patch.object(installer.subprocess,'check_output',return_value=b'ActiveState=active\nFragmentPath=/run/user/1000/systemd/transient/other\n'),patch.object(installer.subprocess,'run') as run,self.assertRaises(PermissionError):installer.install(P,self.binding())
   self.assertFalse(any('enable' in x.args[0] for x in run.call_args_list));self.assertFalse((root/'accepted-binding.json').exists())
 def test_dropin_changed_exec_or_missing_configuration_refused(self):
  unit=pathlib.Path('/private/user')/link.UNIT;good=self.properties(unit)
  for bad in [good.replace(b'DropInPaths=',b'DropInPaths=/tmp/unreviewed.conf'),good.replace(b'argv[]=/home/tvnner/fawkes/.venv/bin/python',b'argv[]=/bin/other'),good.replace(b'DropInPaths=\n',b''),good.replace(str(unit).encode(),b'/other/unit')]:
   with self.subTest(bad=bad),patch.object(installer.subprocess,'check_output',return_value=bad),self.assertRaises(PermissionError):installer.effective_unit(unit)
 def test_late_dropin_after_reload_prevents_activation(self):
  with tempfile.TemporaryDirectory() as d:
   base=pathlib.Path(d);unit=base/'.config/systemd/user'/link.UNIT
   with patch.object(installer,'ROOT',base/'worker'),patch.object(pathlib.Path,'home',return_value=base),patch.object(installer.subprocess,'check_output',side_effect=[b'LoadState=not-found\nActiveState=inactive\nFragmentPath=\nDropInPaths=\nExecStart=\n',self.properties(unit).replace(b'DropInPaths=',b'DropInPaths=/new/override.conf')]),patch.object(installer.subprocess,'run') as run,self.assertRaises(PermissionError):installer.install(P,self.binding())
   self.assertFalse(any('enable' in x.args[0] for x in run.call_args_list))
 def test_attach_existing_owner_does_not_start_or_resume(self):
  with patch.object(link,'verified_binding'),patch.object(sys,'argv',['script','attach']),patch.object(sys.stdin,'isatty',return_value=True),patch.object(sys.stdout,'isatty',return_value=True),patch.object(link,'lock_file',return_value=99),patch.object(link.os,'close'),patch.object(link,'same_thread_owners',return_value=[123]),patch.object(link.subprocess,'run') as run,patch.object(link.os,'execv') as execute:
   self.assertEqual(link.main(),75);run.assert_not_called();execute.assert_not_called()
 def test_owner_appearing_during_start_preserved(self):
  with patch.object(link,'verified_binding'),patch.object(sys,'argv',['script','attach']),patch.object(sys.stdin,'isatty',return_value=True),patch.object(sys.stdout,'isatty',return_value=True),patch.object(link,'lock_file',return_value=99),patch.object(link.os,'close'),patch.object(link,'same_thread_owners',side_effect=[[],[123]]),patch.object(link.subprocess,'run'),patch.object(link,'verify_server'),patch.object(link.os,'execv') as execute:
   self.assertEqual(link.main(),75);execute.assert_not_called()
 def test_attach_is_only_exact_resume_no_prompt(self):
  with patch.object(link,'verified_binding'),patch.object(sys,'argv',['script','attach']),patch.object(sys.stdin,'isatty',return_value=True),patch.object(sys.stdout,'isatty',return_value=True),patch.object(link,'lock_file',return_value=99),patch.object(link,'same_thread_owners',return_value=[]),patch.object(link.subprocess,'run'),patch.object(link,'verify_server'),patch.object(link.os,'set_inheritable'),patch.object(link.os,'execv') as execute:
   link.main();execute.assert_called_once_with(str(link.EXE),link.remote_args())
 def test_windows_startup_interactive_no_duplicate_or_elevation(self):
  text=(P/'Install-Fawkes-Worker-Startup.ps1').read_text()
  for fragment in ['-AtLogOn','-LogonType Interactive -RunLevel Limited','-MultipleInstances IgnoreNew',".State -ne 'Running'"]:
   self.assertIn(fragment,text)
  self.assertNotIn('-Force',text);self.assertNotIn('-RunLevel Highest',text)
if __name__=='__main__':unittest.main()
