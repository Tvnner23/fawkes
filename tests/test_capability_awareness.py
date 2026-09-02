from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from src.capabilities.acceptance import AcceptanceCenter, capability_acceptance_statuses
from src.capabilities.awareness import CapabilityAwareness
from src.capabilities.core import CapabilityAvailabilityCatalog
from src.capabilities.research_orchestrator import (
    ConversationalResearchOrchestrator, ResearchPlan,
)
from src.capabilities.web_research import WebResearchCapability
from src.presentation.registry import VISUALIZATION_CAPABILITY


def manifests():
    catalog = CapabilityAvailabilityCatalog()
    catalog.advertise(VISUALIZATION_CAPABILITY, effects="derived presentation")
    research = WebResearchCapability(provider=Mock()).definition
    catalog.advertise(research, effects="evidence only")
    return catalog.manifests()


class CapabilityAwarenessTests(unittest.TestCase):
    def test_manifest_contains_operational_judgment_not_just_a_tool_name(self):
        visual = next(item for item in manifests() if item["name"] == "presentation.visualize")
        for key in ("appropriate_use", "inappropriate_use", "limitations", "platform_support",
                    "presentation_options", "provenance_requirements", "acceptance_status"):
            self.assertIn(key, visual)
        self.assertIn("scatter", visual["features"])

    def test_lsua_actual_degree_visual_request_composes_research_and_visualization(self):
        selected = CapabilityAwareness(manifests()).select(
            "Make a nice visual chart ranking the actual classes in my LSUA cybersecurity degree."
        )
        by_id = {item.capability_id: item for item in selected}
        self.assertTrue(by_id["web.research"].required)
        self.assertTrue(by_id["presentation.visualize"].required)
        self.assertIn("external facts", by_id["web.research"].relevance)

    def test_casual_and_self_contained_requests_do_not_select_research(self):
        awareness = CapabilityAwareness(manifests())
        self.assertEqual(awareness.select("Tell me a joke."), ())
        self.assertNotIn("web.research", {
            item.capability_id for item in awareness.select("Rewrite this sentence more clearly.")
        })
        self.assertNotIn("web.research", {
            item.capability_id for item in awareness.select("I don't need current information. Explain this concept.")
        })

    def test_planner_cannot_turn_required_external_verification_into_a_guess(self):
        planner = Mock()
        planner.plan.return_value = ResearchPlan(False, "I could estimate instead")
        capability = Mock()
        capability.run.return_value = {"research": {
            "research_id": "r1", "answer": "Official course list", "citations": [{"url": "https://lsua.edu/catalog", "title": "LSUA Catalog"}],
        }, "capability_receipt_id": "receipt-1"}
        with TemporaryDirectory() as tmp:
            orchestrator = ConversationalResearchOrchestrator(
                planner=planner, capability=capability, sessions_dir=tmp, assessor=None,
            )
            result = orchestrator.research_if_needed(
                instance_id="fawkes", user_message="Rank the actual classes in my LSUA degree.", force_research=True,
            )
        self.assertIsNotNone(result)
        capability.run.assert_called_once()
        self.assertIn("LSUA", capability.run.call_args.kwargs["query"])

    def test_acceptance_evidence_is_separate_from_runtime_availability(self):
        class Runtime:
            def capability_context(self): return list(manifests())
        class Service:
            instance_id = "fawkes-awareness"; runtime = Runtime()
            def capabilities(self): return {"capabilities": self.runtime.capability_context()}
            def history(self): return {"messages": []}
            def development_dashboard(self): return {"observations": [], "development_proposals": [], "human_review_items": [], "progression": [], "memory_triage": {"status_counts": {}}}
        with TemporaryDirectory() as tmp:
            center = AcceptanceCenter(Service(), run_dir=tmp)
            started = center.start("presentation.visualization")
            center.complete(started["run_id"], result="pass", actual="4 visible charts", duration_ms=2)
            statuses = capability_acceptance_statuses(instance_id=Service.instance_id, manifests=manifests(), run_dir=tmp)
        visual = next(item for item in manifests() if item["name"] == "presentation.visualize")
        self.assertEqual(visual["availability"], "live")
        self.assertEqual(statuses["presentation.visualize"], "partial")


if __name__ == "__main__": unittest.main()
