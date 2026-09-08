"""Read-only objective closeout notices; never an acceptance or authority owner.

Ordinary campaign success is insufficient. An explicit whole-objective closeout
must be retained through the existing campaign owner after all actual gates.
The evidence references describe the recorded closeout, not new verification.
"""
import hashlib
import json
import re


def blocked_objective_identity(record):
    """Identify the actual retained blocker, never its shortened display text."""
    needs = record.get("needs_tanner")
    if not isinstance(needs, dict) or not needs:
        return None
    attention = needs.get("attention_id")
    events = record.get("events") or []
    event = events[-1].get("event_id") if events and isinstance(events[-1], dict) else None
    identity = attention if isinstance(attention, str) and attention else event
    if not isinstance(identity, str) or not identity:
        return None
    return hashlib.sha256(json.dumps([record.get("campaign_id"), identity, needs],
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def completed_objective(record):
    """Return a bounded recorded closeout, or None; never repair missing facts."""
    if (record.get("status") != "succeeded" or record.get("needs_tanner")
            or record.get("parent_campaign_id")
            or any(r.get("reference_type") == "parent_campaign"
                   for r in record.get("recovery_references", []))):
        return None
    events = record.get("events") or []
    if not events or events[-1].get("kind") != "console_objective_closed":
        return None
    event = events[-1]
    detail = event.get("detail")
    if not isinstance(detail, dict):
        return None
    expected = record.get("acceptance_condition_ids")
    gates = detail.get("gates")
    objective = record.get("objective")
    if (not isinstance(objective, str) or not isinstance(expected, list) or not expected
            or any(not isinstance(c,str) for c in expected)
            or len(set(expected)) != len(expected)
            or set(record.get("acceptance_satisfied") or []) != set(expected)
            or detail.get("scope") != "whole_user_objective"
            or detail.get("campaign_id") != record.get("campaign_id")
            or detail.get("objective_sha256") != hashlib.sha256(objective.encode()).hexdigest()
            or detail.get("remaining_authorized_work") is not False
            or not isinstance(gates, list) or len(gates) != len(expected)):
        return None
    covered = []
    for gate in gates:
        if (not isinstance(gate, dict) or gate.get("status") != "satisfied"
                or gate.get("condition_id") not in expected
                or not isinstance(gate.get("reference_id"), str)
                or not 1 <= len(gate["reference_id"]) <= 180
                or not re.fullmatch(r"[a-f0-9]{64}", str(gate.get("sha256", "")))):
            return None
        covered.append(gate["condition_id"])
    if set(covered) != set(expected) or len(set(covered)) != len(covered):
        return None
    result = detail.get("result")
    if (not isinstance(result, str) or not result.strip()
            or len(json.dumps(result,ensure_ascii=False).encode())-2 > 1200):
        return None
    from src.runtime.autonomy_supervision import console_timestamp
    if not console_timestamp(event.get("created_at")):
        return None
    return {"event_id": event["event_id"], "recorded_at": event["created_at"],
            "result": result, "scope": "whole_user_objective",
            "gate_count": len(gates), "creates_authority": False}
