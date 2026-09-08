"""Isolated filesystem/service fixtures. Never invokes real sudo or poweroff."""
import base64,hashlib,json,os,pathlib,stat,subprocess,sys,tempfile,types,unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'deploy'))
import pi_console_power_policy as policy
import pi_console_shutdown_rollout as rollout
OP='a'*64
def record(body):return {'base64':base64.b64encode(body).decode(),'sha256':hashlib.sha256(body).hexdigest(),'byte_length':len(body)}
class Policy(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=pathlib.Path(self.tmp.name);self.target=self.root/'fixed-policy'
  for name,value in [('DIRECTORY',self.root),('TARGET',self.target)]:
   p=patch.object(policy,name,value);p.start();self.addCleanup(p.stop)
  p=patch.object(policy,'verify_platform');p.start();self.addCleanup(p.stop)
  # The fixture is ordinary-user owned; production additionally requires uid 0.
  real=pathlib.Path.lstat
  def fixture_stat(path,*a,**k):
   value=real(path,*a,**k)
   if path==self.target or (path.name=='policy' and path.parent.name.startswith('.fawkes-power-rollback-')):
    items=list(value);items[4]=0;return os.stat_result(items)
   return value
  p=patch.object(pathlib.Path,'lstat',fixture_stat);p.start();self.addCleanup(p.stop)
  p=patch.object(policy.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'',b''));self.run=p.start();self.addCleanup(p.stop)
 def test_exact_grant_once_and_matching_rollback(self):
  first=policy.apply('install',OP);self.assertTrue(first['changed'])
  self.assertEqual(self.target.read_bytes(),policy.policy_bytes(OP))
  self.assertEqual(self.target.stat().st_mode&0o777,0o440)
  self.assertFalse(policy.apply('install',OP)['changed']);self.assertEqual(self.run.call_count,1)
  self.assertTrue(policy.apply('rollback',OP)['changed']);self.assertFalse(self.target.exists())
  self.assertFalse(policy.apply('rollback',OP)['changed'])
 def test_different_operation_never_removes_or_overwrites(self):
  policy.apply('install',OP)
  for action in ['install','rollback']:
   with self.assertRaises(PermissionError):policy.apply(action,'b'*64)
  self.assertEqual(self.target.read_bytes(),policy.policy_bytes(OP))
 def test_existing_broader_policy_preserved(self):
  self.target.write_bytes(b'other administrator rule\n');self.target.chmod(0o440)
  with self.assertRaises(PermissionError):policy.apply('install',OP)
  self.run.assert_not_called();self.assertEqual(self.target.read_bytes(),b'other administrator rule\n')
 def test_invalid_visudo_never_publishes_policy(self):
  self.run.return_value=subprocess.CompletedProcess([],1,b'',b'bad')
  with self.assertRaises(ValueError):policy.apply('install',OP)
  self.assertFalse(self.target.exists());self.assertEqual(list(self.root.iterdir()),[])
 def test_symlink_and_wrong_mode_refused(self):
  other=self.root/'other';other.write_text('preserve');self.target.symlink_to(other)
  with self.assertRaises(PermissionError):policy.apply('install',OP)
  self.assertEqual(other.read_text(),'preserve');self.target.unlink()
  self.target.write_bytes(policy.policy_bytes(OP));self.target.chmod(0o644)
  with self.assertRaises(PermissionError):policy.apply('rollback',OP)
 def test_exclusive_publish_does_not_replace_racing_admin(self):
  def race(source,target):
   self.target.write_bytes(b'admin');raise FileExistsError('occupied')
  with patch.object(policy.os,'link',side_effect=race),self.assertRaises(FileExistsError):policy.apply('install',OP)
  self.assertEqual(self.target.read_bytes(),b'admin')
 def test_no_arbitrary_action_or_identifier(self):
  for value in ['','../x','a'*63,'A'*64]:
   with self.assertRaises(ValueError):policy.apply('install',value)
  with self.assertRaises(ValueError):policy.apply('anything',OP)
  self.run.assert_not_called()
 def test_current_policy_verification_never_installs_missing_rule(self):
  with self.assertRaises(PermissionError):policy.apply('verify',OP)
  self.assertFalse(self.target.exists());self.run.assert_not_called()
  policy.apply('install',OP);self.assertFalse(policy.apply('verify',OP)['changed'])
  with self.assertRaises(PermissionError):policy.apply('verify-absent',OP)
  policy.apply('rollback',OP);self.assertFalse(policy.apply('verify-absent',OP)['policy_present'])
 def test_admin_replacement_before_atomic_withdrawal_is_restored_not_deleted(self):
  policy.apply('install',OP);real=policy.os.rename
  def replace_then_move(source,target):
   self.target.chmod(0o640);self.target.write_bytes(b'administrator replacement');self.target.chmod(0o440);real(source,target)
  with patch.object(policy.os,'rename',side_effect=replace_then_move),self.assertRaises(PermissionError):policy.apply('rollback',OP)
  self.assertEqual(self.target.read_bytes(),b'administrator replacement')
  self.assertEqual(next(self.root.glob('.fawkes-power-rollback-*/policy')).read_bytes(),b'administrator replacement')
 def test_new_admin_path_after_withdrawal_is_never_touched(self):
  policy.apply('install',OP);real=policy.os.rename
  def move_then_replace(source,target):
   real(source,target);self.target.write_bytes(b'new administrator policy');self.target.chmod(0o440)
  with patch.object(policy.os,'rename',side_effect=move_then_replace),self.assertRaises(PermissionError):policy.apply('rollback',OP)
  self.assertEqual(self.target.read_bytes(),b'new administrator policy')
  self.assertEqual(next(self.root.glob('.fawkes-power-rollback-*/policy')).read_bytes(),policy.policy_bytes(OP))

