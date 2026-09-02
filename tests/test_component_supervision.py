import io
import tempfile
import unittest
from contextlib import redirect_stdout

from src.runtime.component_supervision import ComponentReceiptStore


class ComponentSupervisionTests(unittest.TestCase):
    def test_exact_codes_retained_and_sensitive_content_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            secret, private = "not-a-real-token", "private rider message"
            with redirect_stdout(output):
                record, path = ComponentReceiptStore(directory).failure(
                    component="discord_bridge", stage="receive", category="gateway_close",
                    exception=RuntimeError(f"token={secret} message_content={private} https://sensitive.invalid/path"),
                    process_exit_code=1, provider_code=1000, restart_attempt=3,
                    service_state="activating", notify=True, secrets=(secret, private))
            rendered = path.read_text(encoding="utf-8") + output.getvalue()
            self.assertEqual((record["provider_code"], record["process_exit_code"]), (1000, 1))
            self.assertNotIn(secret, rendered)
            self.assertNotIn(private, rendered)
            self.assertNotIn("sensitive.invalid", rendered)

    def test_identical_failure_notifications_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ComponentReceiptStore(directory)
            record, _ = store.failure(component="app_server", stage="process_exit",
                                      category="exit-code", process_exit_code=1)
            first, created = store.queue_notification(record)
            second, duplicate = store.queue_notification({**record, "failure_id": "different"})
            self.assertTrue(created)
            self.assertFalse(duplicate)
            self.assertEqual(first, second)

    def test_recovery_receipt_matches_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ComponentReceiptStore(directory)
            failure, _ = store.failure(component="discord_bridge", stage="receive", category="network")
            recovery, _ = store.recovery(failure)
            self.assertEqual(recovery["failure_id"], failure["failure_id"])
            self.assertTrue(recovery["recovered"])
