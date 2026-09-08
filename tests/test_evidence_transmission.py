import json
import tempfile
import unittest
from pathlib import Path

from src.runtime.evidence_transmission import EvidenceTransmissionAuthorizer, ProviderRoute, ChatRetrievalPathSwitch
from src.runtime.evidence_eligibility import POLICY_VERSION


class EvidenceTransmissionTests(unittest.TestCase):
    def route(self,model="model-a"): return ProviderRoute("private-chat-policy","openai-compatible",model)
    def evidence(self,**kw):
        route=self.route().public()
        x={"instance_id":"fawkes","owner_principal_id":"rider:tanner","evidence_id":"e1","domain":"memory",
           "authority_class":"derived_memory_evidence","original_evidence_reference":{"memory_id":"m1"},
           "adapter_version":"memory-two-stage-v1","text":"SENSITIVE AUTHORIZED BODY",
           "eligibility":{"instance_id":"fawkes","policy_version":POLICY_VERSION,"privacy_classification":"potentially_private",
             "selected_for_context":True,"provider_transmission":{"allowed":True,"reason":"authorized_private_context_provider_processing","provider_route":route},
             "external_disclosure":{"allowed":False},"cross_principal_disclosure":{"allowed":False},"legacy_compatibility":None}}
        x.update(kw); return x
    def authorize(self,tmp,evidence=None,route=None):
        return EvidenceTransmissionAuthorizer(root=tmp).authorize(instance_id="fawkes",rider_principal_id="rider:tanner",
            conversation_id="c1",request_message_id="q1",correlation_id="q1",route=route or self.route(),
            selected_evidence=[] if evidence is None else evidence,planner_version="planner-v1",policy_version=POLICY_VERSION,
            adapter_versions={"memory":"memory-two-stage-v1"})

    def test_manifest_exists_before_provider_bodies_can_be_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            e=[self.evidence()]; permit=self.authorize(tmp,e)
            self.assertTrue(permit.path.exists()); self.assertEqual(permit.provider_bodies(route=self.route(),selected_evidence=e)["e1"],"SENSITIVE AUTHORIZED BODY")
            self.assertNotIn("SENSITIVE AUTHORIZED BODY",permit.path.read_text())

    def test_denied_missing_foreign_and_route_mismatch_fail_closed(self):
        cases=[self.evidence(eligibility={**self.evidence()["eligibility"],"provider_transmission":{"allowed":False,"reason":"denied"}}),
               {k:v for k,v in self.evidence().items() if k!="eligibility"},self.evidence(instance_id="other"),self.evidence(owner_principal_id="rider:other")]
        for item in cases:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises((PermissionError,ValueError)): self.authorize(tmp,[item])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(PermissionError,"provider_route_mismatch"): self.authorize(tmp,[self.evidence()],route=self.route("model-b"))

    def test_digest_policy_and_body_staleness_fail_closed(self):
        bad=self.evidence(materialized_sha256="0"*64)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,"evidence_digest_mismatch"): self.authorize(tmp,[bad])
        stale=self.evidence(); stale["eligibility"]={**stale["eligibility"],"policy_version":"old-policy"}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(PermissionError,"policy_mismatch"): self.authorize(tmp,[stale])

    def test_manifest_tampering_and_changed_set_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            e=[self.evidence()]; permit=self.authorize(tmp,e)
            data=json.loads(permit.path.read_text()); data["provider_route"]["model"]="tampered"; permit.path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"tampered"): permit.provider_bodies(route=self.route(),selected_evidence=e)
        with tempfile.TemporaryDirectory() as tmp:
            e=[self.evidence()]; permit=self.authorize(tmp,e); changed=[{**e[0],"text":"changed"}]
            with self.assertRaisesRegex(ValueError,"set_or_digest"): permit.provider_bodies(route=self.route(),selected_evidence=changed)

    def test_empty_authorized_set_is_valid_and_body_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            permit=self.authorize(tmp,[]); self.assertEqual(permit.provider_bodies(route=self.route(),selected_evidence=[]),{})

    def test_rollback_switch_is_deterministic_and_failure_never_uses_legacy(self):
        legacy=lambda:{"memories":["legacy"]}; planner=lambda:{"memories":["planner"]}
        self.assertEqual(ChatRetrievalPathSwitch(enabled=False).select(legacy_builder=legacy,planner_builder=planner)["path"],"legacy")
        self.assertEqual(ChatRetrievalPathSwitch(enabled=True).select(legacy_builder=legacy,planner_builder=planner)["path"],"planner")
        result=ChatRetrievalPathSwitch(enabled=True).select(legacy_builder=legacy,planner_builder=lambda:(_ for _ in ()).throw(RuntimeError()))
        self.assertEqual(result["path"],"planner_degraded_empty"); self.assertEqual(result["context"]["memories"],[])

if __name__=="__main__": unittest.main()
