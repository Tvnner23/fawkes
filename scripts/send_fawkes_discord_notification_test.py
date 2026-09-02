#!/usr/bin/env python3
"""Send one harmless, explicitly invoked Discord notification diagnostic."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.autonomy_supervision import RiderNotificationStore
from src.runtime.discord_webhook import DiscordWebhookConfiguration, DiscordWebhookSender


def main():
    sender = DiscordWebhookSender(DiscordWebhookConfiguration.from_environment())
    store = RiderNotificationStore("diagnostic", root=ROOT / "database" / "rider_notifications")
    logical, _ = store.create_once(
        kind="discord_delivery_test",
        campaign_id="notification-diagnostic",
        state_key="explicit-discord-diagnostic-v1",
        message="Fawkes notification test. Discord delivery is working. No action is required.",
        evidence_refs=[{"reference_type": "diagnostic", "reference_id": "notification-diagnostic"}],
    )
    delivered = store.deliver(logical, sender)
    attempt = delivered["attempts"][-1]
    print(f"notification_id={delivered['notification_id']}")
    print(f"attempt_id={attempt['attempt_id']}")
    print(f"status={attempt['status']}")
    return 0 if attempt["status"] == "delivered" else 1


if __name__ == "__main__":
    raise SystemExit(main())
