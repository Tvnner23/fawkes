#!/usr/bin/env python3
"""Emit sanitized durable events for the credential-free Windows attention agent."""

from pathlib import Path
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.runtime.component_supervision import ComponentReceiptStore
from src.runtime.development_attention import DevelopmentAttentionStore

ROOT = Path(os.environ.get("FAWKES_DEVELOPMENT_ROOT", "/home/tvnner/fawkes"))


def _id(kind, source_id):
    return "windows-attention-" + hashlib.sha256(f"{kind}:{source_id}".encode()).hexdigest()


def project(*, root=ROOT, attention_store=None, receipt_store=None):
    events = []
    attention_store = attention_store or DevelopmentAttentionStore()
    receipt_store = receipt_store or ComponentReceiptStore()
    for item in attention_store.list(pending_only=True):
        events.append({"event_id": _id("needs_tanner", item["attention_id"]),
            "kind": "needs_tanner", "created_at": item["created_at"],
            "campaign_id": item["campaign_id"], "title": "Fawkes needs Tanner",
            "safe_message": item["why_required"], "focus": True,
            "detail_url": item["detail_url"], "source_id": item["attention_id"]})
    campaign_root = Path(root) / "database" / "development_campaigns"
    if campaign_root.exists():
        for path in campaign_root.glob("*.json"):
            try:
                campaign = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for event in campaign.get("events", []):
                if event.get("kind") not in {"builder_return_retained", "independent_review_retained"}:
                    continue
                kind = "candidate_completed" if event["kind"] == "builder_return_retained" else "reviewer_completed"
                events.append({"event_id": _id(kind, event["event_id"]), "kind": kind,
                    "created_at": event["created_at"], "campaign_id": campaign["campaign_id"],
                    "title": "Worker candidate ready" if kind == "candidate_completed" else "Reviewer completed",
                    "safe_message": f"Campaign {campaign['campaign_id']} has durable evidence ready for inspection.",
                    "focus": True, "detail_url": f"http://localhost:8787/?view=developer&campaign={campaign['campaign_id']}",
                    "source_id": event["event_id"]})
    for receipt in receipt_store.latest(limit=200):
        terminal = receipt.get("receipt_type") == "failure" and receipt.get("service_state") in {"failed", "needs_tanner"}
        recovery = receipt.get("receipt_type") == "recovery"
        if not terminal and not recovery:
            continue
        source = f"{receipt['failure_id']}:{receipt['receipt_type']}"
        events.append({"event_id": _id("component_receipt", source),
            "kind": "component_recovered" if recovery else "component_failed",
            "created_at": receipt["timestamp_utc"], "campaign_id": None,
            "title": f"Fawkes {receipt['component']} recovered" if recovery else f"Fawkes {receipt['component']} needs attention",
            "safe_message": (f"failure_id={receipt['failure_id']} stage={receipt['stage']} "
                f"exit={receipt.get('process_exit_code')} provider={receipt.get('provider_code')} state={receipt['service_state']}"),
            "focus": not recovery, "detail_url": "http://localhost:8787/?view=developer&section=status",
            "source_id": source})
    return sorted(events, key=lambda item: (item["created_at"], item["event_id"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seen", action="append", default=[])
    args = parser.parse_args()
    seen = set(args.seen)
    print(json.dumps({"schema_version": 1,
        "events": [item for item in project() if item["event_id"] not in seen],
        "creates_authority": False}, separators=(",", ":")))


if __name__ == "__main__":
    main()
