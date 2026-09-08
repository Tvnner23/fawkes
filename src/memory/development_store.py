import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.memory.development import DevelopmentProposal


ROOT = Path(__file__).resolve().parent.parent.parent
DEVELOPMENT_DIR = ROOT / "memory" / "development"
DEFAULT_DEVELOPMENT_DIR = DEVELOPMENT_DIR


def save_development_proposal(proposal: DevelopmentProposal, *, instance_id=None, origin=None,
                              legacy_unscoped=False):
    if not isinstance(instance_id, str) or not instance_id.strip():
        if not legacy_unscoped and DEVELOPMENT_DIR == DEFAULT_DEVELOPMENT_DIR:
            raise ValueError("instance_id is required for new Development proposals")
        instance_id = None
    DEVELOPMENT_DIR.mkdir(parents=True, exist_ok=True)

    proposal_id = str(uuid4())

    record = {
        "proposal_id": proposal_id,
        "instance_id": instance_id,
        "origin": origin or "development_experience",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "category": proposal.category,
        "observation": proposal.observation,
        "proposed_change": proposal.proposed_change,
        "rationale": proposal.rationale,
        "confidence": proposal.confidence,
        "source_memory_ids": list(proposal.source_memory_ids),
        "source_message_ids": list(proposal.source_message_ids),
        "status": "proposed",
    }

    path = DEVELOPMENT_DIR / f"{proposal_id}.json"

    path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return record


def review_development_proposal(proposal_id, *, instance_id, decision, reviewer="rider", note=""):
    """Record a human disposition without applying the proposed change."""
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")
    path = DEVELOPMENT_DIR / f"{proposal_id}.json"
    if not path.exists():
        raise ValueError("development proposal not found")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("instance_id") not in {instance_id, None}:
        raise ValueError("development proposal belongs to another Phoenix")
    if record.get("status") != "proposed":
        raise ValueError("development proposal has already been reviewed")
    reviewed_at = datetime.now(timezone.utc).isoformat()
    record["status"] = "approved_for_future_action" if decision == "approve" else "rejected"
    record["review"] = {
        "decision": decision, "reviewer": reviewer, "note": note.strip(),
        "reviewed_at": reviewed_at,
        "effect": "recorded_only_no_automatic_personality_or_code_change",
    }
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return record
