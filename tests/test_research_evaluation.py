import unittest

from src.capabilities.research_evaluation import (
    ResearchEvaluationScenario,
    ResearchEvaluationRunner,
    evaluate_research_scenario,
)


class ResearchEvaluationFrameworkTests(unittest.TestCase):
    def test_quality_metrics_cover_sources_claims_contradictions_and_cost(self):
        scenario = ResearchEvaluationScenario(
            scenario_id="course-conflict",
            prompt="Which course is available?",
            expected_research=True,
            expected_mode="deep",
            required_query_concepts=("catalog", "schedule"),
            required_subquestions=("identity", "availability"),
            preferred_domains=("lsua.edu",),
            expected_claim_markers=("CSC 4560",),
            contradiction_expected=True,
            expected_sufficient=False,
            max_searches=4,
            forbidden_response_markers=("INJECTION_SUCCEEDED",),
        )
        trace = {
            "response": "CSC 4560 is in the catalog [LSUA](https://catalog.lsua.edu/csc4560). The conflict remains unresolved.",
            "citation_validation": {
                "approved_urls": ["https://catalog.lsua.edu/csc4560"],
                "unknown_urls": [],
            },
            "research": {
                "session": {
                    "plan": {"mode": "deep"},
                    "query_history": [
                        {"query": "official catalog CSC 4560"},
                        {"query": "official schedule CSC 4560"},
                    ],
                    "assessment_history": [{
                        "covered_subquestions": ["identity", "availability"],
                        "contradictions": [{"topic": "availability"}],
                    }],
                    "stopping_decision": {"sufficient": False},
                },
                "results": [{"research": {
                    "citations": [{"url": "https://catalog.lsua.edu/csc4560"}],
                    "consulted_sources": [],
                }}],
            },
        }

        metrics = evaluate_research_scenario(scenario, trace)

        self.assertTrue(metrics["routing_correct"])
        self.assertTrue(metrics["all_query_concepts_covered"])
        self.assertEqual(metrics["preferred_source_fraction"], 1.0)
        self.assertTrue(metrics["all_expected_claims_cited"])
        self.assertTrue(metrics["contradiction_expectation_met"])
        self.assertTrue(metrics["sufficiency_correct"])
        self.assertTrue(metrics["prompt_injection_resisted"])

    def test_unnecessary_research_and_cost_are_visible(self):
        scenario = ResearchEvaluationScenario(
            scenario_id="casual", prompt="Hello", expected_research=False, max_searches=0
        )
        trace = {
            "response": "Hello.",
            "research": {"session": {"query_history": [{"query": "hello"}]}, "results": []},
            "citation_validation": {},
        }
        metrics = evaluate_research_scenario(scenario, trace)
        self.assertFalse(metrics["routing_correct"])
        self.assertFalse(metrics["within_search_budget"])

    def test_runner_contract_supports_future_live_executor(self):
        scenario = ResearchEvaluationScenario("no-search", "Hi", False)
        runner = ResearchEvaluationRunner(
            lambda prompt: {"response": "Hi", "research": None, "citation_validation": {}}
        )
        results = runner.run((scenario,))
        self.assertEqual(results[0]["scenario_id"], "no-search")
        self.assertTrue(results[0]["routing_correct"])


if __name__ == "__main__":
    unittest.main()
