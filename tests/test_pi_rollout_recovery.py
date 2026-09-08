import importlib.util,pathlib,json,tempfile,unittest
from unittest.mock import patch
P=pathlib.Path(__file__).resolve().parents[1]/'deploy/pi_console_shutdown_rollout.py'
s=importlib.util.spec_from_file_location('rollout',P);r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
class Recovery(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)
  self.patch=patch.object(r,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop)
  self.old='a'*64;self.rollback='b'*64;self.pre={}
  for n in r.OLD_FILES:(self.root/n).write_bytes(b'old');self.pre[n]=r.sha(b'old')
  self.failed={'state':'failed_retained_for_reconciliation','action':'install','operation_id':self.old}
  self.row={'state':'completed','action':'rollback','operation_id':self.rollback,'result':{'fresh_accepted_ready':True,'policy_result':{'operation_id':self.old,'policy_present':False},'installed_files':self.pre}}
  self.p={'action':'install','linked_install_operation':self.old,'preimages':self.pre}
  self.write()
 def write(self):
  for key,v in [(self.old,self.failed),(self.rollback,self.row)]: (self.root/('power-rollout-'+key+'.json')).write_text(json.dumps(v))
 def test_qualified_successor_preserves_failed_record(self):
  p=self.root/('power-rollout-'+self.old+'.json');before=p.read_bytes();v=r.recovery_lineage(self.p)
  self.assertEqual(v['failed_operation_id'],self.old);self.assertEqual(p.read_bytes(),before)
 def test_not_completed_rollback_rejected(self):
  self.row['state']='failed_retained_for_reconciliation';self.write()
  with self.assertRaises(ValueError):r.recovery_lineage(self.p)
 def test_changed_postimage_rejected(self):
  (self.root/'supervisor.py').write_bytes(b'changed')
  with self.assertRaises(ValueError):r.recovery_lineage(self.p)
 def test_policy_not_withdrawn_rejected(self):
  self.row['result']['policy_result']['policy_present']=True;self.write()
  with self.assertRaises(ValueError):r.recovery_lineage(self.p)
 def test_duplicate_matching_rollbacks_rejected(self):
  (self.root/('power-rollout-'+'c'*64+'.json')).write_text(json.dumps(self.row))
  with self.assertRaises(ValueError):r.recovery_lineage(self.p)
 def test_completed_original_not_relabeled(self):
  self.failed['state']='completed';self.write()
  with self.assertRaises(ValueError):r.recovery_lineage(self.p)
 def test_normal_install_unchanged(self):
  self.assertIsNone(r.recovery_lineage({**self.p,'linked_install_operation':None}))
if __name__=='__main__':unittest.main()
