import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parent.parent.parent
DEV_REVIEW_DIR = ROOT / "memory" / "development" / "review"


@dataclass(frozen=True)
class DeveloperReviewItem:
    """
    Centralized developer-review record.

    This is a reference/copy of something that already exists in its
    original system location. It exists so developers have one obvious
    place to inspect things Fawkes believes need attention.
    """
    review_id: str
    candidate_id: str
    reason: str
    source: str
    original_reference: str
    content: str
    memory_type: str
    tier: str
    confidence: float
    importance: float
    created_at: str
    instance_id: str | None = None


def create_developer_review_item(
    *,
    candidate_id,
    reason,
    source,
    original_reference,
    content,
    memory_type,
    tier,
    confidence,
    importance,
    instance_id=None,
):
    if not candidate_id:
        raise ValueError("candidate_id cannot be empty")

    if not reason.strip():
        raise ValueError("reason cannot be empty")

    if not source.strip():
        raise ValueError("source cannot be empty")

    if not original_reference.strip():
        raise ValueError("original_reference cannot be empty")

    if not content.strip():
        raise ValueError("content cannot be empty")

    return DeveloperReviewItem(
        review_id=str(uuid4()),
        candidate_id=candidate_id,
        reason=reason.strip(),
        source=source.strip(),
        original_reference=original_reference.strip(),
        content=content.strip(),
        memory_type=memory_type,
        tier=tier,
        confidence=float(confidence),
        importance=float(importance),
        created_at=datetime.now(timezone.utc).isoformat(),
        instance_id=instance_id,
    )


def save_developer_review_item(item):
    DEV_REVIEW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = DEV_REVIEW_DIR / f"{item.review_id}.json"

    path.write_text(
        json.dumps(
            {
                "review_id": item.review_id,
                "instance_id": item.instance_id,
                "candidate_id": item.candidate_id,
                "reason": item.reason,
                "source": item.source,
                "original_reference": item.original_reference,
                "content": item.content,
                "memory_type": item.memory_type,
                "tier": item.tier,
                "confidence": item.confidence,
                "importance": item.importance,
                "created_at": item.created_at,
                "status": "needs_review",
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return path


def list_developer_review_items(
    *,
    status="needs_review",
):
    """
    Return developer-review items from the centralized review inbox.

    Items remain linked to their original source through
    original_reference.
    """
    if not DEV_REVIEW_DIR.exists():
        return []

    items = []

    for path in sorted(DEV_REVIEW_DIR.glob("*.json")):
        try:
            record = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue

        if status is not None and record.get("status") != status:
            continue

        items.append(record)

    return items


def apply_developer_review_decision(
    review_id,
    *,
    decision,
    reviewer="user",
    note="",
):
    """
    Apply an explicit human decision to a developer-review item.

    The original review record is preserved in-place as the source
    record, while the human disposition is appended as review metadata.
    """
    if decision not in {"accept", "reject"}:
        raise ValueError(
            f"Invalid developer review decision: {decision}"
        )

    if not DEV_REVIEW_DIR.exists():
        raise FileNotFoundError(
            f"Developer review directory does not exist: {DEV_REVIEW_DIR}"
        )

    path = DEV_REVIEW_DIR / f"{review_id}.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Developer review item not found: {review_id}"
        )

    record = json.loads(
        path.read_text(encoding="utf-8")
    )

    if record.get("status") != "needs_review":
        raise ValueError(
            "Developer review item has already been decided"
        )

    record["status"] = "reviewed"
    record["human_decision"] = decision
    record["reviewer"] = reviewer
    record["review_note"] = note.strip()
    record["reviewed_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    from src.memory.review_feedback import record_review_feedback

    record_review_feedback(
        record,
        human_decision=decision,
        reviewer=reviewer,
        note=note,
    )

    path.write_text(
        json.dumps(
            record,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return record
