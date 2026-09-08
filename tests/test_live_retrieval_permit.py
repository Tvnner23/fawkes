import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.runtime.chat import FawkesChatRuntime
from src.runtime.evidence_eligibility import POLICY_VERSION


class LivePermitPromptTests(unittest.TestCase):
    class Response:
        output_text="safe answer"; usage=None

    def evidence(self, body="AUTHORIZED PRIVATE EVIDENCE", **changes):
        route={"provider_policy_id":"private-chat-policy","provider_class":"openai-compatible","model":"test-model","route_version":"1"}
        item={"instance_id":"fawkes","owner_principal_id":"authenticated-rider:fawkes",
            "evidence_id":"m1","domain":"memory","authority_class":"derived_memory_evidence",
            "original_evidence_reference":{"memory_id":"m1"},"adapter_version":"memory-two-stage-v1",
            "text":body,"content":body,"memory_type":"preference",
            "eligibility":{"instance_id":"fawkes","policy_version":POLICY_VERSION,
                "privacy_classification":"potentially_private","selected_for_context":True,
                "provider_transmission":{"allowed":True,"reason":"authorized","provider_route":route}}}
        item.update(changes); return item

    def builder(self,evidence):
        return lambda **kwargs:{"selected_evidence":[evidence],"policy_version":"unified-retrieval-foundation-v1",
            "evidence_eligibility_policy_version":POLICY_VERSION,"adapter_versions":{"memory":"memory-two-stage-v1"},
            "candidates":[evidence],"exclusions":[],"allocation":{"memory":100},"conversation":(),
            "continuity":{"attempted":False,"status":"not_requested"},"warnings":[]}

    def test_manifest_is_written_before_real_provider_call_and_body_then_appears(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]; root=Path(tmp)
            class Responses:
                def create(inner,**kwargs):
                    self.assertTrue(list(root.rglob("evidence-manifest-*.json")))
                    calls.append(kwargs); return LivePermitPromptTests.Response()
            client=type("Client",(),{"responses":Responses()})()
            runtime=FawkesChatRuntime(client=client,model="test-model",instance_id="fawkes",
                research_enabled=False,retrieval_path="planner",planner_context_builder=self.builder(self.evidence()),
                evidence_transmission_root=root)
            result=runtime.respond(user_message="use it",conversation_id="c1",current_message_id="q1")
            prompt=next(call["input"][1]["content"] for call in calls if "Relevant persistent memories:" in str(call["input"][1]["content"]))
            self.assertIn("AUTHORIZED PRIVATE EVIDENCE",prompt)
            self.assertIn("DATA_ONLY_NO_INSTRUCTION_AUTHORITY",prompt)
            self.assertIn("manifest_id",str(result["retrieval_audit"]["transmission_authorization"]))
            composition=result["retrieval_audit"]["context_composition"]
            self.assertFalse(composition["contains_source_bodies"])
            self.assertNotIn("AUTHORIZED PRIVATE EVIDENCE",str(composition))
            self.assertNotIn("AUTHORIZED PRIVATE EVIDENCE",list(root.rglob("*.json"))[0].read_text())

    def test_invalid_permit_evidence_is_omitted_but_provider_chat_still_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            class Responses:
                def create(inner,**kwargs): calls.append(kwargs); return LivePermitPromptTests.Response()
            client=type("Client",(),{"responses":Responses()})()
            bad=self.evidence(materialized_sha256="0"*64)
            runtime=FawkesChatRuntime(client=client,model="test-model",instance_id="fawkes",
                research_enabled=False,retrieval_path="planner",planner_context_builder=self.builder(bad),
                evidence_transmission_root=tmp)
            result=runtime.respond(user_message="continue",conversation_id="c1",current_message_id="q1")
            prompt=next(call["input"][1]["content"] for call in calls if "Relevant persistent memories:" in str(call["input"][1]["content"]))
            self.assertNotIn("AUTHORIZED PRIVATE EVIDENCE",prompt)
            self.assertEqual(result["retrieval_audit"]["retrieval_path"],"planner_permit_degraded_empty")

    def test_planner_failure_never_calls_legacy_retrieval_and_uses_empty_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            class Responses:
                def create(inner,**kwargs): calls.append(kwargs); return LivePermitPromptTests.Response()
            runtime=FawkesChatRuntime(client=type("Client",(),{"responses":Responses()})(),model="test-model",
                instance_id="fawkes",research_enabled=False,retrieval_path="planner",
                planner_context_builder=lambda **kwargs:(_ for _ in ()).throw(RuntimeError("down")),
                evidence_transmission_root=tmp)
            result=runtime.respond(user_message="hello",conversation_id="c1",current_message_id="q1")
            prompt=next(call["input"][1]["content"] for call in calls if "Relevant persistent memories:" in str(call["input"][1]["content"]))
            self.assertIn("Relevant persistent memories:\n(none)",prompt)
            self.assertEqual(result["retrieval_audit"]["retrieval_path"],"planner_degraded_empty")

    def test_tamper_after_prompt_build_is_caught_at_real_provider_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); calls=[]
            class Responses:
                def create(inner,**kwargs):
                    content=str(kwargs["input"][1]["content"])
                    if "Relevant persistent memories:" not in content:
                        manifests=list(root.rglob("evidence-manifest-*.json"))
                        if manifests:
                            manifests[0].write_text("{}")
                    calls.append(kwargs); return LivePermitPromptTests.Response()
            runtime=FawkesChatRuntime(client=type("Client",(),{"responses":Responses()})(),model="test-model",
                instance_id="fawkes",research_enabled=False,retrieval_path="planner",
                planner_context_builder=self.builder(self.evidence()),evidence_transmission_root=root)
            result=runtime.respond(user_message="use it",conversation_id="c1",current_message_id="q1")
            prompt=next(call["input"][1]["content"] for call in calls if "Relevant persistent memories:" in str(call["input"][1]["content"]))
            self.assertNotIn("AUTHORIZED PRIVATE EVIDENCE",prompt)
            self.assertEqual(result["retrieval_audit"]["retrieval_path"],"planner_permit_degraded_empty")

    def test_legacy_mode_is_immediate_rollback_and_ignores_planner_builder(self):
        runtime=FawkesChatRuntime(client=type("Client",(),{})(),model="test-model",instance_id="fawkes",
            research_enabled=False,retrieval_path="legacy",planner_context_builder=lambda **kwargs:(_ for _ in ()).throw(AssertionError()))
        self.assertEqual(runtime.retrieval_path,"legacy")

    def test_composed_body_must_match_verified_permit_at_final_provider_boundary(self):
        import hashlib
        from src.runtime.context_composer import ProductionContextComposer, _digest
        for mutation in ('body', 'evidence_id', 'manifest'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                calls=[]
                class Responses:
                    def create(inner,**kwargs):
                        calls.append(kwargs);return LivePermitPromptTests.Response()
                class ChangedComposer(ProductionContextComposer):
                    def compose(inner,**kwargs):
                        package=super().compose(**kwargs)
                        if mutation=='body':
                            source=package['retrieved_sources'][0]
                            source['body']='SUBSTITUTED UNAUTHORIZED BODY'
                            source['body_sha256']=hashlib.sha256(source['body'].encode()).hexdigest()
                        elif mutation=='evidence_id':
                            package['retrieved_sources'][0]['metadata']['evidence_id']='other-evidence'
                        else:
                            package['transmission_authorization']['manifest_id']='other-manifest'
                        # Even a self-consistent package is not independent transmission authority.
                        package['package_id']=_digest({k:v for k,v in package.items() if k not in {'package_id','audit'}})
                        package['audit']=inner.audit(package)
                        return package
                runtime=FawkesChatRuntime(client=type('Client',(),{'responses':Responses()})(),model='test-model',
                    instance_id='fawkes',research_enabled=False,retrieval_path='planner',
                    planner_context_builder=self.builder(self.evidence()),evidence_transmission_root=tmp)
                runtime.context_composer=ChangedComposer()
                result=runtime.respond(user_message='use it',conversation_id='c1',current_message_id='q1')
                prompt=next(call['input'][1]['content'] for call in calls
                    if 'Relevant persistent memories:' in str(call['input'][1]['content']))
                self.assertNotIn('SUBSTITUTED UNAUTHORIZED BODY',prompt)
                self.assertNotIn('AUTHORIZED PRIVATE EVIDENCE',prompt)
                self.assertEqual(result['retrieval_audit']['retrieval_path'],'planner_permit_degraded_empty')

    def test_legacy_and_planner_empty_paths_preserve_provider_request_structure(self):
        captured=[]
        class Responses:
            def create(inner,**kwargs): captured.append(kwargs); return LivePermitPromptTests.Response()
        client=type("Client",(),{"responses":Responses()})()
        empty={"memories":[],"archive_passages":[],"library_passages":[],"conversation":(),
               "continuity":{"attempted":False,"status":"not_requested"},"warnings":[],
               "retrieval_trace":{}}
        legacy=FawkesChatRuntime(client=client,model="test-model",instance_id="fawkes",research_enabled=False,retrieval_path="legacy")
        with patch.object(legacy,"build_context",return_value=dict(empty)):
            legacy.respond(user_message="hello",conversation_id="c1",current_message_id="q1")
        planner=FawkesChatRuntime(client=client,model="test-model",instance_id="fawkes",research_enabled=False,
            retrieval_path="planner",planner_context_builder=lambda **kwargs:{**empty,"selected_evidence":[],
            "policy_version":"unified-retrieval-foundation-v1","evidence_eligibility_policy_version":POLICY_VERSION,"adapter_versions":{}},
            evidence_transmission_root=tempfile.mkdtemp())
        planner.respond(user_message="hello",conversation_id="c1",current_message_id="q1")
        main=[x for x in captured if "Relevant persistent memories:" in str(x["input"][1]["content"])]
        self.assertEqual(len(main),2)
        self.assertEqual(set(main[0]),set(main[1])); self.assertEqual(main[0]["model"],main[1]["model"])
        self.assertIn("Relevant persistent memories:\n(none)",main[1]["input"][1]["content"])

    def test_response_permit_does_not_authorize_separate_research_provider(self):
        captured=[]
        class Research:
            capability=None
            def research_if_needed(inner,**kwargs):
                captured.extend(kwargs["conversation_context"]); return None
        class Responses:
            def create(inner,**kwargs): return LivePermitPromptTests.Response()
        runtime=FawkesChatRuntime(client=type("Client",(),{"responses":Responses()})(),model="test-model",
            instance_id="fawkes",research_orchestrator=Research(),retrieval_path="planner",
            planner_context_builder=self.builder(self.evidence()),evidence_transmission_root=tempfile.mkdtemp())
        runtime.respond(user_message="What is the latest status?",conversation_id="c1",current_message_id="q1")
        self.assertNotIn("AUTHORIZED PRIVATE EVIDENCE",str(captured))


if __name__=="__main__": unittest.main()