class Rollout(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)
  p=patch.object(rollout,'ROOT',self.root);p.start();self.addCleanup(p.stop)
  self.payload={'action':'install','snapshot':'candidate-snapshot-'+'a'*64,'commit':'b'*40,'acceptance_receipt':'c'*64,'files':{},'preimages':{},'policy':record(b'# accepted root helper\n'),'linked_install_operation':None}
  for name in rollout.NEW_FILES:
   body=b'new '+name.encode()
   if name=='accepted-console.json':body=json.dumps({'candidate_snapshot_id':self.payload['snapshot']}).encode()
   if name=='pi_console_power_policy.py':body=b'# accepted root helper\n'
   self.payload['files'][name]=record(body)
   old=(b'old '+name.encode()) if name in rollout.OLD_FILES else None
   self.payload['preimages'][name]=hashlib.sha256(old).hexdigest() if old else None
   if old:(self.root/name).write_bytes(old)
  real=pathlib.Path.read_bytes
  def reads(path):
   if str(path)=='/proc/device-tree/model':return b'Raspberry Pi 4 Model B Rev 1.5\0'
   return real(path)
  p=patch.object(pathlib.Path,'read_bytes',reads);p.start();self.addCleanup(p.stop)
  p=patch.object(rollout.os,'getuid',return_value=1000);p.start();self.addCleanup(p.stop)
  p=patch.object(rollout.subprocess,'run',return_value=subprocess.CompletedProcess([],0));self.calls=p.start();self.addCleanup(p.stop)
  p=patch.object(rollout,'policy_action',return_value={'changed':True,'action':'install','operation_id':'fixture','shutdown_executed':False});self.policy=p.start();self.addCleanup(p.stop)
  p=patch.object(rollout,'ready',return_value={'state':'READY','time':123});self.ready=p.start();self.addCleanup(p.stop)
 def test_validate_full_scope_and_byte_binding(self):
  files,_=rollout.validate(self.payload);self.assertEqual(set(files),rollout.NEW_FILES)
  self.payload['files']['supervisor.py']['sha256']='0'*64
  with self.assertRaises(ValueError):rollout.run(self.payload)
  self.calls.assert_not_called();self.policy.assert_not_called()
 def test_install_order_and_duplicate_fresh_verification(self):
  result=rollout.run(self.payload);self.assertTrue(result['fresh_accepted_ready'])
  self.assertFalse(result['shutdown_requested']);self.assertEqual(self.calls.call_args_list[0].args[0],['/usr/bin/sudo','-v','-p','Pi sudo password (native terminal only):\n'])
  count=self.calls.call_count;again=rollout.run(self.payload)
  self.assertTrue(again['duplicate_reconciled_without_restart']);self.assertEqual(self.policy.call_count,2)
  self.assertEqual(self.policy.call_args.args[1:],('verify',result['operation_id']))
  self.assertEqual(self.calls.call_count,count+2);self.assertEqual(self.ready.call_count,2)
  self.assertEqual(self.calls.call_args.args[0],['/usr/bin/systemctl','--user','is-active','--quiet','fawkes-pi-console.service'])
 def test_duplicate_does_not_claim_old_readiness(self):
  rollout.run(self.payload);self.ready.side_effect=RuntimeError('now disconnected')
  with self.assertRaises(RuntimeError):rollout.run(self.payload)
  self.assertEqual(self.policy.call_count,2)
 def test_duplicate_missing_or_changed_policy_is_not_success_or_reinstalled(self):
  rollout.run(self.payload);count=self.calls.call_count
  def missing(source,action,operation):
   self.assertEqual(action,'verify');raise PermissionError('policy changed')
  self.policy.side_effect=missing
  with self.assertRaises(PermissionError):rollout.run(self.payload)
  self.assertEqual(self.calls.call_count,count+1);self.assertEqual(self.ready.call_count,1)
 def test_changed_preimage_stops_before_native_auth(self):
  (self.root/'supervisor.py').write_bytes(b'unrelated')
  with self.assertRaises(ValueError):rollout.run(self.payload)
  self.calls.assert_not_called();self.assertFalse(list(self.root.glob('power-rollout-*.json')))
 def test_failed_readiness_preserves_journal_and_refuses_blind_retry(self):
  self.ready.side_effect=RuntimeError('no exact browser')
  with self.assertRaises(RuntimeError):rollout.run(self.payload)
  path=next(self.root.glob('power-rollout-*.json'));value=json.loads(path.read_text())
  self.assertEqual(value['state'],'failed_retained_for_reconciliation');self.assertTrue(pathlib.Path(value['backup']).exists())
  with self.assertRaises(RuntimeError):rollout.run(self.payload)
  self.assertEqual(self.policy.call_count,1)
 def test_rollback_exact_link_removes_only_its_policy_and_restores_parent(self):
  result=rollout.run(self.payload);old={name:(pathlib.Path(result['rollback_directory'])/name).read_bytes() for name in rollout.OLD_FILES}
  old['accepted-console.json']=json.dumps({'candidate_snapshot_id':'candidate-snapshot-'+'d'*64}).encode()
  back={**self.payload,'action':'rollback','snapshot':'candidate-snapshot-'+'d'*64,'commit':'e'*40,'acceptance_receipt':'f'*64,
    'linked_install_operation':result['operation_id'],'files':{n:record(b) for n,b in old.items()},'preimages':{n:self.payload['files'][n]['sha256'] for n in old}}
  final=rollout.run(back);self.assertEqual(final['commit'],'e'*40)
  self.assertEqual(self.policy.call_args.args[1:],('rollback',result['operation_id']))
  self.assertTrue((self.root/'pi_shutdown_state.py').exists()) # retained evidence/helper, no longer imported
 def test_arbitrary_extra_file_is_not_in_scope(self):
  self.payload['files']['../../etc/sudoers']=record(b'bad')
  with self.assertRaises(ValueError):rollout.run(self.payload)
  self.calls.assert_not_called()

if __name__=='__main__':unittest.main()
