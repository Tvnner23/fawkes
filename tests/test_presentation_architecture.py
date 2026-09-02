import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class PhoenixPresentationArchitectureTests(unittest.TestCase):
    def test_presentation_contract_preserves_stable_rider_controls(self):
        text = (ROOT / "docs" / "phoenix" / "PRESENTATION_ARCHITECTURE.md").read_text(
            encoding="utf-8"
        )
        for required in (
            "Chat and message composition",
            "primary navigation",
            "authentication",
            "Settings",
            "security",
            "Developer",
            "reversible",
            "instance-",
            "declarative rather than executable",
        ):
            self.assertIn(required, text)
        self.assertIn("No prank or autonomous presentation behavior is implemented", text)

    def test_current_client_keeps_chat_auth_and_developer_skeleton(self):
        html = (ROOT / "src" / "app" / "static" / "index.html").read_text(
            encoding="utf-8"
        )
        for stable_id in (
            'id="auth"',
            'id="chat-view"',
            'id="composer"',
            'id="developer-view"',
            'data-view="chat"',
            'data-view="developer"',
        ):
            self.assertIn(stable_id, html)

    def test_reserved_growth_and_presentation_surfaces_have_no_control_engine(self):
        dashboard = (ROOT / "src" / "memory" / "development_dashboard.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"presentation_development": []', dashboard)
        self.assertIn('"growth_assessment": None', dashboard)
        self.assertNotIn("personality_score", dashboard)
        self.assertNotIn("apply_personality", dashboard)

    def test_presentation_formats_are_runtime_registered_not_a_fixed_chat_enum(self):
        registry = (ROOT / "src" / "presentation" / "registry.py").read_text(
            encoding="utf-8"
        )
        architecture = (ROOT / "docs" / "phoenix" / "PRESENTATION_ARCHITECTURE.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("class VisualizationRegistry", registry)
        self.assertIn("capability discovery", architecture)
        self.assertIn("canonical fallback", architecture)


if __name__ == "__main__":
    unittest.main()
