import unittest

from src.presentation.response import clean_display_url, prepare_response_presentation
from src.presentation.registry import DEFAULT_VISUALIZATION_REGISTRY, VISUALIZATION_CAPABILITY


def research_fixture():
    url = "https://official.example/report?utm_source=openai&year=2026"
    return {
        "session": {"assessment_history": [{"source_assessments": [{
            "url": url, "source_role": "primary_official", "reason": "Official report",
        }]}]},
        "results": [{"research": {
            "citations": [{"url": url, "title": "Official Annual Report"}],
            "consulted_sources": [],
        }}],
    }


class ResponsePresentationTests(unittest.TestCase):
    def test_visualization_registry_and_manifest_report_installed_formats(self):
        self.assertIn("pie", DEFAULT_VISUALIZATION_REGISTRY.names())
        self.assertIn("scatter", VISUALIZATION_CAPABILITY.public_manifest()["features"])
        self.assertNotIn("map", VISUALIZATION_CAPABILITY.public_manifest()["features"])

    def test_text_table_and_named_citation_are_validated(self):
        url = "https://official.example/report?utm_source=openai&year=2026"
        answer = f"""The official comparison is documented in the [annual report]({url}).

```fawkes-presentation
{{"type":"table","title":"Course comparison","fallback":"Course A is online; Course B is on campus.","source_scope":"research","source_urls":["{url}"],"columns":["Course","Format"],"rows":[["A","Online"],["B","Campus"]]}}
```"""
        result = prepare_response_presentation(answer, research_fixture())

        self.assertNotIn("fawkes-presentation", result["archive_text"])
        self.assertIn("Visual — Course comparison", result["archive_text"])
        self.assertEqual(result["presentation"]["blocks"][0]["type"], "table")
        citation = result["presentation"]["citations"][0]
        self.assertEqual(citation["title"], "Official Annual Report")
        self.assertEqual(citation["source_role"], "primary_official")
        self.assertEqual(citation["url"], url)
        self.assertEqual(citation["display_url"], "https://official.example/report?year=2026")

    def test_clean_display_url_in_visual_resolves_to_original_approved_provenance(self):
        original = "https://official.example/report?utm_source=openai&year=2026"
        display = "https://official.example/report?year=2026"
        answer = f'''Difficulty is estimated.
```fawkes-presentation
{{"type":"chart","title":"Estimated ranking","caption":"Estimated, not official.","fallback":"A is estimated at 5.","source_scope":"research","source_urls":["{display}"],"chart_type":"bar","series":[{{"name":"Estimate","points":[{{"label":"A","value":5}}]}}]}}
```'''
        result = prepare_response_presentation(answer, research_fixture())
        self.assertEqual(result["presentation"]["blocks"][0]["source_urls"], [original])

    def test_hostile_or_unapproved_visual_fields_are_not_rendered(self):
        answer = """Safe explanation.
```fawkes-presentation
{"type":"diagram","title":"Bad","fallback":"Safe fallback","source_scope":"reasoning","source_urls":[],"nodes":[{"id":"a","label":"Start"},{"id":"b","label":"End"}],"edges":[{"from":"a","to":"b"}],"onClick":"stealToken()"}
```"""
        result = prepare_response_presentation(answer)

        self.assertEqual(result["presentation"]["blocks"], [])
        self.assertTrue(result["presentation"]["rejected_blocks"])
        self.assertNotIn("stealToken", result["archive_text"])

    def test_chart_rejects_reasoning_or_unapproved_data_provenance(self):
        chart = """Answer.
```fawkes-presentation
{"type":"chart","title":"Invented trend","fallback":"No verified trend.","source_scope":"reasoning","source_urls":[],"chart_type":"line","x_label":"Year","y_label":"Value","series":[{"name":"Values","points":[{"label":"2026","value":12}]}]}
```"""
        result = prepare_response_presentation(chart)
        self.assertEqual(result["presentation"]["blocks"], [])

    def test_clearly_labeled_illustrative_chart_is_renderable_without_becoming_fact(self):
        chart = """A deliberately silly illustration.
```fawkes-presentation
{"type":"chart","title":"Illustrative lameness recovery","caption":"Illustrative values, not measurements.","fallback":"Illustrative values show lameness at 100 and recovery at 100; these are not measured facts.","source_scope":"illustrative","source_urls":[],"chart_type":"pie","series":[{"name":"Illustration","points":[{"label":"Lameness","value":100},{"label":"Not lame","value":0}]}]}
```"""
        result = prepare_response_presentation(chart)
        self.assertEqual(result["presentation"]["blocks"][0]["source_scope"], "illustrative")

    def test_illustrative_scope_drives_server_owned_disclosure_badge(self):
        chart = """An illustration.
```fawkes-presentation
{"type":"chart","title":"Values","caption":"","fallback":"A is 100.","source_scope":"illustrative","source_urls":[],"chart_type":"bar","series":[{"name":"Values","points":[{"label":"A","value":100}]}]}
```"""
        result = prepare_response_presentation(chart)
        self.assertEqual(result["presentation"]["blocks"][0]["source_scope"], "illustrative")

    def test_illustrative_visual_cannot_borrow_research_authority(self):
        url = "https://official.example/report?utm_source=openai&year=2026"
        chart = f"""No.
```fawkes-presentation
{{"type":"chart","title":"Illustration","caption":"Illustrative.","fallback":"Illustrative A is 1.","source_scope":"illustrative","source_urls":["{url}"],"chart_type":"bar","series":[{{"name":"Values","points":[{{"label":"A","value":1}}]}}]}}
```"""
        result = prepare_response_presentation(chart, research_fixture())
        self.assertEqual(result["presentation"]["blocks"], [])
        self.assertIn("cannot claim research", result["presentation"]["rejected_blocks"][0])

    def test_diagram_rejects_unknown_node_reference(self):
        diagram = """Explanation.
```fawkes-presentation
{"type":"diagram","title":"Flow","fallback":"A leads somewhere unknown.","source_scope":"reasoning","source_urls":[],"direction":"vertical","nodes":[{"id":"a","label":"A"},{"id":"b","label":"B"}],"edges":[{"from":"a","to":"missing","label":"next"}]}
```"""
        result = prepare_response_presentation(diagram)
        self.assertEqual(result["presentation"]["blocks"], [])

    def test_linear_flow_diagram_is_preserved_with_text_fallback(self):
        diagram = """Explanation.
```fawkes-presentation
{"type":"diagram","title":"Research flow","fallback":"Question leads to research, then an answer.","source_scope":"reasoning","source_urls":[],"direction":"horizontal","nodes":[{"id":"question","label":"Question"},{"id":"research","label":"Research"},{"id":"answer","label":"Answer"}],"edges":[{"from":"question","to":"research","label":"plan"},{"from":"research","to":"answer","label":"synthesize"}]}
```"""
        result = prepare_response_presentation(diagram)
        self.assertEqual(result["presentation"]["blocks"][0]["direction"], "horizontal")
        self.assertIn("Question leads to research", result["archive_text"])

    def test_only_http_links_can_be_cleaned(self):
        with self.assertRaises(ValueError):
            clean_display_url("javascript:alert(1)")

    def test_pie_scatter_and_timeline_use_distinct_validated_contracts(self):
        answer = """Visuals.
```fawkes-presentation
[
 {"type":"chart","title":"Traffic","fallback":"Web is 70 and mail is 30.","source_scope":"user_supplied","source_urls":[],"chart_type":"pie","series":[{"name":"Traffic","points":[{"label":"Web","value":70},{"label":"Mail","value":30}]}]},
 {"type":"chart","title":"Latency","fallback":"Latency rises with load.","source_scope":"user_supplied","source_urls":[],"chart_type":"scatter","x_label":"Load","y_label":"Latency","series":[{"name":"Tests","points":[{"label":"A","x":10,"y":20},{"label":"B","x":30,"y":55}]}]},
 {"type":"timeline","title":"Block preparation","fallback":"Register, prepare, then start.","source_scope":"user_supplied","source_urls":[],"items":[{"date":"Oct 12","label":"Register"},{"date":"Oct 18","label":"Prepare"},{"date":"Oct 19","label":"Block starts"}]}
]
```"""
        result = prepare_response_presentation(answer)
        self.assertEqual(result["presentation"]["schema_version"], 2)
        self.assertEqual(
            [item.get("chart_type", item["type"]) for item in result["presentation"]["blocks"]],
            ["pie", "scatter", "timeline"],
        )
        self.assertIn("Register, prepare, then start", result["archive_text"])

    def test_pie_rejects_negative_or_multi_series_data(self):
        answer = """No.
```fawkes-presentation
{"type":"chart","title":"Invalid","fallback":"Invalid data.","source_scope":"user_supplied","source_urls":[],"chart_type":"pie","series":[{"name":"Values","points":[{"label":"A","value":-1},{"label":"B","value":2}]}]}
```"""
        self.assertEqual(prepare_response_presentation(answer)["presentation"]["blocks"], [])


if __name__ == "__main__":
    unittest.main()
