"""Closed continuity D1-D4 reproductions, entirely disposable and offline."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from src.runtime.production_retrieval_adapters import (
    MemoryProductionAdapter, NativeArchiveProductionAdapter, LibraryProductionAdapter,
    TwoStageRetrievalCoordinator,
)
from src.runtime.evidence_eligibility import EvidenceUseContext, POLICY_VERSION
from src.runtime.evidence_transmission import EvidenceTransmissionAuthorizer, ProviderRoute
from src.runtime.context_composer import ProductionContextComposer
from src.runtime.retrieval_planner import StaticEvidenceAdapter, UnifiedRetrievalPlanner

MOD='src.runtime.production_retrieval_adapters.'
ROUTE=ProviderRoute('fixture','synthetic','no-model-called')


def memory(eid='memory-z', **changes):
    return {'memory_id':eid,'instance_id':'one','status':'active','content':'fixture '+eid,
        'memory_type':'fact','owner_principal_id':'rider:fixture','privacy_classification':'standard',
        'source_archive_ids':['archive-one'], 'source_message_ids':['message-one'], **changes}


def plan(adapter, **kwargs):
    return TwoStageRetrievalCoordinator('one','rider:fixture',adapters=[adapter],
        provider_route=ROUTE.public()).plan('fixture',evidence_use_context=EvidenceUseContext(
        instance_id='one',rider_principal_id='rider:fixture',capability_id='chat.respond',
        capability_authorized=True,provider_mode='configured_external_provider',provider_authorized=True),**kwargs)


class ContinuityReviewFindings(unittest.TestCase):
    def archive(self, root):
        root=Path(root);index=root/'index.sqlite';meta=root/'metadata';meta.mkdir()
        with closing(sqlite3.connect(index)) as db, db:
            db.execute('CREATE TABLE canonical_message_projection (instance_id, conversation_id, message_id, created_at, content, source_archive_id, canonicalizer_version, role)')
            db.execute('INSERT INTO canonical_message_projection VALUES (?,?,?,?,?,?,?,?)',
                ('one','conversation','message-one','2020-01-01T00:00:00+00:00','fixture archive body','archive-one','v1','user'))
        value={'schema_version':1,'archive_id':'archive-one','instance_id':'one','conversation_id':'conversation',
            'owner_principal_id':'rider:fixture','privacy':{'classification':'standard'}}
        path=meta/'archive-one.json';path.write_text(json.dumps(value))
        return NativeArchiveProductionAdapter(index_path=index,meta_dir=meta),path,value

    def test_archive_metadata_errors_never_become_legacy_provider_authority(self):
        for kind in ('missing','malformed','unreadable','duplicate','wrong-owner','wrong-archive','wrong-conversation'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root:
                adapter,path,value=self.archive(root)
                self.assertTrue(plan(adapter)['selected_evidence'])
                if kind=='missing':path.unlink()
                elif kind=='malformed':path.write_text('{invalid')
                elif kind=='duplicate':path.write_text(path.read_text()[:-1]+',"privacy":{"classification":"restricted"}}')
                elif kind.startswith('wrong-'):
                    value[{'wrong-owner':'instance_id','wrong-archive':'archive_id','wrong-conversation':'conversation_id'}[kind]]='other'
                    path.write_text(json.dumps(value))
                if kind=='unreadable':
                    with patch.object(Path,'read_text',side_effect=PermissionError('synthetic denied')):
                        result=plan(adapter)
                else:result=plan(adapter)
                self.assertEqual(result['selected_evidence'],[])
                self.assertTrue(result['exclusions'])

    def test_readable_bound_legacy_archive_remains_compatible(self):
        with tempfile.TemporaryDirectory() as root:
            adapter,path,value=self.archive(root);value.pop('privacy');value.pop('owner_principal_id')
            path.write_text(json.dumps(value));selected=plan(adapter)['selected_evidence']
            self.assertEqual(len(selected),1)
            self.assertEqual(selected[0]['privacy_classification'],'legacy_private_unclassified')

    def test_archive_materialization_rejects_changed_metadata_and_index_body(self):
        for field in ('privacy','owner_principal_id','instance_id','body'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as root:
                adapter,path,value=self.archive(root)
                ref=adapter.enumerate_metadata(instance_id='one')[0]['original_evidence_reference']
                if field=='body':
                    with closing(sqlite3.connect(adapter.index_path)) as db, db:db.execute("UPDATE canonical_message_projection SET content='other'")
                else:
                    value[field]={'classification':'restricted'} if field=='privacy' else 'other'
                    path.write_text(json.dumps(value))
                with self.assertRaises((LookupError,ValueError,PermissionError)):adapter.materialize(ref,instance_id='one')

    def test_memory_authorization_and_body_are_same_observation_before_ranking(self):
        for changes in ({'privacy_classification':'restricted'},{'owner_principal_id':'other'},
                        {'content':'changed body'},{'source_archive_ids':['different']},
                        {'contradiction_group_ids':['changed']},{'status':'quarantined'}):
            before=memory();after=memory(**changes)
            with self.subTest(changes=changes),patch(MOD+'list_memories',return_value=[before]),patch(MOD+'load_memory',return_value=after):
                result=plan(MemoryProductionAdapter())
                self.assertEqual(result['selected_evidence'],[])
                self.assertTrue(any(x['stage']=='materialization' for x in result['exclusions']))
                self.assertTrue(all(x['candidate_count']==0 for x in result['enforcement_order'] if x['event']=='rank'))

    def test_library_source_authority_is_rechecked_before_returning_body(self):
        source={'source_id':'source','instance_id':'one','sha256':'fixture-digest','artifact':{
            'owner_principal_id':'rider:fixture','privacy':{'classification':'standard'},'lifecycle':{'state':'active'}}}
        extraction={'source_id':'source','instance_id':'one','extraction_id':'extract','source_sha256':'fixture-digest',
            'segments':[{'segment_id':'segment','text':'fixture library'}]}
        for field in ('owner_principal_id','privacy','lifecycle'):
            changed=copy.deepcopy(source)
            changed['artifact'][field]={'owner_principal_id':'other','privacy':{'classification':'restricted'},'lifecycle':{'state':'revoked'}}[field]
            with self.subTest(field=field),patch(MOD+'list_sources',side_effect=[[source],[changed]]),patch(MOD+'list_extractions',return_value=[extraction]):
                adapter=LibraryProductionAdapter();ref=adapter.enumerate_metadata(instance_id='one')[0]['original_evidence_reference']
                with self.assertRaises((LookupError,ValueError,PermissionError)):adapter.materialize(ref,instance_id='one')

    def selected(self, records, **kwargs):
        byid={x['memory_id']:x for x in records}
        with patch(MOD+'list_memories',return_value=records),patch(MOD+'load_memory',side_effect=lambda eid:copy.deepcopy(byid[eid])):
            return plan(MemoryProductionAdapter(),**kwargs)

    def compose_with_actual_permit(self, items, root):
        permit=EvidenceTransmissionAuthorizer(root=root).authorize(instance_id='one',rider_principal_id='rider:fixture',
            conversation_id='conversation',request_message_id='request',correlation_id='correlation',route=ROUTE,
            selected_evidence=items,planner_version='fixture',policy_version=POLICY_VERSION,adapter_versions={})
        self.assertTrue(permit.verify(route=ROUTE,selected_evidence=items))
        if items:
            with self.assertRaises(ValueError):permit.verify(route=ROUTE,selected_evidence=items+[items[0]])
            changed=copy.deepcopy(items);changed[0]['original_evidence_reference']={'id':'substitution'}
            with self.assertRaises(ValueError):permit.verify(route=ROUTE,selected_evidence=changed)
        composer=ProductionContextComposer()
        package=composer.compose(instance_id='one',rider_principal_id='rider:fixture',
            conversation_id='conversation',request_message_id='request',provider_route=ROUTE.public(),current_message='fixture',
            retrieved_evidence=items,transmission_authorization={'manifest_id':permit.manifest['manifest_id'],
                'authorized_evidence_ids':[x['evidence_id'] for x in permit.manifest['evidence']]})
        self.assertTrue(composer.verify_transmission(package,
            verified_bodies=permit.provider_bodies(route=ROUTE,selected_evidence=items),
            manifest_id=permit.manifest['manifest_id']))
        return package

    def test_ranked_order_and_actual_sorted_transmission_set_are_compatible(self):
        result=self.selected([memory('memory-a'),memory('memory-z')])
        items=list(reversed(result['selected_evidence']))
        self.assertEqual([x['evidence_id'] for x in items],['memory-z','memory-a'])
        with tempfile.TemporaryDirectory() as root:
            package=self.compose_with_actual_permit(items,root)
        self.assertEqual([x['metadata']['evidence_id'] for x in package['retrieved_sources']],['memory-z','memory-a'])

    def test_mixed_domains_permit_preserves_render_order(self):
        items=self.selected([memory('memory-a'),memory('memory-z')])['selected_evidence']
        items[1]['domain']='library';items[1]['authority_class']='immutable_library_source'
        # Decision's exact source domain must match the new synthetic fixture.
        items[1]['eligibility']['source_domain']='library'
        with tempfile.TemporaryDirectory() as root:package=self.compose_with_actual_permit(items,root)
        self.assertEqual([x['metadata']['domain'] for x in package['retrieved_sources']],['memory','library'])

    def test_duplicate_or_substituted_authorized_ids_remain_rejected(self):
        items=self.selected([memory('memory-a'),memory('memory-z')])['selected_evidence']
        for ids in (['memory-a','memory-a'],['memory-a','other'],['memory-z'],['memory-a','memory-z','other'],['memory-a',{}]):
            with self.subTest(ids=ids),self.assertRaises(PermissionError):
                ProductionContextComposer().compose(instance_id='one',rider_principal_id='rider:fixture',conversation_id='conversation',
                    request_message_id='request',provider_route=ROUTE.public(),current_message='fixture',retrieved_evidence=items,
                    transmission_authorization={'manifest_id':'fixture','authorized_evidence_ids':ids})

    def test_full_pipeline_budget_never_selects_only_one_known_conflict_member(self):
        records=[memory(eid,content='fixture '+('x'*182),contradiction_group_ids=['conflict']) for eid in ('memory-a','memory-b')]
        result=self.selected(records,total_budget_chars=256)
        self.assertEqual(result['selected_evidence'],[])
        self.assertTrue(result['warnings'])
        result=self.selected(records,total_budget_chars=512)
        self.assertEqual(len(result['selected_evidence']),2)
        with tempfile.TemporaryDirectory() as root:self.compose_with_actual_permit(result['selected_evidence'],root)

    def test_rank_limit_and_nonmatching_peer_do_not_hide_known_contradiction(self):
        records=[memory('memory-a',contradiction_group_ids=['conflict']),memory('memory-b',contradiction_group_ids=['conflict'])]
        self.assertEqual(self.selected(records,limit_per_domain=1)['selected_evidence'],[])
        records[1]['content']='unrelated wording'
        self.assertEqual(self.selected(records)['selected_evidence'],[])

    def test_ineligible_or_changed_peer_never_authorizes_a_partial_group(self):
        records=[memory('memory-a',contradiction_group_ids=['conflict']),memory('memory-b',contradiction_group_ids=['conflict'],privacy_classification='restricted')]
        self.assertEqual(self.selected(records)['selected_evidence'],[])
        records[1]['privacy_classification']='standard'
        with patch(MOD+'list_memories',return_value=records),patch(MOD+'load_memory',side_effect=[records[0],memory('memory-b',privacy_classification='restricted')]):
            self.assertEqual(plan(MemoryProductionAdapter())['selected_evidence'],[])

    def test_transitive_cross_domain_budget_group_is_atomic(self):
        items=self.selected([memory('memory-a'),memory('memory-b'),memory('memory-c')])['selected_evidence']
        for i,item in enumerate(items):
            item['contradiction_group_ids']=[['first'],['first','second'],['second']][i]
            item['text']='x'*180
        items[2]['domain']='library';items[2]['authority_class']='immutable_library_source'
        adapters=[StaticEvidenceAdapter('memory',items[:2],authority_class='derived_memory_evidence'),
            StaticEvidenceAdapter('library',items[2:],authority_class='immutable_library_source')]
        result=UnifiedRetrievalPlanner('one',adapters=adapters).plan('fixture',total_budget_chars=600)
        self.assertEqual(result['selected_evidence'],[])  # memory's fair share cannot fit both.
        result=UnifiedRetrievalPlanner('one',adapters=adapters).plan('fixture',total_budget_chars=800)
        self.assertEqual(len(result['selected_evidence']),3)

    def test_body_aliases_have_one_meaning_at_permit_and_composer(self):
        items=self.selected([memory()])['selected_evidence']
        with tempfile.TemporaryDirectory() as root:
            permit=EvidenceTransmissionAuthorizer(root=root).authorize(instance_id='one',rider_principal_id='rider:fixture',
                conversation_id='conversation',request_message_id='request',correlation_id='correlation',route=ROUTE,
                selected_evidence=items,planner_version='fixture',policy_version=POLICY_VERSION,adapter_versions={})
            for field in ('text','content'):
                for value in ('SUBSTITUTED UNAUTHORIZED BODY', None, 42, {}):
                    changed=copy.deepcopy(items);changed[0][field]=value
                    with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                        permit.provider_bodies(route=ROUTE,selected_evidence=changed)
                    with self.subTest(composer_field=field,value=value), self.assertRaises(ValueError):
                        ProductionContextComposer().compose(instance_id='one',rider_principal_id='rider:fixture',
                            conversation_id='conversation',request_message_id='request',provider_route=ROUTE.public(),
                            current_message='fixture',retrieved_evidence=changed,
                            transmission_authorization={'manifest_id':permit.manifest['manifest_id'],
                                'authorized_evidence_ids':[items[0]['evidence_id']]})
            for field in ('text','content'):
                single=copy.deepcopy(items);single[0].pop(field)
                self.assertTrue(permit.verify(route=ROUTE,selected_evidence=single))
                self.compose_with_actual_permit(single,root)

    def test_archive_actual_metadata_conflicts_survive_projection_and_budget(self):
        for metadata in ({'contradiction_group_id':'conflict'},
                         {'contradiction_group_ids':['conflict']},
                         {'contradiction_group_id':'conflict','contradiction_group_ids':['second']}):
            with self.subTest(metadata=metadata),tempfile.TemporaryDirectory() as root:
                adapter,path,value=self.archive(root);value.update(metadata);path.write_text(json.dumps(value))
                second={**value,'archive_id':'archive-two'}
                (path.parent/'archive-two.json').write_text(json.dumps(second))
                with closing(sqlite3.connect(adapter.index_path)) as db,db:
                    db.execute('UPDATE canonical_message_projection SET content=?',('fixture '+('x'*182),))
                    db.execute('INSERT INTO canonical_message_projection VALUES (?,?,?,?,?,?,?,?)',
                        ('one','conversation','message-two','2020-01-01T00:01:00+00:00',
                         'fixture '+('y'*182),'archive-two','v1','user'))
                expected={'conflict'} | set(metadata.get('contradiction_group_ids',[]))
                catalog=adapter.enumerate_metadata(instance_id='one')
                self.assertTrue(all(set(x.get('contradiction_group_ids',[]))==expected for x in catalog))
                small=plan(adapter,total_budget_chars=256)
                self.assertEqual(small['selected_evidence'],[])
                self.compose_with_actual_permit([],Path(root)/'empty-permit')
                large=plan(adapter,total_budget_chars=512)['selected_evidence']
                self.assertEqual(len(large),2)
                self.assertTrue(all(set(x.get('contradiction_group_ids',[]))==expected for x in large))
                package=self.compose_with_actual_permit(large,Path(root)/'full-permit')
                self.assertTrue(all(set(x['metadata']['contradiction_group_ids'])==expected
                                    for x in package['retrieved_sources']))
                self.assertEqual(plan(adapter,limit_per_domain=1)['selected_evidence'],[])
                second['privacy']={'classification':'restricted'}
                (path.parent/'archive-two.json').write_text(json.dumps(second))
                self.assertEqual(plan(adapter)['selected_evidence'],[])

    def test_malformed_archive_groups_cannot_become_ungrouped_authority(self):
        for metadata in ({'contradiction_group_id':42},{'contradiction_group_ids':'conflict'},
                         {'contradiction_group_ids':[None]},{'contradiction_group_ids':None}):
            with self.subTest(metadata=metadata),tempfile.TemporaryDirectory() as root:
                adapter,path,value=self.archive(root);value.update(metadata);path.write_text(json.dumps(value))
                self.assertEqual(plan(adapter)['selected_evidence'],[])

    def test_memory_combined_membership_survives_materialization_to_transmission(self):
        variants=[
            ({'contradiction_group_id':'shared','contradiction_group_ids':[]},)*2,
            ({'contradiction_group_id':'shared','contradiction_group_ids':['left']},
             {'contradiction_group_id':'shared','contradiction_group_ids':['right']}),
            ({'contradiction_group_id':'shared'},)*2,
            ({'contradiction_group_ids':['shared']},)*2,
        ]
        for left,right in variants:
            with self.subTest(left=left,right=right),tempfile.TemporaryDirectory() as root:
                records=[memory(eid,content='fixture '+('x'*182),**group)
                    for eid,group in zip(('memory-a','memory-b'),(left,right))]
                byid={r['memory_id']:r for r in records}
                with patch(MOD+'list_memories',return_value=records),patch(MOD+'load_memory',side_effect=lambda eid:copy.deepcopy(byid[eid])):
                    adapter=MemoryProductionAdapter()
                    catalog=adapter.enumerate_metadata(instance_id='one')
                    for item in catalog:
                        body=adapter.materialize(item['original_evidence_reference'],instance_id='one')
                        self.assertEqual(body['contradiction_group_ids'],item['contradiction_group_ids'])
                    self.assertEqual(plan(adapter,total_budget_chars=256)['selected_evidence'],[])
                    self.assertEqual(plan(adapter,limit_per_domain=1)['selected_evidence'],[])
                    selected=plan(adapter,total_budget_chars=512)['selected_evidence']
                self.assertEqual(len(selected),2)
                package=self.compose_with_actual_permit(selected,root)
                for source,record in zip(package['retrieved_sources'],records):
                    expected=set(record.get('contradiction_group_ids',[]))|{'shared'}
                    self.assertEqual(set(source['metadata']['contradiction_group_ids']),expected)
                records[1]['privacy_classification']='restricted'
                self.assertEqual(self.selected(records,total_budget_chars=512)['selected_evidence'],[])


if __name__=='__main__':unittest.main()
