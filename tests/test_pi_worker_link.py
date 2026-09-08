import importlib.util, pathlib, tempfile, socket, os, unittest
from unittest.mock import patch
P=pathlib.Path(__file__).resolve().parents[1]/'deploy/pi_worker_link.py'
s=importlib.util.spec_from_file_location('link',P);link=importlib.util.module_from_spec(s);s.loader.exec_module(link)
class Link(unittest.TestCase):
 def test_exact_no_prompt_resume(self):
  args=link.remote_args();self.assertEqual(args[1:3],['resume',link.THREAD]);self.assertIn('on-request',args);self.assertIn('workspace-write',args)
  self.assertEqual(args[-2:],['-c','model_reasoning_effort="xhigh"']);self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',args)
 def test_only_exact_thread_owner(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d)
   for pid,args in [('11',['codex','resume',link.THREAD]),('12',['codex','resume','another']),('13',['python','log',link.THREAD])]:
    (root/pid).mkdir();(root/pid/'cmdline').write_bytes(b'\0'.join(a.encode() for a in args))
   self.assertEqual(link.same_thread_owners(root),[11])
 def test_stale_socket_retained(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'socket';sock=socket.socket(socket.AF_UNIX);sock.bind(str(p));sock.close()
   old=p.stat().st_ino;out=link.archive_stale_socket(p);self.assertFalse(p.exists());self.assertEqual(out.stat().st_ino,old)
 def test_live_socket_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'socket'
   with socket.socket(socket.AF_UNIX) as sock:
    sock.bind(str(p));sock.listen()
    with self.assertRaises(PermissionError):link.archive_stale_socket(p)
    self.assertTrue(p.exists())
 def test_symlink_and_non_socket_refused(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);p=root/'socket';p.write_text('keep')
   with self.assertRaises(PermissionError):link.archive_stale_socket(p)
   p.unlink();p.symlink_to(root/'missing')
   with self.assertRaises(PermissionError):link.archive_stale_socket(p)
 def test_no_missing_socket_mutation(self):
  with tempfile.TemporaryDirectory() as d:self.assertIsNone(link.archive_stale_socket(pathlib.Path(d)/'socket'))
 def test_lock_exclusive(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'lock';fd=link.lock_file(p)
   try:
    with self.assertRaises(BlockingIOError):link.lock_file(p)
   finally:os.close(fd)
 def test_wrong_directory_permission(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);p.chmod(0o755)
   with self.assertRaises(PermissionError):link.private_dir(p)
 def test_persistent_service_no_turn_start(self):
  text=(P.parent/'fawkes-console-worker-app-server.service').read_text()
  self.assertIn('Restart=on-failure',text);self.assertIn('WantedBy=default.target',text);self.assertNotIn('turn/start',text)
 def test_native_wrapper_respects_explicit_quit(self):
  text=(P.parent/'Run-Fawkes-Worker.ps1').read_text();self.assertIn('if($exit -eq 0){break}',text);self.assertIn('if($exit -eq 78)',text)
if __name__=='__main__':unittest.main()
