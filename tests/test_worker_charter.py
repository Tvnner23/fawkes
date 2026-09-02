import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PHOENIX_DOCS = ROOT / "docs" / "phoenix"


class UniversalWorkerCharterContractTests(unittest.TestCase):
    def setUp(self):
        self.charter = (PHOENIX_DOCS / "UNIVERSAL_WORKER_CHARTER.md").read_text(encoding="utf-8")

    def test_canonical_identity_precedence_and_no_authority_grant_are_explicit(self):
        self.assertIn("**Contract ID:** `phoenix.universal_worker_charter`", self.charter)
        self.assertIn("**Version:** 1.0", self.charter)
        self.assertIn("**Status:** Canonical", self.charter)
        self.assertIn("not a capability grant", self.charter)
        self.assertIn("Where\nthis charter is less strict, the stricter contract controls", self.charter)
        self.assertIn("MUST NOT grant authority merely by changing this\ndocument", self.charter)

    def test_future_worker_systems_remain_conceptual_and_non_authorizing(self):
        self.assertIn("Specialist Mesh — architectural direction", self.charter)
        self.assertIn("AI / Tool Scout — architectural direction", self.charter)
        self.assertIn("not an active runtime capability", self.charter)
        self.assertIn("No Tool Scout runtime is implemented", self.charter)
        self.assertIn("Host enforcement MUST NOT be bypassed", self.charter)

    def test_standard_proposal_and_handoff_contracts_are_complete(self):
        for field in ("Title", "Discovered by", "Area", "Observation", "Proposed upgrade",
                      "Fawkes principle fit", "Benefit", "Cost/complexity", "Risks/tradeoffs",
                      "Authority/security impact", "Reversibility", "Validation", "Dependencies",
                      "Cross-system impact", "Recommendation"):
            self.assertIn(f"| {field} |", self.charter)
        for term in ("approved scope", "deliberate non-changes", "tests, failures, defects",
                     "security/privacy", "continuity/identity", "rollback state"):
            self.assertIn(term, self.charter)

    def test_canonical_documents_reference_the_charter(self):
        for name in ("CANONICAL_ROADMAP.md", "CURRENT_IMPLEMENTATION.md", "FOUNDATION.md"):
            self.assertIn("UNIVERSAL_WORKER_CHARTER.md",
                          (PHOENIX_DOCS / name).read_text(encoding="utf-8"))
        external = (ROOT / "docs" / "EXTERNAL_REVIEW_GUIDE.md").read_text(encoding="utf-8")
        self.assertIn("phoenix/UNIVERSAL_WORKER_CHARTER.md", external)

    def test_embodiment_review_items_are_complete_and_non_authorizing(self):
        proposals = (PHOENIX_DOCS / "CROSS_WORKER_IMPROVEMENT_PROPOSALS.md").read_text(encoding="utf-8")
        for title in ("Versioned Semantic Expression Interface",
                      "Automated Fawkes GLB Readiness Gate",
                      "Protected Pose-regression Library"):
            self.assertIn(f"## {title}", proposals)
        self.assertIn("non-authorizing", proposals)
        self.assertIn("do not implement", proposals)


if __name__ == "__main__":
    unittest.main()
