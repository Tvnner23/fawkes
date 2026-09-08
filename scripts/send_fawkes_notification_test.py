#!/usr/bin/env python3
"""Send one harmless, explicitly invoked Fawkes/Twilio acceptance message."""

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.autonomy_supervision import RiderNotificationStore
from src.runtime.twilio_sms import TwilioSmsConfiguration, TwilioSmsSender


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--needs-tanner-test", action="store_true")
    arguments = parser.parse_args()
    configuration = TwilioSmsConfiguration.from_environment()
    sender = TwilioSmsSender(configuration)
    store = RiderNotificationStore("diagnostic", root=ROOT / "database" / "rider_notifications")
    if arguments.needs_tanner_test:
        kind, key = "needs_tanner_test", "explicit-diagnostic-v1"
        message = ("Fawkes NEEDS_TANNER notification test. The diagnostic branch remains paused. "
                   "No approval was created and no action is required.")
    else:
        kind, key = "phone_delivery_test", "explicit-diagnostic-v1"
        message = "Fawkes notification test. Phone delivery is working. No action is required."
    logical, _ = store.create_once(kind=kind, campaign_id="notification-diagnostic",
        state_key=key, message=message,
        evidence_refs=[{"reference_type": "explicit_rider_diagnostic",
                        "reference_id": "notification-diagnostic"}])
    delivered = store.deliver(logical, sender)
    attempt = delivered["attempts"][-1]
    print(f"status={attempt['status']}")
    if attempt["status"] == "delivered":
        print(f"provider={attempt['provider_receipt']['provider']}")
        print(f"message_sid={attempt['provider_receipt']['message_sid']}")
        return 0
    print(f"failure_code={attempt.get('failure_code', 'delivery_failed')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
