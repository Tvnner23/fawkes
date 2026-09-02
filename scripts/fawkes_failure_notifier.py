#!/usr/bin/env python3
"""Deliver queued sanitized component receipts through an independent webhook."""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.component_supervision import ComponentReceiptStore
from src.runtime.discord_webhook import DiscordWebhookConfiguration, DiscordWebhookSender


def main():
    store = ComponentReceiptStore()
    if not store.pending_root.exists():
        return
    sender = DiscordWebhookSender(DiscordWebhookConfiguration.from_environment())
    for path in sorted(store.pending_root.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        receipt = value["receipt"]
        message = (f"Fawkes {receipt['component']} {receipt['receipt_type']}: "
                   f"{receipt['category']} (code {receipt.get('provider_code') or receipt.get('process_exit_code') or 'none'}). "
                   "Inspect local Fawkes component receipts.")
        try:
            sender(message)
        except Exception as exc:
            value["attempts"].append({"status": "failed", "failure_code": type(exc).__name__})
            path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            continue
        path.unlink()


if __name__ == "__main__":
    main()
