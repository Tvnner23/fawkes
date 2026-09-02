#!/usr/bin/env python3
"""Run one bounded read-only production Worker Exchange handoff to Codex."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.codex_worker_adapter import ADAPTER_ID, PROMOTION_RECORD, CodexExecWorkerAdapter
from src.runtime.worker_exchange import WorkerExchange


INSTANCE = "fawkes"
TASK_SCOPE = "codex-adapter-production-pilot-v1"
SENDER = {"worker_id": "fawkes-runtime", "role": "coordination",
          "identity_status": "verified", "charter_version": "1.0"}
RECIPIENT = {"worker_id": "codex-repository-production-pilot", "role": "software_repository",
             "identity_status": "rider_attested", "charter_version": "1.0"}


def authority(sender, expires_at, recipient=None, **extra):
    value = {"decision": "authorized", "instance_id": INSTANCE, "task_scope_id": TASK_SCOPE,
             "sender_worker_id": sender,
             "authorization_reference": "tanner-codex-production-pilot-2026-09-01",
             "expires_at": expires_at}
    if recipient:
        value["recipient_worker_id"] = recipient
    value.update(extra)
    return value


def main():
    task = (
        "Perform a read-only operational review of the promoted Codex adapter using the exact Worker Exchange "
        "source section. Inspect docs/phoenix/CODEX_WORKER_ADAPTER.md and the adapter capability definition. "
        "Report whether production promotion, manual fallback, and zero-authority boundaries agree, identify "
        "one concrete operational strength and any real friction for a future reviewer, and do not edit files."
    )
    expires = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
    exchange = WorkerExchange(INSTANCE)
    report = exchange.create_report(task_scope_id=TASK_SCOPE, sender=SENDER,
        authority=authority("fawkes-runtime", expires), sections=[{
            "section_id": "pilot-review-target", "title": "Production pilot review target",
            "content": (
                "Tanner promoted phoenix.worker_exchange.adapter.codex_cli_exec v0.1 after independent "
                "campaign v12 passed. Verify repository/runtime consistency. Manual fallback remains required; "
                "delivery is not verification, and neither state grants worker or promotion authority."
            )}], claims=[{"claim_id": "pilot-promotion-claim", "area": "worker_exchange",
                "statement": "The bounded Codex CLI adapter is promoted for controlled production use.",
                "maturity": "live", "change_class": "software_system"}],
        evidence_references=[{"campaign_version": "codex-cli-independent-assurance-v12",
            "candidate_snapshot_id": PROMOTION_RECORD["candidate_snapshot_id"],
            "fixed_campaign_sha256": PROMOTION_RECORD["fixed_campaign_sha256"]}],
        contract_references=[{"contract_id": "phoenix.worker_exchange.adapter.codex_cli_exec",
                              "version": "0.1"}])
    package = exchange.compose_package(report_id=report["report_id"], recipient=RECIPIENT,
        authority=authority("fawkes-runtime", expires, RECIPIENT["worker_id"]),
        included_section_ids=["pilot-review-target"])
    environment_id = f"codex-cli:{ROOT}"
    transport = authority("fawkes-runtime", expires, RECIPIENT["worker_id"],
        adapter_id=ADAPTER_ID, package_id=package["package_id"],
        recipient_environment_id=environment_id,
        read_only_task_sha256=hashlib.sha256(task.encode()).hexdigest(),
        adapter_promotion_reference=PROMOTION_RECORD["promotion_id"])
    result = CodexExecWorkerAdapter(exchange, workspace=ROOT).deliver_production_once(
        package_id=package["package_id"], transport_authority=transport,
        return_authority=authority(RECIPIENT["worker_id"], expires),
        recipient_environment_id=environment_id, read_only_task=task)
    returned = exchange._load("reports", result["return_report_id"]) if result.get("return_report_id") else None
    print(json.dumps({"result": result, "return_report": returned}, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "delivered" and result.get("adapter_promoted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
