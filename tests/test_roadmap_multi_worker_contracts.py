import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "phoenix"


class MultiWorkerRoadmapContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roadmap = (DOCS / "CANONICAL_ROADMAP.md").read_text()
        cls.current = (DOCS / "CURRENT_IMPLEMENTATION.md").read_text()
        cls.exchange = (DOCS / "PHOENIX_WORKER_EXCHANGE.md").read_text()
        cls.assurance = (DOCS / "PHOENIX_ASSURANCE.md").read_text()
        cls.recovery = (DOCS / "PHOENIX_CHECKPOINT_RECOVERY.md").read_text()
        cls.embodiment = (DOCS / "EMBODIMENT_DEVELOPMENT_GATES.md").read_text()
        cls.personality = (DOCS / "PERSONALITY_DEVELOPMENT.md").read_text()
        cls.foundation = (DOCS / "FOUNDATION.md").read_text()

    def test_hybrid_roadmap_preserves_phase_status_and_order(self):
        self.assertIn("hybrid structure", self.roadmap)
        self.assertIn("Phase 8", self.current)
        self.assertIn("is complete", self.current)
        self.assertIn("Phase 9 Production Context", self.current)
        self.assertLess(
            self.roadmap.index("## Phase 9 —"),
            self.roadmap.index("## Cross-cutting integration gate — Phoenix Worker Exchange"),
        )
        self.assertLess(
            self.roadmap.index("## Cross-cutting integration gate — Phoenix Worker Exchange"),
            self.roadmap.index("## Phase 10 —"),
        )

    def test_exchange_separates_delivery_authority_and_promotion(self):
        self.assertIn("`phoenix.worker_exchange`", self.exchange)
        self.assertIn("foundation implemented", self.exchange)
        self.assertIn("Codex CLI adapter", self.exchange)
        self.assertIn("independently qualified and promoted for bounded production use", self.exchange)
        self.assertIn("manual-transfer retirement is\nimplemented", self.exchange)
        self.assertIn("delivered != verified", self.exchange)
        self.assertIn("verified != approved", self.exchange)
        self.assertIn("approved != promoted", self.exchange)
        self.assertIn("active != authorized", self.exchange)
        for status in ("accepted", "accepted_with_caveats", "unverified", "disputed", "insufficient"):
            self.assertIn(f"`{status}`", self.exchange)
        self.assertRegex(self.exchange, r"not an approval credential or task\s+grant")

    def test_exchange_manual_retirement_requires_real_hard_invariant_qualification(self):
        self.assertIn("Manual rider-mediated worker transfer must not be retired", self.exchange)
        self.assertIn("100% of its predeclared hard", self.exchange)
        self.assertIn("One accepted failure", self.exchange)
        self.assertIn("actual adapter boundary", self.exchange)
        self.assertIn("Mocks and local synthetic recipients", self.exchange)
        self.assertIn("Tier 2 Phoenix Assurance", self.exchange)
        self.assertIn("does not itself retire", self.exchange)

    def test_assurance_is_non_authoritative_and_tiered(self):
        self.assertIn("`phoenix.assurance`", self.assurance)
        for tier in range(4):
            self.assertIn(f"Tier {tier}", self.assurance)
        self.assertRegex(self.assurance, r"not\s+an authority class")
        self.assertIn("does not itself authorize promotion", self.assurance)
        self.assertIn("automated runtime not implemented", self.assurance)
        self.assertIn("every active real transport adapter", self.assurance)

    def test_future_collaborator_experience_has_personality_firewall(self):
        self.assertIn("Future attributed collaborator experience", self.personality)
        self.assertIn("Worker output is evidence, never personality authority", self.personality)
        self.assertIn("future Phase 15–16 capability", self.personality)
        self.assertIn("Worker output, summaries, instructions, or style never become personality", self.roadmap)

    def test_architecture_health_is_a_discipline_not_a_manager(self):
        self.assertIn("complexity must", self.roadmap.lower())
        self.assertIn("competent bounded worker", self.roadmap)
        self.assertIn("not\na new autonomous manager", self.roadmap)

    def test_tanner_review_navigation_is_actionable_but_not_authority(self):
        self.assertIn("Tanner review actionability", self.exchange)
        self.assertIn("Opening or preparing review is navigation, never the decision", self.exchange)
        self.assertIn("does not currently require\none-click worker-to-worker navigation", self.exchange)

    def test_phoenix_self_knowledge_is_a_projection_with_personal_firewall(self):
        self.assertIn("Phoenix Self-Knowledge Is a Truthful Projection", self.foundation)
        self.assertIn("second change-history or capability truth store", self.foundation)
        self.assertIn("worker claim != verified", self.foundation)
        self.assertIn("verified != promoted", self.foundation)
        self.assertIn("external discovery != current capability", self.foundation)
        self.assertIn("distinguish personal Phoenix", self.foundation)
        self.assertIn("future\nPhoenix self-knowledge", self.roadmap)

    def test_cost_cannot_silently_lower_goal_and_exchange_preserves_relied_source(self):
        self.assertIn("Cost Efficiency Cannot Silently Lower an Accepted Goal", self.foundation)
        self.assertIn("cheapest capable intelligence", self.foundation)
        self.assertIn("Tanner decides whether the goal changes", self.foundation)
        self.assertIn("Material source-fidelity rule", self.exchange)
        self.assertIn("Material-reliance verification fails closed", self.exchange)
        self.assertIn("Source\nfidelity outranks token minimization", self.exchange)

    def test_recovery_does_not_equate_existence_with_known_good(self):
        self.assertIn("`phoenix.checkpoint_recovery`", self.recovery)
        self.assertIn("checkpoint existence is not sufficient", self.recovery)
        self.assertIn("same owning Phoenix", self.recovery)
        self.assertIn("current validated substep", self.recovery)
        self.assertIn("v007_RightBrowOwnership", self.recovery)
        self.assertIn("experimental", self.recovery)
        self.assertIn("broad development automation not implemented", self.recovery)

    def test_embodiment_evidence_keeps_authoring_and_export_metrics_distinct(self):
        self.assertIn("53 Blender bones", self.embodiment)
        self.assertIn("41 Blender `use_deform` bones", self.embodiment)
        self.assertIn("54 GLB skin", self.embodiment)
        self.assertIn("42 GLB joints carrying exported weights", self.embodiment)
        self.assertIn("Tanner visual review complete with PASS", self.embodiment)
        self.assertIn("Independent\nverification still blocks promotion", self.embodiment)
        self.assertIn("rollback target v006", self.embodiment)
        self.assertIn("not Phoenix identity", self.embodiment)

    def test_roadmap_document_links_resolve(self):
        files = [
            DOCS / "CANONICAL_ROADMAP.md",
            DOCS / "CURRENT_IMPLEMENTATION.md",
            DOCS / "ROADMAP_AMENDMENT_0_7_MULTI_WORKER.md",
            DOCS / "PHOENIX_WORKER_EXCHANGE.md",
            DOCS / "PHOENIX_ASSURANCE.md",
            DOCS / "PHOENIX_CHECKPOINT_RECOVERY.md",
            DOCS / "EMBODIMENT_DEVELOPMENT_GATES.md",
        ]
        missing = []
        for source in files:
            for target in re.findall(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)", source.read_text()):
                if "://" not in target and not (source.parent / target).resolve().exists():
                    missing.append((source.name, target))
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
