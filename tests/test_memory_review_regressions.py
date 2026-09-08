"""Held finding reproductions D1–D6 through real functions, synthetic state only."""
from contextlib import ExitStack
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from src.memory import store,mutation,worker,development_retrieval,development_runtime
from src.capture import canonical
from src.memory.semantic import SemanticMemoryAssessment


class MemoryReviewRegressions(unittest.TestCase):
    def ranking_pipeline_fixture(self, *, owner=None, semantic=True, matcher=None):
        from src.memory.pipeline import process_conversation
        from src.memory.semantic_retrieval import SemanticMemoryRetriever
        self.message('input','input',owner,'a new durable preference','2026-09-01T00:00:00+00:00')
        evaluator=Mock();evaluator.evaluate.return_value=SemanticMemoryAssessment(True,'preference','new preference',.9,.8)
        provider=Mock();provider.rank_memories.side_effect=lambda **kwargs:list(kwargs['memories'])
        result=process_conversation('conversation',instance_id=owner,evaluator=evaluator,matcher=matcher,
            semantic_retriever=SemanticMemoryRetriever(provider) if semantic else None)
        return result,provider

    def test_C9_D1_default_pipeline_ranking_never_receives_other_owners(self):
        store.create_memory('fact','first owner private fact',instance_id='one')
        store.create_memory('fact','second owner private fact',instance_id='two')
        legacy=store.create_memory('fact','legacy fact',legacy_unscoped=True)
        result,provider=self.ranking_pipeline_fixture()
        self.assertEqual([m['memory_id'] for m in provider.rank_memories.call_args.kwargs['memories']],[legacy.memory_id])
        self.assertEqual(result[0].action,'created')
        self.assertIsNone(store.load_memory(result[0].memory_id)['instance_id'])

    def test_C9_D1_scoped_pipeline_ranking_remains_exact(self):
        own=store.create_memory('fact','first owner fact',instance_id='one')
        store.create_memory('fact','second owner fact',instance_id='two')
        store.create_memory('fact','legacy fact',legacy_unscoped=True)
        result,provider=self.ranking_pipeline_fixture(owner='one')
        self.assertEqual([m['memory_id'] for m in provider.rank_memories.call_args.kwargs['memories']],[own.memory_id])
        self.assertEqual(store.load_memory(result[0].memory_id)['instance_id'],'one')

    def test_C9_D1_empty_legacy_selection_does_not_refill_from_other_owners(self):
        for semantic in (True,False):
            with self.subTest(semantic=semantic):
                store.create_memory('fact','new preference',instance_id='one')
                matcher=Mock();matcher.compare.return_value=Mock(relation='unrelated')
                result,provider=self.ranking_pipeline_fixture(semantic=semantic,matcher=matcher)
                self.assertEqual(result[0].action,'created')
                matcher.compare.assert_not_called();provider.rank_memories.assert_not_called()
                for p in list(self.records.glob('*.json'))+list(self.events.glob('*.json')):p.unlink()

    def test_C9_D1_lexical_retrieval_and_default_matcher_only_receive_legacy(self):
        from src.memory.retrieval import retrieve_memories
        from src.memory.consolidate import consolidate_assessment
        store.create_memory('fact','new preference scoped',instance_id='one')
        legacy=store.create_memory('fact','new preference legacy',legacy_unscoped=True)
        self.assertEqual([m['memory_id'] for m in retrieve_memories('new preference')],[legacy.memory_id])
        matcher=Mock();matcher.compare.return_value=Mock(relation='unrelated')
        consolidate_assessment(SemanticMemoryAssessment(True,'preference','separate preference',.9,.8),matcher=matcher)
        self.assertEqual(matcher.compare.call_count,1)
        self.assertEqual(matcher.compare.call_args.kwargs['existing_memory']['memory_id'],legacy.memory_id)

    def test_C9_D1_default_single_scoped_conversation_rejected_before_evaluation(self):
        from src.memory.pipeline import process_conversation
        self.message('input','input','one','private scoped content','2026-09-01T00:00:00+00:00')
        evaluator=Mock();evaluator.evaluate.return_value=SemanticMemoryAssessment(False,None,None,0,0)
        with self.assertRaises(store.MemoryOwnershipReview):process_conversation('conversation',evaluator=evaluator)
        evaluator.evaluate.assert_not_called()

    def test_C9_D1_foreign_candidate_or_context_rejected_before_any_provider(self):
        from src.memory.pipeline import process_memory_candidate
        for candidate,context,owner in (
            ({'content':'foreign','instance_id':'two'},(),'one'),
            ({'content':'own','instance_id':'one'},({'content':'foreign','instance_id':'two'},),'one'),
            ({'content':'legacy','instance_id':None},(),'one')):
            evaluator=Mock();evaluator.evaluate.return_value=SemanticMemoryAssessment(False,None,None,0,0)
            with self.subTest(candidate=candidate,context=context):
                with self.assertRaises(store.MemoryOwnershipReview):
                    process_memory_candidate(candidate,evaluator=evaluator,conversation_context=context,instance_id=owner)
                evaluator.evaluate.assert_not_called()

    def test_C9_D1_foreign_ranker_output_rejected_before_matcher_or_mutation(self):
        from src.memory.pipeline import process_memory_candidate
        memory=store.create_memory('fact','foreign',instance_id='two')
        evaluator=Mock();evaluator.evaluate.return_value=SemanticMemoryAssessment(True,'fact','new',.9,.8)
        retriever=Mock();retriever.rank.return_value=[store.load_memory(memory.memory_id)]
        matcher=Mock();before={str(p):p.read_bytes() for p in self.root.rglob('*.json')}
        with self.assertRaises(store.MemoryOwnershipReview):
            process_memory_candidate({'content':'input'},evaluator=evaluator,semantic_retriever=retriever,matcher=matcher)
        matcher.compare.assert_not_called()
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*.json')})

    def test_C9_D1_administrative_all_owner_listing_and_explicit_legacy_read_preserved(self):
        first=store.create_memory('fact','first',instance_id='one')
        second=store.create_memory('fact','second',instance_id='two')
        legacy=store.create_memory('fact','legacy',legacy_unscoped=True)
        self.assertEqual({m['memory_id'] for m in store.list_memories()},{first.memory_id,second.memory_id,legacy.memory_id})
        self.assertEqual({m['memory_id'] for m in store.list_memories_for_context(instance_id='one',include_unscoped=True)},
                         {first.memory_id,legacy.memory_id})
        self.assertEqual([m['memory_id'] for m in store.list_memories_for_context(include_unscoped=True)],[legacy.memory_id])

    def test_C9_D1_legacy_duplicate_and_supersession_ignore_scoped_same_content(self):
        scoped=store.create_memory('fact','same',instance_id='one')
        legacy=store.create_memory('fact','same',legacy_unscoped=True)
        duplicate=store.create_memory('fact','same',legacy_unscoped=True)
        self.assertEqual(legacy.memory_id,duplicate.memory_id)
        self.assertNotEqual(scoped.memory_id,legacy.memory_id)
        store.create_memory('fact','replacement',instance_id='one')
        result=store.supersede_memory(legacy.memory_id,'fact','replacement')
        self.assertIsNone(result.instance_id)
        self.assertEqual(store.load_memory(scoped.memory_id)['status'],'active')

    def test_C9_D1_legacy_cleanup_compares_only_owned_records(self):
        from src.memory.consolidate import cleanup_semantic_duplicates
        scoped=store.create_memory('fact','scoped',instance_id='one')
        store.create_memory('fact','legacy first',legacy_unscoped=True)
        store.create_memory('fact','legacy second',legacy_unscoped=True)
        matcher=Mock();matcher.compare.return_value=Mock(relation='unrelated')
        cleanup_semantic_duplicates(matcher=matcher)
        self.assertEqual(matcher.compare.call_count,1)
        self.assertIsNone(matcher.compare.call_args.kwargs['existing_memory']['instance_id'])
        matcher.reset_mock()
        with self.assertRaises(ValueError):cleanup_semantic_duplicates(matcher=matcher,memories=[store.load_memory(scoped.memory_id)])
        matcher.compare.assert_not_called()

    def test_C9_D1_actual_runtime_does_not_send_scoped_conversation_to_default_provider(self):
        from src.memory.runtime import process_memory_conversation
        self.message('input','input','one','private scoped content','2026-09-01T00:00:00+00:00')
        provider=Mock()
        with self.assertRaises(store.MemoryOwnershipReview):process_memory_conversation('conversation',provider=provider)
        self.assertEqual(provider.mock_calls,[])

    def mixed_merge_fixture(self, operation, *, new_work=True, inherited=True):
        donor=self.create(source_work_item_ids=['old'])
        target=store.create_memory('fact','survivor',instance_id='one')
        store.merge_duplicate_memories(target.memory_id,donor.memory_id,instance_id='one')
        work=(['old'] if inherited else [])+(['new'] if new_work else [])
        if operation=='revise':
            store.revise_memory(target.memory_id,content='later revision',instance_id='one',source_work_item_ids=work)
        else:
            store.strengthen_memory(target.memory_id,confidence=.8,source_message_ids=['later-evidence'],instance_id='one',source_work_item_ids=work)
        return donor,target

    def test_C8_D1_revision_after_merge_preserves_old_donor_and_new_completion(self):
        donor,target=self.mixed_merge_fixture('revise')
        self.assertEqual(store.find_memory_by_work_item('old',instance_id='one')['memory_id'],donor.memory_id)
        self.assertEqual(store.find_memory_by_work_item('new',instance_id='one')['memory_id'],target.memory_id)

    def test_C8_D1_strengthening_after_merge_preserves_old_donor_and_new_completion(self):
        donor,target=self.mixed_merge_fixture('strengthen')
        self.assertEqual(store.find_memory_by_work_item('old',instance_id='one')['memory_id'],donor.memory_id)
        self.assertEqual(store.find_memory_by_work_item('new',instance_id='one')['memory_id'],target.memory_id)

    def test_C8_D1_existing_only_history_declares_no_new_completion(self):
        donor,target=self.mixed_merge_fixture('revise',new_work=False)
        store.strengthen_memory(target.memory_id,confidence=.8,source_message_ids=['later-more'],instance_id='one',source_work_item_ids=['old'])
        event=next(e for e in store.list_memory_events(target.memory_id) if e['event_type']=='revised')
        self.assertEqual(event['data']['completed_work_item_ids'],[])
        self.assertNotIn('old',store.load_memory(target.memory_id).get('completed_work_item_events',{}))
        self.assertEqual(store.find_memory_by_work_item('old',instance_id='one')['memory_id'],donor.memory_id)

    def test_C8_D1_combined_history_keeps_its_other_work_binding_required(self):
        donor,target=self.mixed_merge_fixture('revise')
        path=self.records/(target.memory_id+'.json');original=path.read_bytes()
        value=json.loads(original);del value['completed_work_item_events']['new'];path.write_text(json.dumps(value))
        with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item('old',instance_id='one')
        path.write_bytes(original)
        event=store.load_memory(donor.memory_id)['completed_work_item_events']['old']
        (self.events/(event+'.json')).unlink()
        with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item('old',instance_id='one')

    def test_C8_D1_new_only_control_and_multihop_quarantine_remain_valid(self):
        donor,target=self.mixed_merge_fixture('revise',inherited=False)
        last=store.create_memory('fact','last',instance_id='one')
        store.merge_duplicate_memories(last.memory_id,target.memory_id,instance_id='one')
        store.revise_memory(last.memory_id,content='third',source_work_item_ids=['old','new','third'],instance_id='one')
        store.quarantine_memory(last.memory_id,reason='fixture',actor='test',instance_id='one')
        for work,expected in [('old',donor.memory_id),('new',target.memory_id),('third',last.memory_id)]:
            self.assertEqual(store.find_memory_by_work_item(work,instance_id='one')['memory_id'],expected)

    def test_C8_D1_actual_worker_recovers_donor_after_mixed_work_history(self):
        item,path=self.accepted_item('unused');work=item['work_item_id']
        donor=self.create(source_work_item_ids=[work])
        target=store.create_memory('fact','survivor',instance_id='one')
        store.merge_duplicate_memories(target.memory_id,donor.memory_id,instance_id='one')
        store.revise_memory(target.memory_id,content='later',source_work_item_ids=[work,'other-new-work'],instance_id='one')
        before={str(p):p.read_bytes() for p in self.root.rglob('*.json')}
        self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'consolidated')
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*.json')})
        self.assertEqual(store.find_memory_by_work_item(work,instance_id='one')['memory_id'],donor.memory_id)

    def test_C7_D1_competing_revision_restored_to_preimage_cannot_disappear(self):
        item,path=self.accepted_item('revision');work=item['work_item_id']
        first=self.create(source_work_item_ids=[work])
        second=store.create_memory('fact','second operation',instance_id='one')
        target=self.records/(second.memory_id+'.json');preimage=target.read_bytes()
        store.revise_memory(second.memory_id,content='revised second',source_work_item_ids=[work],instance_id='one')
        self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'review')
        target.write_bytes(preimage)
        worker.update_work_item(work,status='accepted',path=path)
        before={str(p):p.read_bytes() for p in self.root.rglob('*.json')}
        self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'review')
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*.json')})
        self.assertEqual(store.load_memory(first.memory_id)['content'],'original')

    def test_C7_D1_each_supersession_half_stays_required_with_another_completed_result(self):
        for reuse,change in ((False,True),(True,True),(True,False)):
            item,path,old,preimage,retirement,record,completion=self.supersession_fixture(reuse,change)
            store.create_memory('fact','independent completed result',instance_id='one',source_work_item_ids=[item['work_item_id']])
            targets=[(old,preimage),(self.records/(record['memory_id']+'.json'),None),
                     (retirement,None),(self.events/(completion['event_id']+'.json'),None)]
            mutation_id=completion['data']['replacement_change']['event_id']
            if mutation_id:targets.append((self.events/(mutation_id+'.json'),None))
            for target,restored in targets:
                with self.subTest(reuse=reuse,change=change,target=target.name):
                    original=target.read_bytes()
                    if restored is None:target.unlink()
                    else:target.write_bytes(restored)
                    worker.update_work_item(item['work_item_id'],status='accepted',path=path)
                    before={str(p):p.read_bytes() for p in self.root.rglob('*.json')}
                    self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'review')
                    self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*.json')})
                    target.write_bytes(original)
            for p in list(self.records.glob('*.json'))+list(self.events.glob('*.json')):p.unlink()

    def test_C7_D1_mixed_old_and_new_work_declares_only_the_new_completion(self):
        first=self.create(source_work_item_ids=['old'])
        store.revise_memory(first.memory_id,content='updated',instance_id='one',source_work_item_ids=['old','new'])
        record=store.load_memory(first.memory_id)
        event=next(e for e in store.list_memory_events(first.memory_id) if e['event_id']==record['completed_work_item_events']['new'])
        self.assertEqual(event['data']['completed_work_item_ids'],['new'])
        for work in ('old','new'):
            self.assertEqual(store.find_memory_by_work_item(work,instance_id='one')['memory_id'],first.memory_id)
        original=(self.events/(event['event_id']+'.json')).read_bytes()
        for invalid in (['old','new'],['old'],[],None,['new','new'],['unrelated'],[1]):
            value=json.loads(original);value['data']['completed_work_item_ids']=invalid
            (self.events/(event['event_id']+'.json')).write_text(json.dumps(value))
            with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item('new' if invalid!=['old','new'] else 'old',instance_id='one')
        (self.events/(event['event_id']+'.json')).write_bytes(original)

    def test_C7_D1_inherited_merge_chain_is_valid_but_missing_or_cyclic_donor_is_not(self):
        donor=self.create(source_work_item_ids=['work'])
        middle=store.create_memory('fact','middle',instance_id='one')
        target=store.create_memory('fact','last',instance_id='one')
        store.merge_duplicate_memories(middle.memory_id,donor.memory_id,instance_id='one')
        store.merge_duplicate_memories(target.memory_id,middle.memory_id,instance_id='one')
        store.quarantine_memory(target.memory_id,reason='fixture',actor='test',instance_id='one')
        self.assertEqual(store.find_memory_by_work_item('work',instance_id='one')['memory_id'],donor.memory_id)
        event=next(e for e in store.list_memory_events(middle.memory_id) if e.get('data',{}).get('inherited_from_memory_id'))
        path=self.events/(event['event_id']+'.json');original=path.read_bytes()
        for altered in (None,'missing-record',target.memory_id):
            value=json.loads(original)
            if altered is None:del value['data']['inherited_from_memory_id']
            else:value['data']['inherited_from_memory_id']=altered
            path.write_text(json.dumps(value))
            with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item('work',instance_id='one')
        path.write_bytes(original)
        self.assertEqual(store.find_memory_by_work_item('work',instance_id='one')['memory_id'],donor.memory_id)

    def test_C7_D1_merge_record_preimage_and_unknown_legacy_work_cannot_borrow_completion(self):
        donor=self.create(source_work_item_ids=['work'])
        target=store.create_memory('fact','target',instance_id='one')
        target_path=self.records/(target.memory_id+'.json');preimage=target_path.read_bytes()
        store.merge_duplicate_memories(target.memory_id,donor.memory_id,instance_id='one')
        postimage=target_path.read_bytes();target_path.write_bytes(preimage)
        with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item('work',instance_id='one')
        target_path.write_bytes(postimage)
        unknown=store.create_memory('fact','legacy work',instance_id='one')
        path=self.records/(unknown.memory_id+'.json');value=json.loads(path.read_text())
        value['source_work_item_ids']=['work'];path.write_text(json.dumps(value))
        with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item('work',instance_id='one')

    def test_C7_D1_unbound_retirement_cannot_be_ignored_beside_a_completed_record(self):
        self.create(source_work_item_ids=['work'])
        old=store.create_memory('fact','other previous',instance_id='one')
        replacement=store.create_memory('fact','other replacement',instance_id='one')
        store.mark_memory_superseded(old.memory_id,superseded_by=replacement.memory_id,instance_id='one',source_work_item_ids=['work'])
        with self.assertRaisesRegex(store.IncompleteMemoryMutation,'Retained retirement'):
            store.find_memory_by_work_item('work',instance_id='one')

    def supersession_fixture(self,reuse=True,change=True):
        item,path=self.accepted_item('replacement')
        old=self.create();old_path=self.records/(old.memory_id+'.json');old_bytes=old_path.read_bytes()
        target=store.create_memory('fact','replacement',instance_id='one') if reuse else None
        result=store.supersede_memory(old.memory_id,'fact','replacement',instance_id='one',
            source_work_item_ids=[item['work_item_id']],source_message_ids=['m-new'] if change else [])
        if target:self.assertEqual(result.memory_id,target.memory_id)
        record=store.load_memory(result.memory_id)
        completion=next(e for e in store.list_memory_events(result.memory_id) if e['event_type']=='supersession_completed')
        retirement=self.events/(completion['data']['retirement_event_id']+'.json')
        self.assertIn(item['work_item_id'],result.source_work_item_ids)
        return item,path,old_path,old_bytes,retirement,record,completion

    def test_C6_D1_both_replacement_mutations_require_their_exact_event(self):
        for reuse in [False,True]:
            item,path,old,preimage,retirement,record,completion=self.supersession_fixture(reuse)
            change=completion['data']['replacement_change']
            self.assertEqual(change['kind'],'strengthened' if reuse else 'created')
            event=self.events/(change['event_id']+'.json');original=event.read_bytes()
            for alteration in ['missing','changed-data','other-owner','wrong-type']:
                with self.subTest(reuse=reuse,alteration=alteration):
                    event.write_bytes(original)
                    if alteration=='missing':event.unlink()
                    else:
                        value=json.loads(original)
                        if alteration=='changed-data':value['data']['synthetic-change']='not retained original'
                        if alteration=='other-owner':value['instance_id']='other'
                        if alteration=='wrong-type':value['event_type']='quarantined'
                        event.write_text(json.dumps(value))
                    worker.update_work_item(item['work_item_id'],status='accepted',path=path)
                    self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'review')
            event.write_bytes(original)
            worker.update_work_item(item['work_item_id'],status='accepted',path=path)
            self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'consolidated')
            for p in list(self.records.glob('*.json'))+list(self.events.glob('*.json')):p.unlink()

    def test_C6_D1_unchanged_reuse_has_explicit_no_mutation_proof_and_no_fake_event(self):
        item,path,old,preimage,retirement,record,completion=self.supersession_fixture(True,False)
        self.assertEqual(completion['data']['replacement_change'],{'kind':'unchanged_reuse','event_id':None,'event_sha256':None})
        self.assertFalse(any(e['event_type']=='strengthened' for e in store.list_memory_events(record['memory_id'])))
        self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'consolidated')
        before={str(p):p.read_bytes() for p in self.root.rglob('*.json')}
        self.assertEqual(store.find_memory_by_work_item(item['work_item_id'],instance_id='one')['memory_id'],record['memory_id'])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*.json')})

    def test_C6_D1_missing_replacement_declaration_cannot_default_to_unchanged_reuse(self):
        item,path,old,preimage,retirement,record,completion=self.supersession_fixture()
        event=self.events/(completion['event_id']+'.json');original=event.read_bytes()
        changes=[None,{}, {'kind':'created','event_id':None,'event_sha256':None},
                 {'kind':'unchanged_reuse','event_id':'unexpected','event_sha256':None},
                 {'kind':[],'event_id':None,'event_sha256':None}]
        for change in changes:
            value=json.loads(original);value['data']['replacement_change']=change;event.write_text(json.dumps(value))
            worker.update_work_item(item['work_item_id'],status='accepted',path=path)
            self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'review')
        event.write_bytes(original)

    def test_C6_D1_every_supersession_record_and_event_half_is_required(self):
        for reuse,change in [(False,True),(True,True),(True,False)]:
            item,path,old,preimage,retirement,record,completion=self.supersession_fixture(reuse,change)
            targets=[old,self.records/(record['memory_id']+'.json'),retirement,self.events/(completion['event_id']+'.json')]
            if completion['data']['replacement_change']['event_id']:
                targets.append(self.events/(completion['data']['replacement_change']['event_id']+'.json'))
            for target in targets:
                with self.subTest(reuse=reuse,change=change,target=target.name):
                    raw=target.read_bytes();target.unlink()
                    worker.update_work_item(item['work_item_id'],status='accepted',path=path)
                    before={str(p):p.read_bytes() for p in self.root.rglob('*.json')}
                    self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'review')
                    self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*.json')})
                    target.write_bytes(raw)
            for p in list(self.records.glob('*.json'))+list(self.events.glob('*.json')):p.unlink()

    def test_C6_D1_orphan_ordinary_creation_event_is_review_not_duplicate_create(self):
        item,path=self.accepted_item('unused');memory=self.create(source_work_item_ids=[item['work_item_id']])
        (self.records/(memory.memory_id+'.json')).unlink()
        before={str(p):p.read_bytes() for p in self.events.glob('*.json')}
        self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'review')
        self.assertEqual(list(self.records.glob('*.json')),[])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.events.glob('*.json')})

    def test_C6_D1_later_changes_do_not_replace_operation_event_bindings(self):
        item,path,old,preimage,retirement,record,completion=self.supersession_fixture()
        original_change=completion['data']['replacement_change']
        store.revise_memory(record['memory_id'],content='legitimate later revision',instance_id='one',source_work_item_ids=['later'])
        self.assertEqual(store.find_memory_by_work_item(item['work_item_id'],instance_id='one')['content'],'legitimate later revision')
        (self.events/(original_change['event_id']+'.json')).unlink()
        with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item(item['work_item_id'],instance_id='one')
        self.assertIsNotNone(store.find_memory_by_work_item('later',instance_id='one'))

    def test_C6_D1_unchanged_reuse_recovers_every_durable_boundary(self):
        for stop in range(1,6):
            item,path=self.accepted_item('replacement');old=self.create()
            target=store.create_memory('fact','replacement',instance_id='one')
            write=mutation.durable_write;count=0
            def interrupt(path,text):
                nonlocal count
                write(path,text);count+=1
                if count==stop:raise OSError('synthetic unchanged reuse interruption')
            with patch.object(mutation,'durable_write',side_effect=interrupt),self.assertRaises(OSError):
                store.supersede_memory(old.memory_id,'fact','replacement',instance_id='one',source_work_item_ids=[item['work_item_id']])
            self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'consolidated')
            self.assertEqual(store.find_memory_by_work_item(item['work_item_id'],instance_id='one')['memory_id'],target.memory_id)
            for p in list(self.records.glob('*.json'))+list(self.events.glob('*.json')):p.unlink()

    def test_C5_D1_both_replacement_branches_require_exact_retirement_on_worker_recovery(self):
        for reuse in [False,True]:
            with self.subTest(reuse=reuse):
                item,path,old,preimage,retirement,record,completion=self.supersession_fixture(reuse)
                postimage=old.read_bytes();event_bytes=retirement.read_bytes()
                mutations=['missing-event','old-active','old-wrong-target','missing-old','foreign-owner','wrong-replacement','wrong-work','wrong-type']
                for changed in mutations:
                    with self.subTest(changed=changed):
                        old.write_bytes(postimage);retirement.write_bytes(event_bytes)
                        if changed=='missing-event':retirement.unlink()
                        elif changed=='old-active':old.write_bytes(preimage)
                        elif changed=='old-wrong-target':
                            value=json.loads(postimage);value['superseded_by']='wrong';old.write_text(json.dumps(value))
                        elif changed=='missing-old':old.unlink()
                        else:
                            value=json.loads(event_bytes)
                            if changed=='foreign-owner':value['instance_id']='other'
                            elif changed=='wrong-replacement':value['data']['superseded_by']='another'
                            elif changed=='wrong-work':value['source_work_item_ids']=[]
                            elif changed=='wrong-type':value['event_type']='quarantined'
                            retirement.write_text(json.dumps(value))
                        worker.update_work_item(item['work_item_id'],status='accepted',path=path)
                        before={str(p):p.read_bytes() for p in self.root.rglob('*.json')}
                        result=worker.apply_next_accepted(instance_id='one',path=path)
                        self.assertEqual(result['status'],'review')
                        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*.json')})
                old.write_bytes(postimage);retirement.write_bytes(event_bytes)
                worker.update_work_item(item['work_item_id'],status='accepted',path=path)
                result=worker.apply_next_accepted(instance_id='one',path=path)
                self.assertEqual(result['status'],'consolidated')
                self.assertEqual(result['resulting_memory_ids'],[record['memory_id']])
                # Restore a distinct store for the other replacement branch.
                for p in list(self.records.glob('*.json'))+list(self.events.glob('*.json')):p.unlink()

    def test_C5_D1_malformed_or_missing_completion_declaration_stays_review(self):
        item,path,old,preimage,retirement,record,event=self.supersession_fixture()
        event_path=self.events/(event['event_id']+'.json');original=event_path.read_bytes()
        for field,value in [('retired_memory_id',None),('retirement_event_id',[]),
                            ('replacement_memory_id','wrong'),('work_completion_kind',None)]:
            value_event=json.loads(original);value_event['data'][field]=value
            event_path.write_text(json.dumps(value_event))
            worker.update_work_item(item['work_item_id'],status='accepted',path=path)
            self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'review')
        event_path.write_bytes(original)
        self.assertIsNotNone(store.find_memory_by_work_item(item['work_item_id'],instance_id='one'))

    def test_C5_D1_historical_strengthening_cannot_be_assumed_complete_supersession(self):
        item,path=self.accepted_item('unused')
        memory=self.create();store.strengthen_memory(memory.memory_id,confidence=.5,
            instance_id='one',source_work_item_ids=[item['work_item_id']])
        event_id=store.load_memory(memory.memory_id)['completed_work_item_events'][item['work_item_id']]
        target=self.events/(event_id+'.json');value=json.loads(target.read_text())
        del value['data']['work_completion_kind'];target.write_text(json.dumps(value))
        before=target.read_bytes()
        self.assertEqual(worker.apply_next_accepted(instance_id='one',path=path)['status'],'review')
        self.assertEqual(target.read_bytes(),before)

    def test_C5_D1_valid_retirement_completion_survives_later_quarantine_and_merge(self):
        item,path,old,preimage,retirement,record,event=self.supersession_fixture()
        target=store.create_memory('fact','final merge',instance_id='one')
        store.merge_duplicate_memories(target.memory_id,record['memory_id'],instance_id='one')
        store.quarantine_memory(target.memory_id,reason='fixture',actor='test',instance_id='one')
        self.assertEqual(store.find_memory_by_work_item(item['work_item_id'],instance_id='one')['memory_id'],record['memory_id'])
        retirement.unlink()
        with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item(item['work_item_id'],instance_id='one')

    def test_C5_D1_existing_work_cannot_be_rebound_to_a_second_retirement(self):
        item,path,old,preimage,retirement,record,event=self.supersession_fixture()
        another=store.create_memory('fact','second old',instance_id='one')
        before={str(p):p.read_bytes() for p in self.root.rglob('*.json')}
        with self.assertRaises(store.IncompleteMemoryMutation):
            store.supersede_memory(another.memory_id,'fact','replacement',instance_id='one',source_work_item_ids=[item['work_item_id']])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*.json')})

    def test_C5_D1_reused_replacement_recovers_every_durable_boundary(self):
        for stop in range(1,7):
            item,path=self.accepted_item('replacement')
            old=self.create();target=store.create_memory('fact','replacement',instance_id='one')
            write=mutation.durable_write;count=0
            def interrupt(path,text):
                nonlocal count
                write(path,text);count+=1
                if count==stop:raise OSError('synthetic reused supersession publication boundary')
            with patch.object(mutation,'durable_write',side_effect=interrupt),self.assertRaises(OSError):
                store.supersede_memory(old.memory_id,'fact','replacement',instance_id='one',
                    source_message_ids=['new-evidence'],source_work_item_ids=[item['work_item_id']])
            result=worker.apply_next_accepted(instance_id='one',path=path)
            self.assertEqual(result['status'],'consolidated')
            self.assertEqual(result['resulting_memory_ids'],[target.memory_id])
            self.assertEqual(store.load_memory(old.memory_id)['superseded_by'],target.memory_id)
            before={str(p):p.read_bytes() for p in self.root.rglob('*.json')}
            self.assertEqual(store.find_memory_by_work_item(item['work_item_id'],instance_id='one')['memory_id'],target.memory_id)
            self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*.json')})
            for p in list(self.records.glob('*.json'))+list(self.events.glob('*.json')):p.unlink()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.records=self.root/'records';self.events=self.root/'events'
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.multiple(store,MEMORY_RECORDS_DIR=self.records,MEMORY_EVENTS_DIR=self.events))
        self.raw=self.root/'raw';self.meta=self.root/'meta';self.raw.mkdir();self.meta.mkdir()
        stack.enter_context(patch.multiple(canonical,RAW_DIR=self.raw,META_DIR=self.meta))

    def create(self,**kwargs):
        return store.create_memory('fact','original',instance_id='one',confidence=.5,**kwargs)

    def partial(self):
        memory=self.create()
        path=self.records/(memory.memory_id+'.json');value=json.loads(path.read_text())
        value['content']='interrupted revision';value['source_work_item_ids']=['lost-work']
        path.write_text(json.dumps(value))
        return memory

    def test_D1_quarantine_does_not_turn_provenance_into_completion(self):
        memory=self.partial()
        with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item('lost-work',instance_id='one')
        store.quarantine_memory(memory.memory_id,reason='keep out of retrieval',actor='fixture',instance_id='one')
        self.assertTrue(any('lost-work' in e['source_work_item_ids'] for e in store.list_memory_events(memory.memory_id)))
        with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item('lost-work',instance_id='one')
        with patch.object(worker,'claim_next_work_item',return_value={'work_item_id':'lost-work'}),patch.object(worker,'update_work_item',side_effect=lambda key,**v:v):
            self.assertEqual(worker.apply_next_accepted(instance_id='one')['status'],'review')

    def test_D1_later_strengthen_and_duplicate_merge_cannot_repair_unknown_work(self):
        memory=self.partial()
        store.strengthen_memory(memory.memory_id,confidence=.9,source_message_ids=['new'],source_work_item_ids=['lost-work'],instance_id='one')
        with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item('lost-work',instance_id='one')
        target=store.create_memory('fact','merge target',instance_id='one')
        store.merge_duplicate_memories(target.memory_id,memory.memory_id,instance_id='one')
        merged=store.load_memory(target.memory_id)
        self.assertIn('lost-work',merged['source_work_item_ids'])
        self.assertNotIn('lost-work',merged.get('completed_work_item_events',{}))
        with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item('lost-work',instance_id='one')

    def test_D1_exact_new_operation_event_is_required_and_survives_other_events(self):
        memory=self.create(source_work_item_ids=['created-work'])
        store.revise_memory(memory.memory_id,content='new',source_work_item_ids=['revision-work'],instance_id='one')
        current=store.load_memory(memory.memory_id)
        mapping=current['completed_work_item_events'];self.assertNotEqual(mapping['created-work'],mapping['revision-work'])
        store.quarantine_memory(memory.memory_id,reason='test',actor='fixture',instance_id='one')
        self.assertEqual(store.find_memory_by_work_item('revision-work',instance_id='one')['memory_id'],memory.memory_id)
        (self.events/(mapping['revision-work']+'.json')).unlink()
        with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item('revision-work',instance_id='one')
        self.assertEqual(store.find_memory_by_work_item('created-work',instance_id='one')['memory_id'],memory.memory_id)

    def test_D2_replay_syncs_already_renamed_event_before_discarding_intent(self):
        memory=self.create();sync=mutation._sync_directory
        def crash(directory):
            if directory==self.events:raise OSError('after event rename before directory sync')
            return sync(directory)
        with patch.object(mutation,'_sync_directory',side_effect=crash),self.assertRaises(OSError):
            store.revise_memory(memory.memory_id,content='revised',source_work_item_ids=['work'],instance_id='one')
        pending=self.records/'.pending-mutation.json';self.assertTrue(pending.exists())
        observed=[]
        def observe(directory):
            observed.append((directory,pending.exists()));return sync(directory)
        with patch.object(mutation,'_sync_directory',side_effect=observe):
            recovered=store.find_memory_by_work_item('work',instance_id='one')
        self.assertEqual(recovered['content'],'revised')
        self.assertIn((self.events,True),observed);self.assertFalse(pending.exists())

    def message(self,archive,mid,owner,text,at):
        (self.raw/(archive+'.json')).write_text(json.dumps({'message_id':mid,'role':'user','text':text}))
        (self.meta/(archive+'.json')).write_text(json.dumps({'archive_id':archive,'raw_file':archive+'.json',
            'capture_type':'message_state','conversation_id':'conversation','instance_id':owner,'created_at':at}))

    def test_D3_same_conversation_owner_filtered_before_revision_and_evaluation(self):
        self.message('own','same','one','own fact','2026-09-01T00:00:00+00:00')
        self.message('foreign','same','two','foreign fact','2026-09-01T00:01:00+00:00')
        self.message('foreign-other','other','two','foreign supporting fact','2026-09-01T00:02:00+00:00')
        item={'instance_id':'one','conversation_id':'conversation','message_id':'same','canonical_revision':'own',
              'candidate_content':'own fact','source_archive_ids':['own'],'work_item_id':'work'}
        context=worker._context(item)
        self.assertEqual([v['content'] for v in context],['own fact'])
        self.assertEqual(context[0]['instance_id'],'one')
        evaluator=Mock();evaluator.evaluate.return_value=SemanticMemoryAssessment(False,None,None,0,0,'not durable')
        with patch.object(worker,'claim_next_work_item',return_value=item),patch.object(worker,'update_work_item',side_effect=lambda key,**v:v):
            worker.evaluate_next(instance_id='one',evaluator=evaluator)
        self.assertEqual(evaluator.evaluate.call_args.kwargs['conversation_context'],context)
        forged=SemanticMemoryAssessment(True,'fact','claim',.9,.8,'reason',supporting_message_ids=('same','other'),supporting_archive_ids=('own','foreign-other'))
        with self.assertRaises(worker.EvidenceAttributionError):worker._validated_evidence(item,forged,context)
        self.message('recaptured','same','one','changed own fact','2026-09-01T00:03:00+00:00')
        with self.assertRaisesRegex(worker.EvidenceAttributionError,'revision changed'):worker._context(item)

    def test_D3_unknown_or_foreign_context_is_rejected_before_provider(self):
        for owner in ['two',None]:
            item={'work_item_id':'work','instance_id':'one','candidate_content':'a meaningful preference',
                  'conversation_id':'conversation','message_id':'same','source_archive_ids':['own']}
            evaluator=Mock()
            with patch.object(worker,'claim_next_work_item',return_value=item),patch.object(worker,'build_archive_context',return_value=({'instance_id':owner},)),patch.object(worker,'update_work_item',side_effect=lambda key,**v:v):
                result=worker.evaluate_next(instance_id='one',evaluator=evaluator)
            self.assertEqual(result['status'],'review');evaluator.evaluate.assert_not_called()

    def test_D3_legacy_collision_is_not_silently_assigned_to_current_owner(self):
        self.message('own','same','one','own','2026-09-01T00:00:00+00:00')
        self.message('legacy','same',None,'legacy','2026-09-01T00:01:00+00:00')
        with self.assertRaisesRegex(ValueError,'migration'):canonical.canonical_messages('conversation',instance_id='one',include_unscoped=True)

    def test_D4_development_owner_reaches_both_provider_inputs(self):
        proposals=self.root/'development';proposals.mkdir()
        for owner in ['one','two',None]:
            (proposals/(str(owner)+'.json')).write_text(json.dumps({'instance_id':owner,'observation':'workflow improvement','proposal_id':str(owner)}))
        similarity=Mock();similarity.rank.side_effect=lambda **v:v['proposals']
        evaluator=Mock();evaluator.evaluate.return_value=None
        with patch.object(development_retrieval,'DEVELOPMENT_DIR',proposals):
            result=development_runtime.process_development_experience('workflow improvement',instance_id='one',evaluator=evaluator,similarity=similarity)
        self.assertEqual([r['instance_id'] for r in similarity.rank.call_args.kwargs['proposals']],['one'])
        self.assertEqual([r['instance_id'] for r in evaluator.evaluate.call_args.kwargs['prior_development']],['one'])
        self.assertIsNone(result['record'])

    def test_D5_new_attribution_for_known_message_does_not_inflate_confidence(self):
        memory=self.create(source_message_ids=['known'])
        enriched=store.strengthen_memory(memory.memory_id,instance_id='one',confidence=.5,
            source_message_ids=['known'],source_archive_ids=['new-attribution'],source_work_item_ids=['new-work'])
        self.assertEqual(enriched['confidence'],.5);self.assertEqual(enriched['source_archive_ids'],['new-attribution'])
        independent=store.strengthen_memory(memory.memory_id,instance_id='one',confidence=.5,source_message_ids=['new-message'],source_archive_ids=['independent'])
        self.assertEqual(independent['confidence'],.75)

    def test_D6_legacy_mutation_requires_review_not_endless_retry(self):
        self.message('archive','candidate','one','Synthetic eligible legacy evidence','2026-09-01T00:00:00+00:00')
        legacy=store.create_memory('fact','legacy memory',legacy_unscoped=True)
        item={'work_item_id':'work','instance_id':'one','message_id':'candidate','canonical_revision':'archive',
              'source_archive_ids':['archive'],'conversation_id':'conversation'}
        assessment=SemanticMemoryAssessment(True,'fact','legacy memory',.9,.8,'reason',supporting_message_ids=('candidate',),supporting_archive_ids=('archive',))
        with patch.object(worker,'claim_next_work_item',return_value=item),patch.object(worker,'_assessment_from_item',return_value=assessment),patch.object(worker,'_context',return_value=()),patch.object(worker,'retrieve_memories',return_value=[store.load_memory(legacy.memory_id)]),patch.object(worker,'update_work_item',side_effect=lambda key,**v:v):
            result=worker.apply_next_accepted(instance_id='one',include_unscoped=True)
        self.assertEqual(result['status'],'review');self.assertIn('migration decision',result['decision_reason'])
        self.assertIsNone(store.load_memory(legacy.memory_id)['instance_id'])
        self.assertEqual(store.list_memories(instance_id='one'),[])


    def test_C2_D1_parent_entries_synced_before_first_intent(self):
        records=self.root/'new'/'nested'/'records';events=self.root/'different'/'deep'/'events'
        trace=[];sync=mutation._sync_directory;write=mutation.durable_write
        def synchronized(path):trace.append(('sync',path));return sync(path)
        def written(path,text):trace.append(('write',path));return write(path,text)
        with patch.multiple(store,MEMORY_RECORDS_DIR=records,MEMORY_EVENTS_DIR=events),patch.object(mutation,'_sync_directory',side_effect=synchronized),patch.object(mutation,'durable_write',side_effect=written):
            memory=self.create(source_work_item_ids=['work'])
        first=trace.index(('write',records/'.pending-mutation.json'))
        for parent in set(records.parents)|set(events.parents):self.assertIn(('sync',parent),trace[:first])
        self.assertTrue((records/(memory.memory_id+'.json')).is_file())

    def test_C2_D1_interrupted_mkdir_is_fenced_on_retry_before_success(self):
        records=self.root/'new'/'records';events=self.root/'new'/'events';sync=mutation._sync_directory
        with patch.multiple(store,MEMORY_RECORDS_DIR=records,MEMORY_EVENTS_DIR=events):
            def fail(path):
                if path==records.parent:raise OSError('directory entry not yet durable')
                return sync(path)
            with patch.object(mutation,'_sync_directory',side_effect=fail),self.assertRaises(OSError):self.create()
            self.assertTrue(records.is_dir());self.assertEqual(list(records.iterdir()),[])
            trace=[]
            def observe(path):trace.append(path);return sync(path)
            with patch.object(mutation,'_sync_directory',side_effect=observe):self.create(source_work_item_ids=['work'])
            self.assertIn(records.parent,trace)
            self.assertIsNotNone(store.find_memory_by_work_item('work',instance_id='one'))

    def test_C2_D2_legacy_discovery_requires_review_without_provider_or_owner_rewrite(self):
        self.message('legacy','m',None,'A meaningful retained personal preference','2026-09-01T00:00:00+00:00')
        for history in [False,True]:
            path=self.root/('history.sqlite' if history else 'conversation.sqlite')
            if history:
                with patch.object(worker,'list_conversation_ids',return_value=['conversation']):items=worker.discover_history(instance_id='one',include_unscoped=True,path=path)
            else:items=worker.discover_conversation('conversation',instance_id='one',include_unscoped=True,path=path)
            self.assertEqual(len(items),1);self.assertEqual(items[0]['status'],'review')
            self.assertIn('ownership/migration decision',items[0]['decision_reason'])
            evaluator=Mock();self.assertIsNone(worker.evaluate_next(instance_id='one',evaluator=evaluator,path=path));evaluator.evaluate.assert_not_called()
            reloaded=worker.get_work_item(items[0]['work_item_id'],path=path)
            self.assertEqual(reloaded['status'],'review');self.assertEqual(reloaded['source_archive_ids'],['legacy'])
        self.assertIsNone(json.loads((self.meta/'legacy.json').read_text())['instance_id'])

    def test_C2_D2_preexisting_queued_legacy_becomes_review_on_recovery(self):
        self.message('legacy','m',None,'A meaningful retained personal preference','2026-09-01T00:00:00+00:00')
        path=self.root/'old.sqlite'
        item=worker.discover_candidate(instance_id='one',conversation_id='conversation',message_id='m',canonical_revision='legacy',
            source_archive_ids=['legacy'],candidate_content='A meaningful retained personal preference',path=path)
        worker.update_work_item(item['work_item_id'],status='queued',path=path)
        evaluator=Mock();result=worker.evaluate_next(instance_id='one',evaluator=evaluator,path=path)
        self.assertEqual(result['status'],'review');evaluator.evaluate.assert_not_called()
        self.assertIsNone(worker.evaluate_next(instance_id='one',evaluator=evaluator,path=path))
        # Previously accepted items also cannot remain in consolidation retry.
        worker.update_work_item(item['work_item_id'],status='accepted',path=path)
        assessment=SemanticMemoryAssessment(True,'fact','a preference',.9,.8,'reason',supporting_message_ids=('m',),supporting_archive_ids=('legacy',))
        with patch.object(worker,'_assessment_from_item',return_value=assessment):result=worker.apply_next_accepted(instance_id='one',path=path)
        self.assertEqual(result['status'],'review');self.assertEqual(store.list_memories(instance_id='one'),[])

    def test_C2_D3_merge_retains_donor_completion_independent_of_iteration_order(self):
        donor=self.create(source_work_item_ids=['work']);target=store.create_memory('fact','distinct merge survivor',instance_id='one')
        store.merge_duplicate_memories(target.memory_id,donor.memory_id,instance_id='one')
        listing=store.list_memories
        for first in [donor.memory_id,target.memory_id]:
            def ordered(**kwargs):return sorted(listing(**kwargs),key=lambda v:v['memory_id']!=first)
            with patch.object(store,'list_memories',side_effect=ordered):
                self.assertEqual(store.find_memory_by_work_item('work',instance_id='one')['memory_id'],donor.memory_id)
        store.quarantine_memory(target.memory_id,reason='fixture',actor='test',instance_id='one')
        self.assertEqual(store.find_memory_by_work_item('work',instance_id='one')['memory_id'],donor.memory_id)
        event=store.load_memory(donor.memory_id)['completed_work_item_events']['work']
        (self.events/(event+'.json')).unlink()
        with self.assertRaises(store.IncompleteMemoryMutation):store.find_memory_by_work_item('work',instance_id='one')

    def test_C2_D3_conflicting_completed_operations_are_not_arbitrarily_selected(self):
        self.create(source_work_item_ids=['work']);store.create_memory('fact','different operation',instance_id='one',source_work_item_ids=['work'])
        with self.assertRaisesRegex(store.IncompleteMemoryMutation,'multiple completed'):store.find_memory_by_work_item('work',instance_id='one')


    def pending_revision(self,work='pending-work'):
        memory=self.create();pending=self.records/'.pending-mutation.json';sync=mutation._sync_directory
        def fail(path):
            if path==self.records and pending.exists():raise OSError('intent renamed before directory fsync')
            return sync(path)
        with patch.object(mutation,'_sync_directory',side_effect=fail),self.assertRaises(OSError):
            store.revise_memory(memory.memory_id,content='new complete content',source_work_item_ids=[work],instance_id='one')
        self.assertTrue(pending.exists())
        return memory,pending

    def test_C3_D1_replay_fences_intent_before_any_postimage_and_keeps_it_on_failure(self):
        memory,pending=self.pending_revision();before={p:p.read_bytes() for d in (self.records,self.events) for p in d.glob('*.json')}
        sync=mutation._sync_directory
        def fail(path):
            if path==self.records:raise OSError('intent fence still unavailable')
            return sync(path)
        with patch.object(mutation,'_sync_directory',side_effect=fail),patch.object(mutation,'durable_write') as writes,self.assertRaises(OSError):
            store.find_memory_by_work_item('pending-work',instance_id='one')
        writes.assert_not_called();self.assertTrue(pending.exists())
        self.assertEqual(before,{p:p.read_bytes() for d in (self.records,self.events) for p in d.glob('*.json')})
        trace=[];write=mutation.durable_write
        def synced(path):trace.append(('sync',path));return sync(path)
        def written(path,text):trace.append(('write',path));return write(path,text)
        with patch.object(mutation,'_sync_directory',side_effect=synced),patch.object(mutation,'durable_write',side_effect=written):
            recovered=store.find_memory_by_work_item('pending-work',instance_id='one')
        first=next(i for i,v in enumerate(trace) if v[0]=='write')
        self.assertIn(('sync',self.records),trace[:first]);self.assertFalse(pending.exists())
        self.assertEqual(recovered['content'],'new complete content')

    def accepted_item(self,work):
        path=self.root/'queue.sqlite'
        item=worker.discover_candidate(instance_id='one',conversation_id='conversation',message_id='m',canonical_revision='archive',candidate_content='original',path=path)
        # Use the actual generated work ID in the pending operation.
        worker.update_work_item(item['work_item_id'],status='accepted',path=path)
        return item,path

    def test_C3_D2_actual_conflict_enters_review_and_does_not_replay_automatically(self):
        item,path=self.accepted_item('unused');memory,pending=self.pending_revision(item['work_item_id'])
        record=self.records/(memory.memory_id+'.json');value=json.loads(record.read_text());value['content']='uncoordinated change';record.write_text(json.dumps(value))
        record_before=record.read_bytes();intent_before=pending.read_bytes()
        result=worker.apply_next_accepted(instance_id='one',path=path)
        self.assertEqual(result['status'],'review');self.assertIn('conflicts',result['decision_reason'])
        self.assertIsNone(worker.apply_next_accepted(instance_id='one',path=path))
        self.assertEqual(worker.get_work_item(item['work_item_id'],path=path)['status'],'review')
        self.assertEqual(record.read_bytes(),record_before);self.assertEqual(pending.read_bytes(),intent_before)

    def test_C3_D2_malformed_or_wrong_root_intent_is_review_not_retry(self):
        for corrupt in ['{', '[]', '{"roots":[],"writes":[],"sha256":"wrong"}']:
            with self.subTest(corrupt=corrupt):
                item,path=self.accepted_item('unused')
                pending=self.records/'.pending-mutation.json';self.records.mkdir(exist_ok=True);pending.write_text(corrupt)
                result=worker.apply_next_accepted(instance_id='one',path=path)
                self.assertEqual(result['status'],'review');self.assertEqual(pending.read_text(),corrupt)
                pending.unlink()
                # Preserve each real work record; create the next fixture database separately.
                self.root=self.root/'next';self.root.mkdir()

    def test_C3_D2_transient_io_remains_retryable_and_valid_intent_recovers(self):
        item,path=self.accepted_item('unused');memory,pending=self.pending_revision(item['work_item_id']);sync=mutation._sync_directory
        def fail(directory):
            if directory==self.records:raise OSError('temporary fsync failure')
            return sync(directory)
        with patch.object(mutation,'_sync_directory',side_effect=fail):result=worker.apply_next_accepted(instance_id='one',path=path)
        self.assertEqual(result['status'],'failed_consolidation_retryable');self.assertTrue(pending.exists())
        recovered=worker.apply_next_accepted(instance_id='one',path=path)
        self.assertEqual(recovered['status'],'consolidated');self.assertFalse(pending.exists())
        self.assertEqual(recovered['resulting_memory_ids'],[memory.memory_id])

    def test_C3_D2_unreadable_record_or_event_is_not_treated_as_absence(self):
        item,path=self.accepted_item('unused');memory=self.create(source_work_item_ids=[item['work_item_id']]);read=store.read_json
        for parent in [self.records,self.events]:
            worker.update_work_item(item['work_item_id'],status='accepted',path=path)
            def unavailable(target):
                if target.parent==parent:raise OSError('temporary read failure')
                return read(target)
            with patch.object(store,'read_json',side_effect=unavailable):result=worker.apply_next_accepted(instance_id='one',path=path)
            self.assertEqual(result['status'],'failed_consolidation_retryable')
            result=worker.apply_next_accepted(instance_id='one',path=path)
            self.assertEqual(result['status'],'consolidated');self.assertEqual(result['resulting_memory_ids'],[memory.memory_id])
        self.assertEqual(len(store.list_memories(instance_id='one')),1)

    def test_C3_D2_corrupt_record_is_review_not_retry_or_new_mutation(self):
        item,path=self.accepted_item('unused');memory=self.create(source_work_item_ids=[item['work_item_id']])
        target=self.records/(memory.memory_id+'.json');target.write_text('[]')
        result=worker.apply_next_accepted(instance_id='one',path=path)
        self.assertEqual(result['status'],'review');self.assertEqual(target.read_text(),'[]')
        self.assertEqual(len(list(self.records.glob('*.json'))),1)


    def test_C4_D1_failed_directory_scan_cannot_duplicate_revised_prior_work(self):
        item,path=self.accepted_item('unused');memory=self.create(source_work_item_ids=[item['work_item_id']])
        store.revise_memory(memory.memory_id,content='legitimate later revision',instance_id='one')
        scan=mutation.os.scandir
        for parent in [self.records,self.events]:
            worker.update_work_item(item['work_item_id'],status='accepted',path=path)
            def unavailable(directory):
                if Path(directory)==parent:raise PermissionError('temporary enumeration denial')
                return scan(directory)
            with patch.object(mutation.os,'scandir',side_effect=unavailable):
                result=worker.apply_next_accepted(instance_id='one',path=path)
            self.assertEqual(result['status'],'failed_consolidation_retryable')
            result=worker.apply_next_accepted(instance_id='one',path=path)
            self.assertEqual(result['resulting_memory_ids'],[memory.memory_id])
        self.assertEqual(len(store.list_memories(instance_id='one')),1)
        self.assertEqual(store.load_memory(memory.memory_id)['content'],'legitimate later revision')

    def test_C4_D1_partial_scan_failure_cannot_return_partial_evidence(self):
        memory=self.create(source_work_item_ids=['done'])
        scan=mutation.os.scandir
        class Partial:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def __iter__(self):
                with scan(self_records) as entries:
                    yield next(entries)
                    raise OSError('scan stopped after first directory entry')
        self_records=self.records
        with patch.object(mutation.os,'scandir',return_value=Partial()),self.assertRaises(OSError):
            store.find_memory_by_work_item('done',instance_id='one')
        self.assertEqual(store.find_memory_by_work_item('done',instance_id='one')['memory_id'],memory.memory_id)

    def test_C4_D2_invalid_utf8_record_and_event_require_review_preserving_bytes(self):
        item,path=self.accepted_item('unused');memory=self.create(source_work_item_ids=[item['work_item_id']])
        event=store.load_memory(memory.memory_id)['completed_work_item_events'][item['work_item_id']]
        for target in [self.records/(memory.memory_id+'.json'),self.events/(event+'.json')]:
            original=target.read_bytes();target.write_bytes(b'\xff')
            worker.update_work_item(item['work_item_id'],status='accepted',path=path)
            result=worker.apply_next_accepted(instance_id='one',path=path)
            self.assertEqual(result['status'],'review');self.assertEqual(target.read_bytes(),b'\xff')
            self.assertIsNone(worker.apply_next_accepted(instance_id='one',path=path))
            target.write_bytes(original)

    def test_C4_D2_wrong_retained_field_types_are_review_not_retry(self):
        item,path=self.accepted_item('unused');memory=self.create(source_work_item_ids=[item['work_item_id']])
        event=store.load_memory(memory.memory_id)['completed_work_item_events'][item['work_item_id']]
        cases={'source_work_item_ids':None,'source_message_ids':'not-a-list',
            'source_archive_ids':[{}],'completed_work_item_events':[], 'data':[],
            'instance_id':{},'created_at':None,'memory_id':None,'confidence':'not-number',
            'importance':10**400}
        for target in [self.records/(memory.memory_id+'.json'),self.events/(event+'.json')]:
            original=target.read_bytes()
            for field,bad in cases.items():
                with self.subTest(target=target.parent.name,field=field):
                    value=json.loads(original);value[field]=bad;target.write_text(json.dumps(value))
                    before=target.read_bytes();worker.update_work_item(item['work_item_id'],status='accepted',path=path)
                    result=worker.apply_next_accepted(instance_id='one',path=path)
                    self.assertEqual(result['status'],'review');self.assertEqual(target.read_bytes(),before)
            target.write_bytes(original)

    def test_C4_D2_decode_and_stat_failures_are_not_absence(self):
        memory=self.create();target=self.records/(memory.memory_id+'.json')
        for text in ['{"a":1,"a":2}', '{"nested":{"a":1,"a":2}}','{"confidence":NaN}']:
            with self.assertRaises(mutation.MemoryRecoveryRequired):mutation._decode_retained(text)
        stat=Path.lstat
        def unavailable(path,*args,**kwargs):
            if path==target:raise PermissionError('temporary stat denial')
            return stat(path,*args,**kwargs)
        with patch.object(Path,'lstat',unavailable),self.assertRaises(PermissionError):store.load_memory(memory.memory_id)
        self.assertEqual(store.load_memory(memory.memory_id)['memory_id'],memory.memory_id)

    def test_C4_D2_missing_required_field_and_invalid_new_write_do_not_commit(self):
        item,path=self.accepted_item('unused');memory=self.create(source_work_item_ids=[item['work_item_id']])
        target=self.records/(memory.memory_id+'.json');original=target.read_bytes()
        value=json.loads(original);del value['confidence'];target.write_text(json.dumps(value))
        result=worker.apply_next_accepted(instance_id='one',path=path)
        self.assertEqual(result['status'],'review');self.assertNotIn('confidence',json.loads(target.read_text()))
        target.write_bytes(original)
        before={p:p.read_bytes() for parent in [self.records,self.events] for p in parent.glob('*.json')}
        with self.assertRaises(mutation.MemoryRecoveryRequired):
            store.revise_memory(memory.memory_id,confidence='not-a-number',instance_id='one')
        self.assertEqual(before,{p:p.read_bytes() for parent in [self.records,self.events] for p in parent.glob('*.json')})
        self.assertFalse((self.records/'.pending-mutation.json').exists())


if __name__=='__main__':unittest.main()
