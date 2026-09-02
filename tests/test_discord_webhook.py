import json
import tempfile
import traceback
import unittest

from src.runtime.autonomy_supervision import RiderNotificationStore
from src.runtime.discord_webhook import (
    DiscordDeliveryError,
    DiscordWebhookConfiguration,
    DiscordWebhookSender,
)


TEST_ENDPOINT = "https://example.invalid/discord-test-endpoint"


class Response:
    status = 204

    def __enter__(self): return self
    def __exit__(self, *arguments): return False


class DiscordWebhookTests(unittest.TestCase):
    def test_successful_delivery_is_safe_and_zero_authority(self):
        captured = {}

        def opener(outbound, timeout):
            captured.update({"request": outbound, "timeout": timeout})
            return Response()

        sender = DiscordWebhookSender(DiscordWebhookConfiguration(TEST_ENDPOINT), opener=opener)
        with tempfile.TemporaryDirectory() as directory:
            store = RiderNotificationStore("phoenix", root=directory)
            logical, _ = store.create_once(
                kind="needs_tanner", campaign_id="campaign-one", state_key="blocked",
                message="Fawkes: campaign-one needs Tanner. Work is paused; inspect Development.",
                evidence_refs=[{"reference_id": "campaign-one"}],
            )
            delivered = store.deliver(logical, sender)
        payload = json.loads(captured["request"].data)
        self.assertEqual(payload["allowed_mentions"], {"parse": []})
        self.assertNotIn("source", payload["content"].lower())
        self.assertTrue(delivered["delivered"])
        self.assertFalse(delivered["creates_authority"])
        self.assertNotIn(TEST_ENDPOINT, json.dumps(delivered))

    def test_missing_webhook_names_only_environment_variable(self):
        with self.assertRaisesRegex(RuntimeError, "FAWKES_DISCORD_WEBHOOK_URL") as caught:
            DiscordWebhookConfiguration.from_environment({})
        self.assertNotIn("example.invalid", str(caught.exception))

    def test_failed_http_delivery_is_sanitized_and_does_not_change_state(self):
        def failed(*arguments, **keywords):
            raise RuntimeError(f"provider rejected {TEST_ENDPOINT}")

        sender = DiscordWebhookSender(DiscordWebhookConfiguration(TEST_ENDPOINT), opener=failed)
        with tempfile.TemporaryDirectory() as directory:
            store = RiderNotificationStore("phoenix", root=directory)
            logical, _ = store.create_once(kind="periodic_progress", campaign_id="campaign-one",
                state_key="bucket-one", message="Fawkes: campaign-one remains active.", evidence_refs=[])
            retained = store.deliver(logical, sender)
        self.assertFalse(retained["delivered"])
        self.assertEqual(retained["attempts"][0]["failure_code"], "DiscordDeliveryError")
        self.assertFalse(retained["creates_authority"])
        self.assertNotIn(TEST_ENDPOINT, json.dumps(retained))

    def test_configuration_and_errors_redact_secret(self):
        configuration = DiscordWebhookConfiguration(TEST_ENDPOINT)
        self.assertNotIn(TEST_ENDPOINT, repr(configuration))
        sender = DiscordWebhookSender(configuration, opener=lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError(TEST_ENDPOINT)))
        with self.assertRaises(DiscordDeliveryError) as caught:
            sender("Fawkes: safe status only.")
        self.assertNotIn(TEST_ENDPOINT, str(caught.exception))
        rendered = "".join(traceback.format_exception(caught.exception))
        self.assertNotIn(TEST_ENDPOINT, rendered)

    def test_needs_tanner_logical_notification_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RiderNotificationStore("phoenix", root=directory)
            arguments = dict(kind="needs_tanner", campaign_id="campaign-one", state_key="same-blocker",
                message="Fawkes: campaign-one needs Tanner.", evidence_refs=[])
            first, first_created = store.create_once(**arguments)
            second, second_created = store.create_once(**arguments)
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first["notification_id"], second["notification_id"])

    def test_discord_receipt_cannot_create_campaign_authority(self):
        receipt = DiscordWebhookSender(
            DiscordWebhookConfiguration(TEST_ENDPOINT), opener=lambda *a, **k: Response()
        )("Fawkes: campaign-one status is active.")
        self.assertEqual(set(receipt), {"provider", "provider_status", "http_status"})
        self.assertNotIn("authority", receipt)
        self.assertNotIn("approval", receipt)


if __name__ == "__main__":
    unittest.main()
