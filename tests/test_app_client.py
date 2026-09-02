import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class FawkesAppClientTests(unittest.TestCase):
    def test_connect_flow_survives_storage_denial_and_targets_phone_origin(self):
        result = subprocess.run(
            ["node", "tests/js/app_login_harness.js"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("client-login-flow-ok", result.stdout)

    def test_exact_attention_deep_link_renders_decision_and_resolved_unknown_states(self):
        import os
        for scenario, attention_id in (("valid", "attention-test-a"),
                ("valid", "attention-test-b"), ("auth-login", "attention-test-a"),
                ("resolved", "attention-test"), ("unknown", "attention-test"),
                ("auth", "attention-test")):
            with self.subTest(scenario=scenario, attention_id=attention_id):
                result = subprocess.run(["node", "tests/js/app_attention_deep_link_harness.js"],
                    cwd=ROOT, text=True, capture_output=True, timeout=10,
                    env={**os.environ, "FAWKES_ATTENTION_SCENARIO": scenario,
                         "FAWKES_ATTENTION_ID": attention_id})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("attention-deep-link-ok " + scenario, result.stdout)

    def test_static_build_identity_is_versioned_and_cache_mismatch_is_visible(self):
        html = (ROOT / "src/app/static/index.html").read_text()
        source = (ROOT / "src/app/static/app.js").read_text()
        server = (ROOT / "src/app/server.py").read_text()
        self.assertIn("/app.js?v=__FAWKES_BUILD_ID__", html)
        self.assertIn("/app.css?v=__FAWKES_BUILD_ID__", html)
        self.assertIn("X-Fawkes-Build-ID", server)
        self.assertIn('"Cache-Control", "no-store"', server)
        self.assertIn("BUILD MISMATCH", source)

    def test_attention_decision_outcomes_are_plain_and_fail_closed(self):
        source = (ROOT / "src/app/static/app.js").read_text()
        self.assertIn("recorded_pending_consumption", source)
        self.assertIn("The exact one-time grant was consumed", source)
        self.assertIn("restart-safe bounded continuation", source)
        self.assertIn("exact approved action completed", source)
        self.assertIn("approval is no longer available", source)
        self.assertIn("Fawkes did not record an approval", source)

    def test_authentication_uses_protected_cookie_session_and_preserves_deep_link(self):
        source = (ROOT / "src/app/static/app.js").read_text()
        server = (ROOT / "src/app/server.py").read_text()
        self.assertNotIn("fawkes-app-token", source)
        self.assertIn("/api/session", source)
        self.assertIn("credentials: 'same-origin'", source)
        self.assertIn("requestedAttentionId = startup.get('attention')", source)
        self.assertIn("if(connected&&requestedAttentionId)await loadExactAttention()", source)
        self.assertIn("HttpOnly; SameSite=Strict", server)
        self.assertIn("Max-Age={SESSION_MAX_AGE_SECONDS}", server)

    def test_attention_identity_mismatch_and_request_failure_cannot_load_forever(self):
        source = (ROOT / "src/app/static/app.js").read_text()
        self.assertIn("Fawkes returned a different attention identity", source)
        self.assertIn("Fawkes did not answer within 15 seconds", source)
        self.assertIn("exactAttentionLoadGeneration", source)

    def test_attention_decision_submission_is_immutable_tuple_bound(self):
        source = (ROOT / "src/app/static/app.js").read_text()
        self.assertIn("const immutableIdentity={attention_id:attention.attention_id", source)
        self.assertIn("identity:immutableIdentity", source)
        self.assertIn("protocol_binding_sha256", source)
        self.assertIn("action_digest", source)
        self.assertIn("Qualification instruction", source)
        self.assertIn("Fawkes’s risk-based recommendation", source)
        self.assertIn("Approve Once — ${qualificationChoice==='Approve Once'?'Test A'", source)
        self.assertIn("Deny — ${qualificationChoice==='Deny'?'Test B'", source)

    def test_client_avoids_known_older_safari_parse_breakers(self):
        source = (ROOT / "src" / "app" / "static" / "app.js").read_text()
        self.assertNotIn("?.", source)
        self.assertNotIn(".replaceAll(", source)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("new Date()", source)
        self.assertIn("That access token was not accepted", source)

    def test_attachment_ui_discloses_audio_and_ephemeral_processing(self):
        html = (ROOT / "src" / "app" / "static" / "index.html").read_text()
        source = (ROOT / "src" / "app" / "static" / "app.js").read_text()
        self.assertIn("audio/mpeg", html)
        self.assertIn("application/pdf", html)
        self.assertIn("not written to durable temporary storage", source)
        self.assertIn("not securely zeroized", source)
        self.assertIn("Keep in Library", source)
        self.assertIn("Library PDF extraction is local", source)
        self.assertIn("Analyzing media", source)
        self.assertIn("Attach image, PDF, or audio", html)

    def test_visual_styles_cover_mobile_light_dark_and_long_labels(self):
        css = (ROOT / "src" / "app" / "static" / "app.css").read_text()
        self.assertIn("@media (max-width: 480px)", css)
        self.assertIn("@media (prefers-color-scheme: light)", css)
        self.assertIn("color-scheme: dark", css)
        self.assertIn("overflow-wrap: anywhere", css)
        self.assertIn(".visual-card > svg", css)

    def test_manual_history_ui_discloses_domains_and_original_authority(self):
        html = (ROOT / "src" / "app" / "static" / "index.html").read_text()
        source = (ROOT / "src" / "app" / "static" / "app.js").read_text()
        self.assertIn('id="history-view"', html)
        self.assertIn("Summary for navigation. Original text for truth.", html)
        self.assertIn("/api/history/search", source)
        self.assertIn("OPEN EXACT ORIGINAL", source)
        self.assertIn("Results never enter Chat or Memory", source)

    def test_rider_chat_renders_and_submits_turn_bound_retrieval_clarification(self):
        result = subprocess.run(
            ["node", "tests/js/app_retrieval_clarification_harness.js"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("client-retrieval-clarification-ok", result.stdout)

    def test_retrieval_clarification_controls_have_accessible_visible_states(self):
        css = (ROOT / "src" / "app" / "static" / "app.css").read_text()
        self.assertIn(".clarification-choice:focus-visible", css)
        self.assertIn('.clarification-choice[aria-pressed="true"]', css)
        self.assertIn(".clarification-choice:disabled", css)

    def test_context_inspector_is_accessible_lazy_and_body_free_by_contract(self):
        source = (ROOT / "src" / "app" / "static" / "app.js").read_text()
        css = (ROOT / "src" / "app" / "static" / "app.css").read_text()
        self.assertIn("Why this context?", source)
        self.assertIn("contains_source_bodies !== false", source)
        self.assertIn("context_inspector_available", source)
        self.assertIn("/context-inspector", source)
        self.assertIn(".context-inspector > summary:focus-visible", css)
        self.assertIn("Feedback recorded as Development evidence. It changes nothing automatically.", source)
        self.assertIn(".context-feedback-choice:focus-visible", css)
        self.assertIn('.context-feedback-choice[aria-pressed="true"]', css)


if __name__ == "__main__":
    unittest.main()
