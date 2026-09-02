import json
import unittest
from urllib import parse

from src.runtime.twilio_sms import TwilioSmsConfiguration, TwilioSmsSender


class Response:
    def __enter__(self): return self
    def __exit__(self, *arguments): return False
    def read(self): return json.dumps({"sid": "SM-test", "status": "queued"}).encode()


class TwilioSmsTests(unittest.TestCase):
    def test_configuration_requires_environment_without_disclosing_values(self):
        with self.assertRaisesRegex(RuntimeError, "FAWKES_TWILIO_AUTH_TOKEN") as caught:
            TwilioSmsConfiguration.from_environment({})
        self.assertNotIn("secret", str(caught.exception))

    def test_sender_posts_sanitized_body_and_returns_body_free_receipt(self):
        captured = {}
        def opener(outbound, timeout):
            captured.update({"request": outbound, "timeout": timeout})
            return Response()
        config = TwilioSmsConfiguration("AC-test", "secret", "+15550000001", "+15550000002")
        receipt = TwilioSmsSender(config, opener=opener)("Fawkes test. No action required.")
        fields = parse.parse_qs(captured["request"].data.decode())
        self.assertEqual(fields["Body"], ["Fawkes test. No action required."])
        self.assertEqual(receipt, {"provider": "twilio", "message_sid": "SM-test",
                                   "provider_status": "queued"})
        self.assertNotIn("secret", json.dumps(receipt))
        self.assertNotIn("+1555", json.dumps(receipt))

    def test_sender_rejects_empty_or_unbounded_message(self):
        sender = TwilioSmsSender(TwilioSmsConfiguration("a", "b", "c", "d"), opener=lambda *a, **k: None)
        with self.assertRaises(ValueError): sender("")
        with self.assertRaises(ValueError): sender("x" * 481)


if __name__ == "__main__": unittest.main()
