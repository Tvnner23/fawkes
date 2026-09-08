"""Synthetic Archive storage/projection regressions; no real Archive access.

The separate capture_receiver replay test remains with the retained receiver
adoption batch; this checkout adopts the normal-app dependencies only.
"""
from contextlib import ExitStack,closing
import hashlib,json,os,sqlite3,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from src import ingest
from src.capture import canonical
from src.memory import archive_retrieval
from src.runtime.persistence import persist_live_message


class ArchiveProvenanceRecoveryTests(unittest.TestCase):
    def test_nonfinite_metadata_never_acknowledges_an_unreadable_retained_record(self):
        from src.capture.storage import read_metadata
        for value in (float('nan'),float('inf'),float('-inf'),{'nested':[float('nan')]}):
            with self.subTest(value=repr(value)),self.assertRaises(ValueError):
                ingest.ingest_bytes(b'synthetic','fixture',source='test',capture_type='text',
                                    encoding=value,emit_receipt=False)
            self.assertEqual(list(self.meta.glob('*.json')),[])
        valid=ingest.ingest_bytes(b'synthetic','fixture',source='test',capture_type='text',
                                 encoding='utf-8',emit_receipt=False)
        retained=read_metadata(self.meta/(valid['archive_id']+'.json'))
        self.assertEqual(retained['encoding'],'utf-8')
        self.assertEqual(ingest.read_archived_bytes(retained),b'synthetic')

    def test_new_invalid_owner_metadata_is_not_published_or_acknowledged(self):
        with self.assertRaises(ValueError):
            ingest.ingest_bytes(b'synthetic','fixture',source='test',capture_type='text',instance_id=['malformed'],emit_receipt=False)
        self.assertEqual(list(self.meta.glob('*.json')),[])
        # A failed metadata publication may retain a harmless orphan blob;
        # that is not a successful receipt or an automatic cleanup request.
        result=ingest.ingest_bytes(b'valid','fixture',source='test',capture_type='text',instance_id='one',emit_receipt=False)
        self.assertEqual(result['instance_id'],'one')

    def test_missing_during_optional_scan_is_not_a_confirmed_empty_source(self):
        from src.capture import storage
        class DisappearingScan:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def __iter__(self):raise FileNotFoundError('synthetic directory disappeared after opening')
        with patch.object(storage.os,'scandir',return_value=DisappearingScan()):
            with self.assertRaises(FileNotFoundError):storage.metadata_paths(self.meta,allow_missing=True)
        self.assertEqual(storage.metadata_paths(self.root/'never-created',allow_missing=True),[])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.raw=self.root/'archive/raw';self.meta=self.root/'archive/meta'
        self.raw.mkdir(parents=True);self.meta.mkdir()
        stack=ExitStack();self.addCleanup(stack.close)
        for module,values in [(ingest,{'RAW_DIR':self.raw,'META_DIR':self.meta}),
            (canonical,{'RAW_DIR':self.raw,'META_DIR':self.meta}),
            (archive_retrieval,{'META_DIR':self.meta,'INDEX_PATH':self.root/'index.sqlite3'})]:
            stack.enter_context(patch.multiple(module,**values))

    def state(self):
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file() and p.name!='.ingest.lock'}

    def capture(self,mid,text,at,owner='one',event=None):
        data={'schema_version':1,'conversation_id':'conversation','message_id':mid,'role':'user','text':text}
        result=ingest.ingest_bytes(json.dumps(data).encode(),'fixture',source='test',capture_type='message_state',instance_id=owner,conversation_id='conversation',capture_event_id=event,emit_receipt=False)
        path=self.meta/(result['archive_id']+'.json');value=json.loads(path.read_text());value['created_at']=at;path.write_text(json.dumps(value))
        return result

    def test_changed_event_payload_or_binding_is_rejected_without_writes(self):
        args={'raw_bytes':b'original','title':'fixture','source':'test','capture_type':'text','instance_id':'one',
              'conversation_id':'c','capture_event_id':'e','encoding':'utf-8','original_filename':'test.txt','emit_receipt':False}
        first=ingest.ingest_bytes(**args);before=self.state()
        for field,value in [('raw_bytes',b'changed'),('title','new'),('source','different'),('capture_type','other'),
                            ('instance_id','two'),('conversation_id','d'),('encoding',None),('original_filename','other.txt')]:
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'different'):
                ingest.ingest_bytes(**{**args,field:value})
            self.assertEqual(before,self.state())
        self.assertEqual(ingest.ingest_bytes(**args)['archive_id'],first['archive_id'])

    def test_same_blob_without_event_keeps_separate_owner_metadata(self):
        first=ingest.ingest_bytes(b'payload','fixture',source='test',capture_type='text',instance_id='one',emit_receipt=False)
        second=ingest.ingest_bytes(b'payload','fixture',source='test',capture_type='text',instance_id='two',emit_receipt=False)
        self.assertNotEqual(first['archive_id'],second['archive_id'])
        self.assertEqual(second['instance_id'],'two')
        self.assertEqual(first['raw_file'],second['raw_file'])
        replay=ingest.ingest_bytes(b'payload','fixture',source='test',capture_type='text',instance_id='two',emit_receipt=False)
        self.assertEqual(replay['archive_id'],second['archive_id'])
        self.assertEqual(len(list(self.meta.glob('*.json'))),2)

    def test_corrupt_or_redirected_blob_does_not_replay(self):
        args={'raw_bytes':b'original','title':'fixture','source':'test','capture_type':'text','capture_event_id':'e','emit_receipt':False}
        result=ingest.ingest_bytes(**args)
        path=self.raw/result['raw_file'];path.write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError,'match'):ingest.ingest_bytes(**args)
        path.unlink();outside=self.root/'outside';outside.write_bytes(b'original');path.symlink_to(outside)
        with self.assertRaises(ValueError):ingest.ingest_bytes(**args)
        self.assertEqual(outside.read_bytes(),b'original')

    def test_failed_metadata_publication_never_returns_a_receipt(self):
        with patch.object(ingest,'_atomic_write_json',side_effect=OSError('metadata unavailable')),self.assertRaises(OSError):
            ingest.ingest_bytes(b'original','fixture',source='test',capture_type='text',capture_event_id='e',emit_receipt=False)
        self.assertEqual(list(self.meta.glob('*.json')),[])
        result=ingest.ingest_bytes(b'original','fixture',source='test',capture_type='text',capture_event_id='e',emit_receipt=False)
        self.assertEqual(ingest.read_archived_bytes(result),b'original')

    def test_existing_archive_objects_are_never_overwritten(self):
        target=self.raw/'fixed';target.write_bytes(b'original')
        with self.assertRaises(FileExistsError):ingest._atomic_write_bytes(target,b'replacement')
        self.assertEqual(target.read_bytes(),b'original')

    def test_metadata_link_without_sync_replay_fences_retained_directories(self):
        args=dict(raw_bytes=b'original',title='fixture',source='test',capture_type='text',capture_event_id='e',emit_receipt=False)
        sync=ingest._sync_directory
        def interrupted(path):
            if path==self.meta and list(self.meta.glob('*.json')):raise OSError('after metadata link before sync')
            return sync(path)
        with patch.object(ingest,'_sync_directory',side_effect=interrupted),self.assertRaises(OSError):ingest.ingest_bytes(**args)
        self.assertEqual(len(list(self.meta.glob('*.json'))),1)
        seen=[]
        def observed(path):seen.append(path);return sync(path)
        with patch.object(ingest,'_sync_directory',side_effect=observed):result=ingest.ingest_bytes(**args)
        self.assertTrue(result['_capture_event_replayed'])
        for path in [self.raw,self.meta,*self.raw.parents,*self.meta.parents]:self.assertIn(path,seen)

    def test_first_directory_creation_failure_never_returns_receipt(self):
        meta=self.root/'fresh'/'deep'/'meta';raw=self.root/'fresh'/'raw';sync=ingest._sync_directory
        def interrupted(path):
            if path==meta.parent:raise OSError('new ancestor not durable')
            return sync(path)
        with patch.multiple(ingest,META_DIR=meta,RAW_DIR=raw):
            with patch.object(ingest,'_sync_directory',side_effect=interrupted),self.assertRaises(OSError):
                ingest.ingest_bytes(b'payload','fixture',source='test',capture_type='text',emit_receipt=False)
            self.assertEqual(list(meta.glob('*.json')),[])
            result=ingest.ingest_bytes(b'payload','fixture',source='test',capture_type='text',emit_receipt=False)
            self.assertEqual(ingest.read_archived_bytes(result),b'payload')

    def test_projection_rejects_forged_or_missing_metadata_receipt(self):
        own=self.capture('same','one fact','2026-09-01T00:00:00+00:00',owner='one',event='a')
        other=self.capture('same','two fact','2026-09-01T00:01:00+00:00',owner='two',event='b')
        archive_retrieval.project_retained_message(other,path=self.root/'index.sqlite3')
        before=(self.root/'index.sqlite3').read_bytes()
        with self.assertRaises(ValueError):archive_retrieval.project_retained_message({**own,'instance_id':'two'},path=self.root/'index.sqlite3')
        self.assertEqual((self.root/'index.sqlite3').read_bytes(),before)
        (self.meta/(own['archive_id']+'.json')).unlink()
        with self.assertRaises(ValueError):archive_retrieval.project_retained_message(own,path=self.root/'index.sqlite3')

    def test_replayed_live_message_cannot_replace_index_with_new_text(self):
        args={'instance_id':'one','conversation_id':'c','message_id':'m','role':'user','text':'original evidence'}
        persist_live_message(**args)
        with self.assertRaises(ValueError):persist_live_message(**{**args,'text':'invented replacement'})
        rows=archive_retrieval.retrieve_archive_passages('original evidence',instance_id='one',path=self.root/'index.sqlite3')
        self.assertEqual(len(rows),1)
        self.assertIn('original evidence',rows[0]['content'])

    def test_recapture_preserves_first_observation_order_and_latest_revision(self):
        self.capture('first','original','2026-09-01T00:00:00+00:00',event='a')
        self.capture('second','second','2026-09-01T00:01:00+00:00',event='b')
        latest=self.capture('first','revised','2026-09-01T00:02:00+00:00',event='c')
        rows=canonical.canonical_messages('conversation',instance_id='one')
        self.assertEqual([x['message_id'] for x in rows],['first','second'])
        self.assertEqual(rows[0]['content'],'revised')
        self.assertEqual(rows[0]['source_archive_id'],latest['archive_id'])
        self.assertEqual(rows[0]['created_at'],'2026-09-01T00:00:00+00:00')
        self.assertEqual(rows[0]['revision_captured_at'],'2026-09-01T00:02:00+00:00')
        self.assertEqual(rows[0]['ordering_basis'],'first_observed_capture')
        self.assertIsNone(rows[0]['source_created_at'])

    def test_owner_is_selected_before_revision_grouping(self):
        self.capture('same','one fact','2026-09-01T00:00:00+00:00',owner='one',event='a')
        self.capture('same','two fact','2026-09-01T00:01:00+00:00',owner='two',event='b')
        for owner,text in [('one','one fact'),('two','two fact')]:
            rows=canonical.canonical_messages('conversation',instance_id=owner)
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['content'],text)
        with self.assertRaisesRegex(ValueError,'explicit instance'):canonical.canonical_messages('conversation')

    def test_configured_rebuild_ignores_legacy_root_and_preserves_other_owner(self):
        self.capture('same','one fact','2026-09-01T00:00:00+00:00',owner='one',event='a')
        self.capture('same','two fact','2026-09-01T00:01:00+00:00',owner='two',event='b')
        with patch.multiple(canonical,RAW_DIR=self.root/'unavailable/raw',META_DIR=self.root/'unavailable/meta'):
            for owner in ['one','two']:
                self.assertEqual(archive_retrieval.rebuild_archive_index(instance_id=owner,path=self.root/'index.sqlite3'),1)
        for owner in ['one','two']:
            rows=archive_retrieval.retrieve_archive_passages('fact',instance_id=owner,path=self.root/'index.sqlite3')
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['content'],owner+' fact')

    def test_empty_or_corrupt_rebuild_does_not_destroy_existing_projection(self):
        args={'instance_id':'one','conversation_id':'c','message_id':'m','role':'user','text':'retained original'}
        persist_live_message(**args)
        with patch.object(archive_retrieval,'META_DIR',self.root/'missing/meta'),self.assertRaisesRegex(ValueError,'refusing'):
            archive_retrieval.rebuild_archive_index(instance_id='one',path=self.root/'index.sqlite3')
        (self.meta/'malformed.json').write_text('broken')
        with self.assertRaises(ValueError):archive_retrieval.rebuild_archive_index(instance_id='one',path=self.root/'index.sqlite3')
        self.assertEqual(len(archive_retrieval.retrieve_archive_passages('retained original',instance_id='one',path=self.root/'index.sqlite3')),1)

    def test_environment_binds_ingest_and_canonical_roots_in_fresh_process(self):
        code='''from src import ingest
from src.capture import canonical
from src.memory import archive_retrieval
assert ingest.META_DIR==canonical.META_DIR==archive_retrieval.META_DIR
assert ingest.RAW_DIR==canonical.RAW_DIR
print('same configured Archive roots')
'''
        result=subprocess.run([sys.executable,'-B','-c',code],env={**os.environ,'FAWKES_RUNTIME_STATE_ROOT':str(self.root/'fresh')},capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr.decode())

    def test_concurrent_equal_event_has_one_identity(self):
        code='''import sys
from src import ingest
for _ in range(5):
 ingest.ingest_bytes(b'payload','fixture',source='test',capture_type='text',instance_id='one',capture_event_id='same-event',emit_receipt=False)
'''
        env={**os.environ,'FAWKES_RUNTIME_STATE_ROOT':str(self.root)}
        processes=[subprocess.Popen([sys.executable,'-B','-c',code],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        try:
            for process in processes:
                _,error=process.communicate(timeout=15);self.assertEqual(process.returncode,0,error.decode())
        finally:
            for process in processes:
                if process.poll() is None:process.kill();process.wait()
        self.assertEqual(len(list(self.meta.glob('*.json'))),1)
        self.assertEqual(len(list(self.raw.iterdir())),1)

    def test_ambiguous_historical_event_is_not_arbitrarily_reused(self):
        args={'raw_bytes':b'original','title':'fixture','source':'test','capture_type':'text','capture_event_id':'e','emit_receipt':False}
        value=ingest.ingest_bytes(**args)
        duplicate=dict(value);duplicate['archive_id']='different'
        (self.meta/'different.json').write_text(json.dumps(duplicate));before=self.state()
        with self.assertRaisesRegex(ValueError,'ambiguous'):ingest.ingest_bytes(**args)
        self.assertEqual(before,self.state())

    def test_delayed_old_projection_uses_newest_revision_and_stable_order(self):
        old=self.capture('first','old wording','2026-09-01T00:00:00+00:00',event='old')
        second=self.capture('second','middle wording','2026-09-01T00:01:00+00:00',event='middle')
        new=self.capture('first','newest wording','2026-09-01T00:02:00+00:00',event='new')
        for metadata in [new,second,old]:archive_retrieval.project_retained_message(metadata,path=self.root/'index.sqlite3')
        with closing(sqlite3.connect(self.root/'index.sqlite3')) as connection:
            rows=connection.execute('SELECT message_id,content,created_at,source_archive_id FROM canonical_message_projection ORDER BY created_at').fetchall()
        self.assertEqual([row[0] for row in rows],['first','second'])
        self.assertEqual(rows[0][1],'newest wording');self.assertEqual(rows[0][3],new['archive_id'])
        empty=self.capture('first',' ','2026-09-01T00:03:00+00:00',event='empty')
        archive_retrieval.project_retained_message(empty,path=self.root/'index.sqlite3')
        self.assertEqual(len(list(self.meta.glob('*.json'))),4)
        with closing(sqlite3.connect(self.root/'index.sqlite3')) as connection:
            self.assertEqual(connection.execute('SELECT message_id FROM canonical_message_projection').fetchall(),[('second',)])

    def test_rebuild_locks_projection_before_resolving_source(self):
        self.capture('first','retained fact','2026-09-01T00:00:00+00:00',event='a')
        archive_retrieval.rebuild_archive_index(instance_id='one',path=self.root/'index.sqlite3')
        resolve=archive_retrieval.canonical_messages;observed=[]
        def inspect(*args,**kwargs):
            with closing(sqlite3.connect(self.root/'index.sqlite3',timeout=.01)) as connection:
                with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                    connection.execute('DELETE FROM canonical_message_projection')
            observed.append(True);return resolve(*args,**kwargs)
        with patch.object(archive_retrieval,'canonical_messages',side_effect=inspect):
            archive_retrieval.rebuild_archive_index(instance_id='one',path=self.root/'index.sqlite3')
        self.assertEqual(observed,[True])

    def test_scoped_legacy_collision_preserves_existing_index(self):
        self.capture('same','own fact','2026-09-01T00:00:00+00:00',event='own')
        archive_retrieval.rebuild_archive_index(instance_id='one',path=self.root/'index.sqlite3')
        self.capture('same','legacy fact','2026-09-01T00:01:00+00:00',owner=None,event='legacy')
        with self.assertRaisesRegex(ValueError,'migration'):
            archive_retrieval.rebuild_archive_index(instance_id='one',include_unscoped=True,path=self.root/'index.sqlite3')
        rows=archive_retrieval.retrieve_archive_passages('own fact',instance_id='one',path=self.root/'index.sqlite3')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['content'],'own fact')

    def test_existing_fts_only_history_is_not_erased_by_missing_source(self):
        path=self.root/'index.sqlite3'
        archive_retrieval.index_canonical_message(instance_id='one',conversation_id='c',message_id='m',role='user',
            content='old retained fact',created_at='2026-09-01T00:00:00+00:00',source_archive_id='historical',path=path)
        with closing(sqlite3.connect(path)) as connection:
            connection.execute('DELETE FROM canonical_message_projection');connection.commit()
        with self.assertRaisesRegex(ValueError,'refusing'):
            archive_retrieval.rebuild_archive_index(instance_id='one',path=path)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute('SELECT content FROM canonical_passages').fetchall(),[('old retained fact',)])


    def test_failed_scan_cannot_reuse_event_with_changed_payload(self):
        args={'raw_bytes':b'original','title':'fixture','source':'test','capture_type':'text',
              'instance_id':'one','capture_event_id':'event','emit_receipt':False}
        original=ingest.ingest_bytes(**args);before=self.state();scan=os.scandir
        def denied(directory):
            if Path(directory)==self.meta:raise PermissionError('temporary Archive scan denial')
            return scan(directory)
        with patch('src.capture.storage.os.scandir',side_effect=denied),self.assertRaises(PermissionError):
            ingest.ingest_bytes(**{**args,'raw_bytes':b'changed'})
        self.assertEqual(self.state(),before)
        self.assertEqual(ingest.ingest_bytes(**args)['archive_id'],original['archive_id'])

    def test_partial_metadata_scan_cannot_return_partial_rebuild(self):
        self.capture('a','first fact','2026-09-01T00:00:00+00:00',event='first')
        self.capture('b','second fact','2026-09-01T00:01:00+00:00',event='second')
        index=self.root/'index.sqlite3';archive_retrieval.rebuild_archive_index(instance_id='one',path=index)
        scan=os.scandir;meta=self.meta
        class Partial:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def __iter__(self):
                with scan(meta) as entries:
                    yield next(entries)
                    raise OSError('metadata iterator interrupted')
        with patch('src.capture.storage.os.scandir',return_value=Partial()),self.assertRaises(OSError):
            archive_retrieval.rebuild_archive_index(instance_id='one',path=index)
        self.assertEqual({r['content'] for r in archive_retrieval.retrieve_archive_passages('fact',instance_id='one',path=index)},
                         {'first fact','second fact'})

    def test_unreadable_metadata_cannot_be_skipped_during_event_replay(self):
        args={'raw_bytes':b'original','title':'fixture','source':'test','capture_type':'text',
              'instance_id':'one','capture_event_id':'event','emit_receipt':False}
        original=ingest.ingest_bytes(**args);target=self.meta/(original['archive_id']+'.json');raw=target.read_bytes()
        for broken in [b'\xff',b'[]',b'{"archive_id":"first","archive_id":"second"}']:
            target.write_bytes(broken)
            with self.assertRaises(ValueError):ingest.ingest_bytes(**args)
            self.assertEqual(target.read_bytes(),broken)
            self.assertEqual(len(list(self.meta.glob('*.json'))),1)
        target.write_bytes(raw)
        self.assertEqual(ingest.ingest_bytes(**args)['archive_id'],original['archive_id'])

    def test_corrupt_selected_revision_is_not_silently_replaced_by_older_text(self):
        first=self.capture('same','old fact','2026-09-01T00:00:00+00:00',event='first')
        latest=self.capture('same','new fact','2026-09-01T00:01:00+00:00',event='second')
        target=self.raw/latest['raw_file'];target.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'Selected Archive content'):
            canonical.canonical_messages('conversation',instance_id='one')
        self.assertTrue((self.meta/(first['archive_id']+'.json')).is_file())


if __name__=='__main__':unittest.main()
