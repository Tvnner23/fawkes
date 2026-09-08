"""Synthetic F05 regressions; no real Memory, provider or application state."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.memory import mutation,store,worker


class MemoryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.records,self.events = self.root/'records',self.root/'events'
        self.patch = patch.multiple(store,MEMORY_RECORDS_DIR=self.records,MEMORY_EVENTS_DIR=self.events)
        self.patch.start();self.addCleanup(self.patch.stop)

    def create(self,content='original',**kwargs):
        return store.create_memory('fact',content,instance_id='one',confidence=.5,**kwargs)

    def state(self):
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*.json')}

    def test_same_evidence_and_work_replay_do_not_inflate_or_add_events(self):
        first=self.create(source_message_ids=('m1',),source_archive_ids=('a1',),source_work_item_ids=('w1',))
        before=self.state()
        for _ in range(3):
            second=self.create(source_message_ids=('m1',),source_archive_ids=('a1',),source_work_item_ids=('w1',))
            self.assertEqual(first.memory_id,second.memory_id)
            self.assertEqual(second.confidence,.5)
        self.assertEqual(before,self.state())
        with_new_work=store.strengthen_memory(first.memory_id,instance_id='one',confidence=.9,
            source_message_ids=('m1',),source_archive_ids=('a1',),source_work_item_ids=('w2',))
        self.assertEqual(with_new_work['confidence'],.5)
        alias=store.strengthen_memory(first.memory_id,instance_id='one',confidence=.99,
            source_message_ids=('alias-for-m1',),source_archive_ids=('a1',))
        self.assertEqual(alias['confidence'],.5)
        independent=store.strengthen_memory(first.memory_id,instance_id='one',confidence=.5,source_message_ids=('m2',),source_archive_ids=('a2',))
        self.assertEqual(independent['confidence'],.75)

    def test_unattributed_repetition_does_not_manufacture_confidence(self):
        first=self.create()
        before=self.state()
        for _ in range(3):
            self.assertEqual(store.strengthen_memory(first.memory_id,instance_id='one',confidence=.99)['confidence'],.5)
        self.assertEqual(before,self.state())

    def test_owner_guard_covers_every_mutation_and_replacement(self):
        first=self.create();other=store.create_memory('fact','other',instance_id='two')
        for owner in [None,'two','']:
            for call in [lambda:store.revise_memory(first.memory_id,content='bad',instance_id=owner),
                         lambda:store.strengthen_memory(first.memory_id,confidence=1,source_message_ids=('x',),instance_id=owner),
                         lambda:store.supersede_memory(first.memory_id,'fact','bad',instance_id=owner),
                         lambda:store.quarantine_memory(first.memory_id,reason='reason',actor='actor',instance_id=owner),
                         lambda:store.mark_memory_superseded(first.memory_id,superseded_by=other.memory_id,instance_id=owner),
                         lambda:store.merge_duplicate_memories(first.memory_id,other.memory_id,instance_id=owner)]:
                before=self.state()
                with self.assertRaises(ValueError):call()
                self.assertEqual(before,self.state())
        with self.assertRaises(ValueError):
            store.mark_memory_superseded(first.memory_id,superseded_by=other.memory_id,instance_id='one')

    def test_exception_during_staging_leaves_no_partial_supersession(self):
        first=self.create();before=self.state();write=store._write_json
        def fail(path,value):
            if value.get('status')=='superseded':raise OSError('synthetic retirement failure')
            return write(path,value)
        with patch.object(store,'_write_json',side_effect=fail),self.assertRaises(OSError):
            store.supersede_memory(first.memory_id,'fact','new',instance_id='one',source_work_item_ids=('w',))
        self.assertEqual(before,self.state())
        self.assertIsNone(store.find_memory_by_work_item('w',instance_id='one'))

    def test_each_publication_boundary_recovers_records_and_events_once(self):
        # Intent + two records + creation/retirement/operation-completion events.
        for stop in range(1,7):
            with self.subTest(stop=stop),tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                with patch.multiple(store,MEMORY_RECORDS_DIR=root/'records',MEMORY_EVENTS_DIR=root/'events'):
                    first=self.create();write=mutation.durable_write;count=0
                    def fail_after(path,text):
                        nonlocal count
                        write(path,text);count+=1
                        if count==stop:raise OSError('synthetic durable boundary')
                    with patch.object(mutation,'durable_write',side_effect=fail_after),self.assertRaises(OSError):
                        store.supersede_memory(first.memory_id,'fact','new',instance_id='one',source_work_item_ids=('w',))
                    recovered=store.find_memory_by_work_item('w',instance_id='one')
                    self.assertIsNotNone(recovered)
                    self.assertEqual(store.load_memory(first.memory_id)['superseded_by'],recovered['memory_id'])
                    self.assertEqual(len(store.list_memories(instance_id='one')),1)
                    events=list((root/'events').glob('*.json'));self.assertEqual(len(events),4)
                    snapshot={p.name:p.read_bytes() for p in events}
                    store.find_memory_by_work_item('w',instance_id='one')
                    self.assertEqual(snapshot,{p.name:p.read_bytes() for p in events})

    def test_fresh_process_recovers_real_abrupt_exit(self):
        first=self.create()
        code='''import os,sys
from pathlib import Path
from src.memory import store,mutation
root=Path(sys.argv[1]);store.MEMORY_RECORDS_DIR=root/'records';store.MEMORY_EVENTS_DIR=root/'events'
write=mutation.durable_write
def crash(path,text):
 write(path,text)
 if path.parent==store.MEMORY_RECORDS_DIR and not path.name.startswith('.'):
  os._exit(23)
mutation.durable_write=crash
store.supersede_memory(sys.argv[2],'fact','new',instance_id='one',source_work_item_ids=('w',))
'''
        result=subprocess.run([sys.executable,'-B','-c',code,str(self.root),first.memory_id],capture_output=True,timeout=15)
        self.assertEqual(result.returncode,23,result.stderr.decode())
        self.assertEqual(len(store.list_memories(instance_id='one')),1)
        self.assertEqual(store.load_memory(first.memory_id)['status'],'superseded')
        self.assertEqual(len(list(self.events.glob('*.json'))),4)
        self.assertFalse((self.records/'.pending-mutation.json').exists())

    def test_worker_recovery_failure_is_retryable_not_success(self):
        with patch.object(worker,'claim_next_work_item',return_value={'work_item_id':'w'}), \
             patch.object(worker,'find_memory_by_work_item',side_effect=OSError('recovery unavailable')), \
             patch.object(worker,'update_work_item',side_effect=lambda key,**value:value):
            result=worker.apply_next_accepted(instance_id='one')
        self.assertEqual(result['status'],'failed_consolidation_retryable')
        self.assertIn('recovery unavailable',result['error'])

    def test_worker_reports_complete_recovered_operation_without_provider(self):
        first=self.create();write=mutation.durable_write
        def stop(path,text):
            write(path,text)
            if path.name=='.pending-mutation.json':raise OSError('interrupted')
        with patch.object(mutation,'durable_write',side_effect=stop),self.assertRaises(OSError):
            store.supersede_memory(first.memory_id,'fact','new',instance_id='one',source_work_item_ids=('w',))
        with patch.object(worker,'claim_next_work_item',return_value={'work_item_id':'w'}), \
             patch.object(worker,'update_work_item',side_effect=lambda key,**value:value), \
             patch.object(worker,'_assessment_from_item',side_effect=AssertionError('no model/reassessment')):
            result=worker.apply_next_accepted(instance_id='one')
        self.assertEqual(result['status'],'consolidated')
        self.assertEqual(store.load_memory(first.memory_id)['status'],'superseded')

    def test_uncoordinated_change_blocks_complete_recovery_before_other_writes(self):
        first=self.create();write=mutation.durable_write
        def stop(path,text):
            write(path,text)
            if path.name=='.pending-mutation.json':raise OSError('interrupted')
        with patch.object(mutation,'durable_write',side_effect=stop),self.assertRaises(OSError):
            store.supersede_memory(first.memory_id,'fact','new',instance_id='one')
        path=self.records/(first.memory_id+'.json');payload=json.loads(path.read_text());payload['content']='outside edit'
        path.write_text(json.dumps(payload));before=self.state()
        with self.assertRaisesRegex(ValueError,'uncoordinated'):store.list_memories(instance_id='one')
        self.assertEqual(before,self.state())

    def test_paths_and_symlinks_cannot_escape_store(self):
        self.create();outside=self.root/'outside.json';outside.write_text('{"private":"synthetic"}')
        (self.records/'link.json').symlink_to(outside)
        with self.assertRaises(ValueError):store.load_memory('link')
        with self.assertRaises(ValueError):store.load_memory('../outside')
        self.assertEqual(outside.read_text(),'{"private":"synthetic"}')

    def test_self_supersession_is_not_retirement(self):
        first=self.create();before=self.state()
        with self.assertRaises(ValueError):store.supersede_memory(first.memory_id,'fact','original',instance_id='one')
        self.assertEqual(before,self.state())

    def test_new_private_records_and_intent_have_restricted_permissions(self):
        self.create()
        self.assertTrue(all(p.stat().st_mode & 0o777==0o600 for p in self.records.glob('*.json')))
        write=mutation.durable_write
        def stop(path,text):
            write(path,text)
            if path.name=='.pending-mutation.json':raise OSError('interrupted')
        with patch.object(mutation,'durable_write',side_effect=stop),self.assertRaises(OSError):self.create('second')
        self.assertEqual((self.records/'.pending-mutation.json').stat().st_mode & 0o777,0o600)

    def test_legacy_record_only_work_item_is_review_not_fabricated_recovery(self):
        first=self.create()
        path=self.records/(first.memory_id+'.json')
        value=json.loads(path.read_text());value['source_work_item_ids']=['old-work']
        path.write_text(json.dumps(value));before=self.state()
        with patch.object(worker,'claim_next_work_item',return_value={'work_item_id':'old-work'}), \
             patch.object(worker,'update_work_item',side_effect=lambda key,**value:value):
            result=worker.apply_next_accepted(instance_id='one')
        self.assertEqual(result['status'],'review')
        self.assertIn('lacks',result['decision_reason'])
        self.assertEqual(before,self.state())

    def test_legacy_partial_supersession_is_not_silently_completed(self):
        first=self.create()
        new=self.create('new',supersedes=first.memory_id,source_work_item_ids=('old-work',))
        before=self.state()
        with self.assertRaisesRegex(store.IncompleteMemoryMutation,'retirement'):
            store.find_memory_by_work_item('old-work',instance_id='one')
        self.assertEqual(before,self.state())
        self.assertEqual(store.load_memory(new.memory_id)['status'],'active')
        self.assertEqual(store.load_memory(first.memory_id)['status'],'active')

    def test_record_event_recovery_applies_to_other_mutators(self):
        first=self.create();duplicate=self.create('other',source_message_ids=('m2',))
        operations=[lambda:store.revise_memory(first.memory_id,content='revised',instance_id='one'),
                    lambda:store.strengthen_memory(first.memory_id,confidence=.5,source_message_ids=('m3',),instance_id='one'),
                    lambda:store.merge_duplicate_memories(first.memory_id,duplicate.memory_id,instance_id='one'),
                    lambda:store.quarantine_memory(first.memory_id,reason='fixture',actor='test',instance_id='one')]
        for operation in operations:
            write=mutation.durable_write
            def stop(path,text):
                write(path,text)
                if path.parent==self.records and not path.name.startswith('.'):
                    raise OSError('after record before event')
            with patch.object(mutation,'durable_write',side_effect=stop),self.assertRaises(OSError):operation()
            store.load_memory(first.memory_id)
            self.assertFalse((self.records/'.pending-mutation.json').exists())
        self.assertEqual(store.load_memory(first.memory_id)['status'],'quarantined')
        self.assertEqual(store.load_memory(duplicate.memory_id)['status'],'superseded')
        self.assertEqual(len(store.list_memory_events(first.memory_id)),5)

    def test_two_processes_register_identical_evidence_once(self):
        code='''import sys
from pathlib import Path
from src.memory import store
root=Path(sys.argv[1]);store.MEMORY_RECORDS_DIR=root/'records';store.MEMORY_EVENTS_DIR=root/'events'
for _ in range(8):
 store.create_memory('fact','concurrent',instance_id='one',confidence=.5,source_message_ids=('m1',),source_work_item_ids=('w1',))
'''
        children=[subprocess.Popen([sys.executable,'-B','-c',code,str(self.root)],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        try:
            for child in children:
                out,error=child.communicate(timeout=15)
                self.assertEqual(child.returncode,0,error.decode())
        finally:
            for child in children:
                if child.poll() is None:child.kill();child.wait()
        memories=store.list_memories(instance_id='one')
        self.assertEqual(len(memories),1)
        self.assertEqual(memories[0]['confidence'],.5)
        self.assertEqual(len(list(self.events.glob('*.json'))),1)

    def test_malformed_intent_or_digest_does_not_publish(self):
        self.create();pending=self.records/'.pending-mutation.json'
        for value in [{}, {'roots':[],'writes':[],'sha256':'wrong'}]:
            pending.write_text(json.dumps(value));before=self.state()
            with self.assertRaises(ValueError):store.list_memories(instance_id='one')
            self.assertEqual(before,self.state())


if __name__=='__main__':unittest.main()
