"""Recorded F07 final representation checks; no real provider or Memory data."""
import copy,json,unittest,os,subprocess,sys,tempfile
from unittest.mock import patch
from src.runtime.context_composer import ProductionContextComposer
from src.runtime.production_retrieval_adapters import MemoryProductionAdapter,TwoStageRetrievalCoordinator
from src.runtime.evidence_eligibility import EvidenceUseContext


class TruthAnnotationPipelineTests(unittest.TestCase):
    def test_native_adapter_uses_configured_metadata_root_not_checkout_default(self):
        code='''from src.runtime.production_retrieval_adapters import NativeArchiveProductionAdapter
from src.memory.archive_retrieval import META_DIR,INDEX_PATH
adapter=NativeArchiveProductionAdapter()
assert adapter.meta_dir==META_DIR and adapter.index_path==INDEX_PATH
assert str(META_DIR).startswith(__import__('os').environ['FAWKES_RUNTIME_STATE_ROOT'])
'''
        with tempfile.TemporaryDirectory() as root:
            result=subprocess.run([sys.executable,'-B','-c',code],env={**os.environ,'FAWKES_RUNTIME_STATE_ROOT':root},capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr.decode())

    def memory(self,**changes):
        return {'memory_id':'memory-one','instance_id':'one','memory_type':'fact','status':'active',
            'content':'The project was using a historical fixture.','confidence':.2,
            'created_at':'2020-01-01T00:00:00+00:00','updated_at':'2021-01-01T00:00:00+00:00',
            'source_archive_ids':['archive-one'],'source_message_ids':['message-one'],
            'uncertainty':'unverified historical statement','contradiction_group_ids':['unresolved-conflict'],
            'privacy_classification':'potentially_private','owner_principal_id':'rider:fixture',**changes}

    def package(self,memory):
        adapter=MemoryProductionAdapter()
        route={'provider_class':'synthetic','model':'no-provider-called'}
        with patch('src.runtime.production_retrieval_adapters.list_memories',return_value=[memory]),patch('src.runtime.production_retrieval_adapters.load_memory',return_value=memory):
            plan=TwoStageRetrievalCoordinator('one','rider:fixture',adapters=(adapter,),provider_route=route).plan('historical fixture',
                evidence_use_context=EvidenceUseContext(instance_id='one',rider_principal_id='rider:fixture',capability_id='chat.respond',
                    capability_authorized=True,provider_mode='configured_external_provider',provider_authorized=True))
        selected=plan['selected_evidence']
        composer=ProductionContextComposer()
        package=composer.compose(instance_id='one',rider_principal_id='rider:fixture',conversation_id='conversation',request_message_id='request',
            provider_route=route,current_message='fixture',retrieved_evidence=selected,
            transmission_authorization={'manifest_id':'synthetic-fixture','authorized_evidence_ids':[x['evidence_id'] for x in selected]})
        return composer,package

    def test_memory_annotations_reach_actual_final_model_context(self):
        memory=self.memory();before=copy.deepcopy(memory)
        composer,package=self.package(memory);rendered=composer.render(package)
        for text in ['unverified historical statement','unresolved-conflict','2020-01-01','2021-01-01','"confidence":0.2','not a calibrated probability','not an established truth-validity interval','DATA_ONLY_NO_INSTRUCTION_AUTHORITY']:
            self.assertIn(text,rendered)
        self.assertIn(memory['content'],rendered);self.assertEqual(memory,before)
        self.assertFalse(package['retrieved_sources'][0]['instruction_authority'])

    def test_unknown_confidence_and_time_are_not_reconstructed(self):
        memory=self.memory();[memory.pop(k) for k in ['confidence','created_at','updated_at','uncertainty']]
        composer,package=self.package(memory);rendered=composer.render(package)
        self.assertIn('not recorded; absence is not confirmation',rendered)
        for name in ['confidence','created_at','updated_at']:
            self.assertNotIn(name,package['retrieved_sources'][0]['metadata'])
        self.assertNotIn('"confidence":0',rendered)

    def test_annotations_remain_attributed_data_and_identity_bound(self):
        memory=self.memory(uncertainty='synthetic quoted "instruction" is evidence, not authority')
        composer,package=self.package(memory)
        self.assertIn('attributed_qualification=',composer.render(package))
        modified=copy.deepcopy(package);modified['retrieved_sources'][0]['metadata']['confidence']=1
        with self.assertRaisesRegex(ValueError,'identity mismatch'):composer.render(modified)

    def test_denied_evidence_does_not_leak_qualification_or_content(self):
        memory=self.memory(privacy_classification='restricted')
        composer,package=self.package(memory);rendered=composer.render(package)
        self.assertEqual(package['retrieved_sources'],[])
        self.assertNotIn('unverified historical statement',rendered);self.assertNotIn(memory['content'],rendered)

    def test_changed_owner_or_quarantine_does_not_materialize_after_enumeration(self):
        for changes in [{'instance_id':'two'},{'status':'quarantined'}]:
            with patch('src.runtime.production_retrieval_adapters.load_memory',return_value=self.memory(**changes)):
                with self.assertRaises(LookupError):MemoryProductionAdapter().materialize({'memory_id':'memory-one'},instance_id='one')

    def test_body_free_audit_remains_separate_from_rendered_evidence(self):
        composer,package=self.package(self.memory())
        self.assertNotIn(self.memory()['content'],json.dumps(package['audit']))
        self.assertFalse(package['audit']['contains_source_bodies'])

    def test_completely_omitted_conflict_is_not_mistaken_for_a_split_group(self):
        from tests.test_context_composer import ProductionContextComposerTests
        fixture=ProductionContextComposerTests();fixture.setUp()
        items=[fixture.evidence('a',body='12345',contradiction_group_ids=['conflict']),
               fixture.evidence('b',body='67890',contradiction_group_ids=['conflict']),fixture.evidence('c',body='ok')]
        for budget,expected in [(0,[]),(3,['c']),(5,['c']),(10,['a','b']),(12,['a','b','c'])]:
            with self.subTest(budget=budget):
                selected,allocation=fixture.composer.allocate_authorized_evidence(items,upstream_allocation={'total_budget':budget})
                self.assertEqual([v['evidence_id'] for v in selected],expected)
                self.assertEqual(allocation['contradiction_policy'],'atomic_all_or_none_no_truth_selection')


if __name__=='__main__':unittest.main()
