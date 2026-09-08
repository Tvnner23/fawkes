import copy
import unittest

from src.runtime.evidence_eligibility import EvidenceUseContext, ProductionEvidenceEligibilityPolicy
from src.runtime.legacy_compatibility import (
    COMPATIBILITY_VERSION, DERIVED_CLASSIFICATION, apply_legacy_compatibility,
    build_legacy_review_projection, derive_legacy_compatibility,
)


class LegacyCompatibilityTests(unittest.TestCase):
    def evidence(self, domain="native_archive", **changes):
        value = {"instance_id": "fawkes", "domain": domain,
            "evidence_id": "archive-1" if domain == "native_archive" else "memory-1",
            "authority_class": "native_canonical_evidence" if domain == "native_archive" else "derived_memory_evidence",
            "original_evidence_reference": {"archive_id": "archive-1"},
            "provenance_valid": True, "automatic_use_enabled": True,
            "continuity_ownership_basis": "scoped_instance_record",
            "source_schema_version": 1, "eligibility_flags": [],
            "text": "SENSITIVE LEGACY BODY"}
        value.update(changes); return value

    def context(self, **changes):
        values = dict(instance_id="fawkes", rider_principal_id="rider:tanner",
            capability_id="chat.respond", capability_authorized=True,
            provider_mode="local_only")
        values.update(changes); return EvidenceUseContext(**values)

    def projected(self, evidence):
        decision = derive_legacy_compatibility(evidence, instance_id="fawkes",
                                               rider_principal_id="rider:tanner")
        return decision, apply_legacy_compatibility(evidence, decision)

    def test_same_phoenix_legacy_archive_and_memory_are_compatibility_eligible(self):
        for domain in ("native_archive", "memory"):
            original = self.evidence(domain); snapshot = copy.deepcopy(original)
            compatibility, projected = self.projected(original)
            policy = ProductionEvidenceEligibilityPolicy().evaluate(projected, self.context())
            self.assertEqual(compatibility["derived_compatibility_classification"], DERIVED_CLASSIFICATION)
            self.assertTrue(policy["automatic_private_context"]["allowed"])
            self.assertFalse(policy["explicit_modern_classification"])
            self.assertEqual(policy["legacy_compatibility"]["compatibility_version"], COMPATIBILITY_VERSION)
            self.assertEqual(original, snapshot)

    def test_foreign_uncertain_malformed_and_blocked_records_fail_closed(self):
        cases = [
            (self.evidence(instance_id="other"), "ownership_uncertain"),
            (self.evidence(continuity_ownership_basis=None), "ownership_uncertain"),
            (self.evidence(provenance_valid=False), "blocked"),
            (self.evidence(eligibility_flags=["quarantined"]), "blocked"),
        ]
        for evidence, status in cases:
            decision, projected = self.projected(evidence)
            self.assertEqual(decision["migration_status"], status)
            self.assertNotIn("legacy_compatibility", projected)

    def test_explicit_modern_privacy_and_owner_always_win(self):
        policy = ProductionEvidenceEligibilityPolicy()
        for privacy, expected in (("potentially_private", True),
                                  ("highly_private", False), ("restricted", False)):
            evidence = self.evidence(privacy_classification=privacy,
                owner_principal_id="rider:tanner")
            compatibility, projected = self.projected(evidence)
            decision = policy.evaluate(projected, self.context())
            self.assertEqual(compatibility["migration_status"], "explicit_classification_present")
            self.assertTrue(decision["explicit_modern_classification"])
            self.assertEqual(decision["automatic_private_context"]["allowed"], expected)
            self.assertIsNone(decision["legacy_compatibility"])

    def test_compatibility_can_be_locally_eligible_while_provider_is_denied(self):
        _, projected = self.projected(self.evidence())
        decision = ProductionEvidenceEligibilityPolicy().evaluate(projected, self.context(
            provider_mode="configured_external_provider", provider_authorized=False))
        self.assertFalse(decision["automatic_private_context"]["allowed"])
        self.assertEqual(decision["automatic_private_context"]["reason"], "provider_transmission_denied")
        self.assertFalse(decision["provider_transmission"]["allowed"])

    def test_compatibility_never_grants_external_cross_rider_or_cross_phoenix_access(self):
        _, projected = self.projected(self.evidence())
        for context in (self.context(external_recipient_id="tool:mail"),
                        self.context(target_rider_principal_id="rider:other"),
                        self.context(target_instance_id="other")):
            decision = ProductionEvidenceEligibilityPolicy().evaluate(projected, context)
            self.assertFalse(decision["external_disclosure"]["allowed"])
            self.assertFalse(decision["cross_principal_disclosure"]["allowed"])

    def test_high_score_cannot_bypass_ineligible_compatibility(self):
        evidence = self.evidence(eligibility_flags=["restricted"], retrieval_score=999999)
        compatibility, projected = self.projected(evidence)
        self.assertEqual(compatibility["migration_status"], "blocked")
        self.assertNotIn("legacy_compatibility", projected)

    def test_review_projection_is_deterministic_rebuildable_and_body_free(self):
        records = [self.evidence(), self.evidence("memory", continuity_ownership_basis=None),
                   self.evidence(privacy_classification="restricted", owner_principal_id="rider:tanner")]
        first = build_legacy_review_projection(records, instance_id="fawkes",
                                               rider_principal_id="rider:tanner")
        second = build_legacy_review_projection(records, instance_id="fawkes",
                                                rider_principal_id="rider:tanner")
        self.assertEqual(first, second)
        self.assertTrue(first["rebuildable"])
        self.assertFalse(first["canonical_records_modified"])
        self.assertNotIn("SENSITIVE LEGACY BODY", str(first))
        self.assertEqual(first["summary"], {"compatibility_eligible": 1,
            "ownership_uncertain": 1, "explicit_classification_present": 1})

    def test_audit_metadata_preserves_basis_schema_review_and_no_body(self):
        _, projected = self.projected(self.evidence())
        decision = ProductionEvidenceEligibilityPolicy().evaluate(projected, self.context())
        audit = decision["legacy_compatibility"]
        self.assertEqual(audit["source_schema_version"], 1)
        self.assertEqual(audit["ownership_provenance_basis"], "scoped_instance_record")
        self.assertEqual(audit["review_status"], "not_reviewed")
        self.assertFalse(audit["canonical_record_modified"])
        self.assertNotIn("SENSITIVE LEGACY BODY", str(decision))


if __name__ == "__main__": unittest.main()
