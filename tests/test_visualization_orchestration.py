import unittest

from src.presentation.orchestrator import (
    OpenAIPresentationPlanner, detect_visualization_intent, visualization_fulfillment,
)
from src.presentation.response import prepare_response_presentation
import json
from src.runtime.chat import FawkesChatRuntime
from src.memory.correction import CorrectionAssessment


class SequenceResponses:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        output = self.outputs.pop(0)
        return type("Response", (), {"output_text": output, "usage": None})()


class EmptyRetriever:
    def rank(self, **kwargs): return []


class NoCorrection:
    def evaluate_correction(self, **kwargs):
        return CorrectionAssessment(
            is_correction=False, confidence=1.0, reasoning="Not a correction."
        )


def four_blocks(scope="illustrative"):
    return f"""```fawkes-presentation
[
{{"type":"chart","title":"Illustrative bar","caption":"Illustrative values.","fallback":"Illustrative A is 100 and B is 0.","source_scope":"{scope}","source_urls":[],"chart_type":"bar","series":[{{"name":"A","points":[{{"label":"A","value":100}},{{"label":"B","value":0}}]}}]}},
{{"type":"chart","title":"Illustrative line","caption":"Illustrative values.","fallback":"Illustrative values rise from 0 to 100.","source_scope":"{scope}","source_urls":[],"chart_type":"line","series":[{{"name":"Rise","points":[{{"label":"Start","value":0}},{{"label":"End","value":100}}]}}]}},
{{"type":"chart","title":"Illustrative pie","caption":"Illustrative values.","fallback":"Illustrative split is 100 to 0.","source_scope":"{scope}","source_urls":[],"chart_type":"pie","series":[{{"name":"Split","points":[{{"label":"Lame","value":100}},{{"label":"Not lame","value":0}}]}}]}},
{{"type":"chart","title":"Illustrative donut","caption":"Illustrative values.","fallback":"Illustrative recovery is 100 to 0.","source_scope":"{scope}","source_urls":[],"chart_type":"donut","series":[{{"name":"Recovery","points":[{{"label":"Potential","value":100}},{{"label":"None","value":0}}]}}]}}
]
```"""


class VisualizationIntentTests(unittest.TestCase):
    def test_natural_explicit_requests_are_detected_without_triggering_on_commentary(self):
        cases = {
            "Make me a pie chart.": (1, ("pie",)),
            "Make four separate charts including a pie chart.": (4, ("pie",)),
            "Graph this.": (1, ()),
            "Draw the network.": (1, ("flow",)),
            "Show me this visually.": (1, ()),
        }
        for prompt, expected in cases.items():
            with self.subTest(prompt=prompt):
                intent = detect_visualization_intent(prompt)
                self.assertTrue(intent.explicit)
                self.assertEqual((intent.count, intent.requested_formats), expected)
        self.assertEqual(
            detect_visualization_intent("Make four charts.").requested_block_type,
            "chart",
        )
        self.assertFalse(detect_visualization_intent("That chart looks weird.").explicit)

    def test_unavailable_format_is_reported_not_substituted(self):
        intent = detect_visualization_intent("Make me a bubble chart.")
        self.assertEqual(intent.unavailable_formats, ("bubble",))
        self.assertEqual(visualization_fulfillment(intent, [
            {"type": "chart", "chart_type": "bar"}
        ])["status"], "unsupported")

    def test_natural_retry_inherits_recent_unfulfilled_visualization_intent(self):
        context = (
            {"role": "user", "content": "Make four charts including a pie chart."},
            {"role": "assistant", "content": "Here are the values in text."},
            {"role": "user", "content": "can you try that again for me"},
            {"role": "assistant", "content": "Fresh attempt."},
        )
        for retry in ("i dont see anything", "nothing rendered", "show them again"):
            with self.subTest(retry=retry):
                intent = detect_visualization_intent(
                    retry, conversation_context=context
                )
                self.assertTrue(intent.explicit)
                self.assertEqual(intent.count, 4)
                self.assertEqual(intent.requested_block_type, "chart")
                self.assertIn("pie", intent.requested_formats)

    def test_openai_adapter_uses_strict_schema_then_normalizes_transport(self):
        raw = {
            "type": "chart", "title": "Illustrative pie", "caption": "Illustrative.",
            "fallback": "Illustrative A is 100.", "source_scope": "illustrative",
            "source_urls": [], "columns": [], "rows": [], "direction": "vertical",
            "nodes": [], "edges": [], "chart_type": "pie", "x_label": "", "y_label": "",
            "series": [{"name": "Values", "points": [
                {"label": "A", "value": 100, "x": None, "y": None},
                {"label": "B", "value": 0, "x": None, "y": None},
            ]}], "items": [],
        }
        responses = SequenceResponses([json.dumps({"blocks": [raw]})])
        planner = OpenAIPresentationPlanner(
            client=type("Client", (), {"responses": responses})(), model="test-model"
        )
        result = planner.create_blocks(
            intent=detect_visualization_intent("Make me a pie chart."),
            user_message="Make me a pie chart.", conversation_context="",
            draft_answer="An illustration.", approved_source_urls=(),
        )
        prepared = prepare_response_presentation(result)
        self.assertEqual(prepared["presentation"]["blocks"][0]["chart_type"], "pie")
        self.assertTrue(responses.calls[0]["text"]["format"]["strict"])


class VisualizationRuntimeAcceptanceTests(unittest.TestCase):
    def _runtime(self, outputs):
        responses = SequenceResponses(outputs)
        client = type("Client", (), {"responses": responses})()
        runtime = FawkesChatRuntime(
            client=client, model="test-model", instance_id=None,
            research_enabled=False,
        )
        runtime.semantic_retriever = EmptyRetriever()
        runtime.correction_evaluator = NoCorrection()
        runtime.paid_call_guard.require_confirmation = False
        return runtime, responses

    def test_original_failure_shape_is_repaired_into_four_actual_blocks(self):
        rejected = "Here are the values.\n\n" + four_blocks(scope="reasoning")
        runtime, responses = self._runtime([rejected, four_blocks()])
        result = runtime.respond(
            user_message="Make the 4 charts, corn ball. Show me your new power."
        )
        self.assertEqual(len(responses.calls), 2)
        self.assertEqual(len(result["presentation"]["blocks"]), 4)
        self.assertEqual(result["presentation"]["fulfillment"]["status"], "fulfilled")
        self.assertIn("pie", result["presentation"]["fulfillment"]["rendered_formats"])
        self.assertTrue(all(
            block["source_scope"] == "illustrative"
            for block in result["presentation"]["blocks"]
        ))

    def test_valid_explicit_chart_does_not_pay_for_repair(self):
        runtime, responses = self._runtime(["Here it is.\n" + four_blocks()])
        result = runtime.respond(user_message="Make four charts including a pie chart.")
        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(result["presentation"]["fulfillment"]["status"], "fulfilled")

    def test_unsupported_chart_is_honest_and_does_not_invoke_repair(self):
        runtime, responses = self._runtime(["I do not have that renderer."])
        result = runtime.respond(user_message="Make me a bubble chart.")
        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(result["presentation"]["fulfillment"]["status"], "unsupported")
        self.assertIn("cannot render", result["text"])


if __name__ == "__main__":
    unittest.main()
