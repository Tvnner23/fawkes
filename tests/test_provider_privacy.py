import base64
import json
import tempfile
import unittest
from pathlib import Path

from src.capabilities.media_chat import validate_chat_media
from src.capabilities.provider_privacy import record_provider_transmission
from src.capabilities.web_research import WebResearchCapability


class ProviderPrivacyReceiptTests(unittest.TestCase):
    def test_receipt_is_instance_scoped_idempotent_and_contains_no_payload(self):
        payload = base64.b64encode(b"\x89PNG\r\n\x1a\nprivate-image").decode()
        artifact = validate_chat_media([{"name": "x.png", "mime_type": "image/png", "data": payload}],
                                       instance_id="phoenix-one", owner_principal_id="rider-one")[0]["artifact"]
        with tempfile.TemporaryDirectory() as tmp:
            kwargs = dict(instance_id="phoenix-one", artifact=artifact,
                          capability_id="media.chat_analyze", provider_class="test-adapter",
                          purpose="test analysis", authorization_source={"mode": "task_request"},
                          status="completed", correlation_id="message-one", receipt_dir=tmp)
            first = record_provider_transmission(**kwargs)
            second = record_provider_transmission(**kwargs)
            encoded = next((Path(tmp) / "phoenix-one").rglob("*.json")).read_text()
        self.assertEqual(first["transmission_id"], second["transmission_id"])
        self.assertFalse(first["payload_recorded"])
        self.assertNotIn("private-image", encoded)

    def test_authorization_and_outcome_are_separate_immutable_receipts(self):
        payload = base64.b64encode(b"%PDF-1.7\nx").decode()
        artifact = validate_chat_media([{"name": "x.pdf", "mime_type": "application/pdf", "data": payload}],
                                       instance_id="phoenix-one", owner_principal_id="rider-one")[0]["artifact"]
        with tempfile.TemporaryDirectory() as tmp:
            kwargs = dict(instance_id="phoenix-one", artifact=artifact,
                capability_id="media.chat_analyze", provider_class="test", purpose="analysis",
                authorization_source={"mode": "task_request"}, correlation_id="message-one", receipt_dir=tmp)
            authorized = record_provider_transmission(status="authorized", **kwargs)
            completed = record_provider_transmission(status="completed", **kwargs)
            receipts = list((Path(tmp) / "phoenix-one").rglob("*.json"))
        self.assertEqual(authorized["transmission_id"], completed["transmission_id"])
        self.assertNotEqual(authorized["receipt_id"], completed["receipt_id"])
        self.assertEqual(len(receipts), 2)

    def test_receipt_rejects_cross_phoenix_artifact(self):
        payload = base64.b64encode(b"%PDF-1.7\nx").decode()
        artifact = validate_chat_media([{"name": "x.pdf", "mime_type": "application/pdf", "data": payload}],
                                       instance_id="phoenix-one", owner_principal_id="rider-one")[0]["artifact"]
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError, "ownership"):
            record_provider_transmission(instance_id="phoenix-two", artifact=artifact,
                capability_id="media.chat_analyze", provider_class="test", purpose="test",
                authorization_source={"mode": "task_request"}, receipt_dir=tmp)

    def test_web_research_uses_same_authorized_outcome_receipt_boundary(self):
        class Provider:
            model = "fixture"; name = "fixture"
            def research(self, query, **kwargs):
                return {"provider": self.name, "model": self.model, "answer": "answer",
                        "citations": [], "consulted_sources": [], "provider_actions": []}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capability = WebResearchCapability(provider=Provider(), research_dir=root / "research",
                receipt_dir=root / "capability", provider_receipt_dir=root / "transmissions")
            result = capability.run(instance_id="one", query="current public fact",
                task_authorized=True, request_message_id="message-one")
            receipts = [json.loads(path.read_text()) for path in (root / "transmissions/one").rglob("*.json")]
        self.assertEqual({item["status"] for item in receipts}, {"authorized", "completed"})
        self.assertEqual(result["research"]["provider_transmission_id"], receipts[0]["transmission_id"])
        self.assertNotIn("current public fact", json.dumps(receipts))


if __name__ == "__main__":
    unittest.main()
