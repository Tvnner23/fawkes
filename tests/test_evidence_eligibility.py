import tempfile
import unittest
from pathlib import Path

from src.capabilities.provider_privacy import ephemeral_provider_artifact, record_provider_transmission
from src.runtime.context_receipts import save_context_receipt
from src.runtime.evidence_eligibility import (
    EvidenceUseContext, POLICY_VERSION, ProductionEvidenceEligibilityPolicy,
    classify_reviewer_source_evidence,
)
import hashlib
from src.runtime.retrieval_planner import StaticEvidenceAdapter, UnifiedRetrievalPlanner
from src.runtime.retrieval_replay import load_flight, record_live_flight


class ProductionEvidenceEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.policy = ProductionEvidenceEligibilityPolicy()

    def evidence(self, privacy="standard", **changes):
        value = {"instance_id": "fawkes", "owner_principal_id": "rider:tanner",
            "evidence_id": "evidence-1", "domain": "library",
            "authority_class": "immutable_library_source", "privacy_classification": privacy,
            "original_evidence_reference": {"source_id": "source-1"},
            "provenance_valid": True, "automatic_use_enabled": True,
            "text": "SENSITIVE FIXTURE CONTENT"}
        value.update(changes)
        return value

    def context(self, **changes):
        value = dict(instance_id="fawkes", rider_principal_id="rider:tanner",
            capability_id="chat.respond", capability_authorized=True,
            provider_mode="local_only", provider_authorized=False)
        value.update(changes)
        return EvidenceUseContext(**value)

    def test_source_disclosure_receipt_is_exact_body_free_and_deterministic(self):
        before=b"old\n"; after=b"new\n"
        expected=lambda body:{"sha256":hashlib.sha256(body).hexdigest(),"byte_length":len(body)}
        first=classify_reviewer_source_evidence(path="src/example.py",before=before,after=after,
            expected_before=expected(before),expected_after=expected(after))
        second=classify_reviewer_source_evidence(path="src/example.py",before=before,after=after,
            expected_before=expected(before),expected_after=expected(after))
        self.assertEqual(first,second);self.assertTrue(first["disclosure_allowed"])
        self.assertEqual(first["secret_assurance"],"no_configured_high_confidence_secret_detected")
        self.assertNotIn("old",str(first));self.assertNotIn("new",str(first))

    def test_source_disclosure_blocks_paths_secrets_binary_and_size(self):
        cases=((".env",b"ordinary","blocked_protected_path"),
            ("src/key.py",b"-----BEGIN PRIVATE KEY----- synthetic","blocked_high_confidence_secret"),
            ("src/token.py",b"sk-"+b"A"*24,"blocked_high_confidence_secret"),
            ("src/blob.bin",b"a\0b","blocked_unsupported_content"),
            ("src/large.py",b"x"*20,"blocked_size"))
        for path,body,want in cases:
            with self.subTest(path=path):
                result=classify_reviewer_source_evidence(path=path,before=None,after=body,evidence_limit=10)
                self.assertEqual(result["classification"],want);self.assertFalse(result["disclosure_allowed"])
                self.assertNotIn(body.decode(errors="ignore"),str(result))

    def test_protected_library_root_does_not_block_source_library(self):
        protected=classify_reviewer_source_evidence(path="library/private.json",before=None,after=b"{}")
        source=classify_reviewer_source_evidence(path="src/library/store.py",before=b"old",after=b"new")
        test=classify_reviewer_source_evidence(path="tests/test_library_store.py",before=b"old",after=b"new")
        self.assertEqual(protected["classification"],"blocked_protected_path")
        self.assertTrue(source["disclosure_allowed"]);self.assertTrue(test["disclosure_allowed"])

    def test_source_disclosure_rejects_escape_and_mismatched_state(self):
        with self.assertRaises(ValueError):
            classify_reviewer_source_evidence(path="../secret",before=None,after=b"x")
        with self.assertRaises(ValueError):
            classify_reviewer_source_evidence(path="src/a.py",before=None,after=b"x",
                expected_after={"sha256":"0"*64,"byte_length":1})

    def test_ordinary_and_potentially_private_are_private_context_eligible(self):
        for privacy in ("standard", "potentially_private"):
            decision = self.policy.evaluate(self.evidence(privacy), self.context())
            self.assertTrue(decision["automatic_private_context"]["allowed"])
            self.assertEqual(decision["privacy_classification"], privacy)
            self.assertFalse(decision["external_disclosure"]["allowed"])
            self.assertFalse(decision["cross_principal_disclosure"]["allowed"])

    def test_potentially_private_provider_use_does_not_grant_external_disclosure(self):
        decision = self.policy.evaluate(self.evidence("potentially_private"), self.context(
            provider_mode="configured_external_provider", provider_authorized=True))
        self.assertTrue(decision["provider_transmission"]["allowed"])
        self.assertTrue(decision["automatic_private_context"]["allowed"])
        self.assertFalse(decision["external_disclosure"]["allowed"])

    def test_highly_private_requires_explicit_relevance_or_category_authorization(self):
        evidence = self.evidence("highly_private", sensitive_category="health")
        unrelated = self.policy.evaluate(evidence, self.context())
        relevant = self.policy.evaluate(evidence, self.context(
            sensitive_request_categories=("health",)))
        authorized = self.policy.evaluate(evidence, self.context(
            grants=("evidence.highly_private.auto:health",)))
        self.assertFalse(unrelated["automatic_private_context"]["allowed"])
        self.assertEqual(unrelated["automatic_private_context"]["reason"],
                         "privacy_requires_explicit_authorization")
        self.assertTrue(relevant["automatic_private_context"]["allowed"])
        self.assertTrue(authorized["automatic_private_context"]["allowed"])

    def test_restricted_is_denied_by_default_and_scoped_grant_allows_local_use(self):
        denied = self.policy.evaluate(self.evidence("restricted"), self.context())
        allowed = self.policy.evaluate(self.evidence("restricted"), self.context(
            grants=("evidence.restricted.auto:evidence-1",)))
        self.assertFalse(denied["automatic_private_context"]["allowed"])
        self.assertTrue(allowed["automatic_private_context"]["allowed"])
        self.assertFalse(allowed["external_disclosure"]["allowed"])

    def test_provider_transmission_is_an_independent_fail_closed_decision(self):
        evidence = self.evidence("highly_private", sensitive_category="health")
        denied = self.policy.evaluate(evidence, self.context(
            provider_mode="configured_external_provider", provider_authorized=True,
            sensitive_request_categories=("health",)))
        allowed = self.policy.evaluate(evidence, self.context(
            provider_mode="configured_external_provider", provider_authorized=True,
            sensitive_request_categories=("health",),
            grants=("provider.transmit:highly_private",)))
        self.assertFalse(denied["provider_transmission"]["allowed"])
        self.assertFalse(denied["automatic_private_context"]["allowed"])
        self.assertEqual(denied["automatic_private_context"]["reason"],
                         "provider_transmission_denied")
        self.assertTrue(allowed["provider_transmission"]["allowed"])
        self.assertTrue(allowed["automatic_private_context"]["allowed"])

    def test_malformed_privacy_foreign_and_cross_rider_fail_closed(self):
        malformed = self.policy.evaluate(self.evidence("unknown"), self.context())
        foreign = self.policy.evaluate(self.evidence(instance_id="other"), self.context())
        cross = self.policy.evaluate(self.evidence(owner_principal_id="rider:other"), self.context())
        self.assertEqual(malformed["automatic_private_context"]["reason"], "privacy_classification_invalid")
        self.assertEqual(foreign["automatic_private_context"]["reason"], "foreign_phoenix")
        self.assertEqual(cross["automatic_private_context"]["reason"], "cross_principal_denied")
        self.assertFalse(malformed["automatic_private_context"]["allowed"])
        self.assertFalse(foreign["storage_access"]["allowed"])
        self.assertFalse(cross["storage_access"]["allowed"])

    def test_inherited_automatic_use_cannot_be_activated_by_grants(self):
        inherited = self.evidence(domain="inherited_history", authority_class="imported",
            history_era="inherited_history", identity_attribution="unassessed",
            native_boundary_status="boundary_unknown")
        decision = self.policy.evaluate(inherited, self.context(grants=(
            "evidence.restricted.auto:evidence-1", "history.inherited.auto")))
        self.assertFalse(decision["automatic_private_context"]["allowed"])
        self.assertEqual(decision["automatic_private_context"]["reason"], "automatic_use_disabled")
        self.assertEqual(inherited["identity_attribution"], "unassessed")
        self.assertEqual(inherited["native_boundary_status"], "boundary_unknown")

    def test_decisions_are_deterministic_and_do_not_mutate_evidence(self):
        evidence = self.evidence("potentially_private")
        original = dict(evidence); original["original_evidence_reference"] = dict(evidence["original_evidence_reference"])
        first = self.policy.evaluate(evidence, self.context())
        second = self.policy.evaluate(evidence, self.context())
        self.assertEqual(first, second)
        self.assertEqual(evidence, original)
        self.assertEqual(first["policy_version"], POLICY_VERSION)
        self.assertFalse(first["sensitive_content_logged"])

    def test_planner_exclusion_has_reason_and_no_sensitive_content(self):
        evidence = self.evidence("restricted")
        adapter = StaticEvidenceAdapter("library", [evidence],
            authority_class="immutable_library_source")
        plan = UnifiedRetrievalPlanner("fawkes", adapters=(adapter,),
            eligibility_policy=self.policy).plan("generic", evidence_use_context=self.context())
        self.assertEqual(plan["selected_evidence"], [])
        self.assertEqual(plan["exclusions"][0]["reason"], "privacy_requires_explicit_authorization")
        self.assertNotIn("SENSITIVE FIXTURE CONTENT", str(plan["exclusions"]))

    def test_context_receipt_and_flight_capture_policy_without_excluded_content(self):
        exclusion = {"domain": "library", "stage": "eligibility",
            "reason": "privacy_requires_explicit_authorization", "evidence_id": "evidence-1",
            "text": "SENSITIVE EXCLUDED CONTENT", "eligibility": {"policy_version": POLICY_VERSION,
                "privacy_classification": "restricted"}}
        audit = {"policy_version": "planner-v1", "exclusions": [exclusion],
                 "selected_evidence": [], "allocation": {"unit": "estimated_characters"}}
        with tempfile.TemporaryDirectory() as tmp:
            receipt = save_context_receipt(instance_id="fawkes", conversation_id="c1",
                request_message_id="q1", response_message_id="r1", model="fixture",
                retrieval_audit=audit, path=Path(tmp) / "receipt.json")
            record_live_flight(instance_id="fawkes", conversation_id="c1",
                request_message_id="q1", response_message_id="r1",
                response_archive_id="a1", request_text="query", model="fixture",
                context_receipt_id="r1", root=tmp, result={"text": "answer",
                    "memories": [], "archive_passages": [], "library_passages": [],
                    "conversation_context": [], "retrieval_trace": {
                        "candidates": [self.evidence("potentially_private")],
                        "exclusions": [exclusion], "retrieval_plan": {
                            "eligibility_policy_version": POLICY_VERSION}}})
            flight = load_flight("fawkes", "r1", root=tmp)
        self.assertNotIn("SENSITIVE EXCLUDED CONTENT", str(receipt["retrieval_audit"]))
        self.assertNotIn("SENSITIVE FIXTURE CONTENT", str(flight["candidates"]))
        self.assertEqual(flight["retrieval_plan"]["eligibility_policy_version"], POLICY_VERSION)

    def test_provider_gateway_enforces_supplied_decision_and_records_policy(self):
        artifact = ephemeral_provider_artifact(instance_id="fawkes", content="secret",
            artifact_kind="fixture", source_domain="library", privacy="highly_private",
            owner_principal_id="rider:tanner")
        denied = self.policy.evaluate(self.evidence("highly_private", sensitive_category="health"),
            self.context(provider_mode="configured_external_provider", provider_authorized=True,
                         sensitive_request_categories=("health",)))
        allowed = self.policy.evaluate(self.evidence("highly_private", sensitive_category="health"),
            self.context(provider_mode="configured_external_provider", provider_authorized=True,
                         sensitive_request_categories=("health",),
                         grants=("provider.transmit:highly_private",)))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(PermissionError, "provider_transmission_denied"):
                record_provider_transmission(instance_id="fawkes", artifact=artifact,
                    capability_id="chat.respond", provider_class="fixture", purpose="private chat",
                    authorization_source={"mode": "task_request"}, receipt_dir=tmp,
                    eligibility_decision=denied)
            receipt = record_provider_transmission(instance_id="fawkes", artifact=artifact,
                capability_id="chat.respond", provider_class="fixture", purpose="private chat",
                authorization_source={"mode": "task_request"}, receipt_dir=tmp,
                eligibility_decision=allowed)
        self.assertEqual(receipt["eligibility_policy_version"], POLICY_VERSION)
        self.assertFalse(receipt["payload_recorded"])


if __name__ == "__main__":
    unittest.main()
