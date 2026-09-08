"""Read-only Developer-tab projection over existing Development stores."""

from pathlib import Path
import json

from src.memory.dev_review import DEV_REVIEW_DIR
from src.memory.development_observations import (
    development_progression,
    list_development_observations,
)
from src.memory.development_store import DEVELOPMENT_DIR
from src.memory.review_feedback import FEEDBACK_DIR
from src.memory.ledger import list_work_items


def _proposal_review_projection(proposal):
    """Expose an existing proposal as review work without copying its data."""
    return {
        "review_id": f"proposal:{proposal['proposal_id']}",
        "candidate_id": proposal["proposal_id"],
        "instance_id": proposal.get("instance_id"),
        "reason": proposal.get("rationale") or "Fawkes proposed a durable development change.",
        "source": "development_proposal",
        "original_reference": proposal["proposal_id"],
        "content": proposal.get("proposed_change") or "",
        "category": proposal.get("category"),
        "confidence": proposal.get("confidence"),
        "created_at": proposal.get("created_at"),
        "status": "needs_review",
        "projection_only": True,
    }


def _records(directory, *, instance_id, include_legacy_unscoped=False):
    directory = Path(directory)
    if not directory.exists():
        return []
    records = []
    for path in directory.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        owner = record.get("instance_id")
        if owner != instance_id and not (include_legacy_unscoped and owner is None):
            continue
        records.append(record)
    return sorted(
        records,
        key=lambda item: item.get("updated_at", item.get("created_at", "")),
        reverse=True,
    )


def build_development_dashboard(*, instance_id, include_legacy_unscoped=False):
    """Build one inspectable view without mutating or duplicating source data."""
    observations = list_development_observations(instance_id=instance_id)
    proposals = _records(
        DEVELOPMENT_DIR,
        instance_id=instance_id,
        include_legacy_unscoped=include_legacy_unscoped,
    )
    review_items = _records(
        DEV_REVIEW_DIR,
        instance_id=instance_id,
        include_legacy_unscoped=include_legacy_unscoped,
    )
    feedback = _records(
        FEEDBACK_DIR,
        instance_id=instance_id,
        include_legacy_unscoped=include_legacy_unscoped,
    )
    memory_items = list_work_items(instance_id=instance_id)
    memory_status_counts = {}
    for item in memory_items:
        memory_status_counts[item["status"]] = memory_status_counts.get(item["status"], 0) + 1
    memory_review = sorted(
        (item for item in memory_items if item["status"] == "review"),
        key=lambda item: item.get("updated_at", ""), reverse=True,
    )
    # A persisted, still-proposed Development record is itself genuine human
    # review work. Project it directly instead of requiring a duplicate inbox
    # record that can become disconnected from its source.
    proposal_review = [
        _proposal_review_projection(item)
        for item in proposals if item.get("status") == "proposed"
    ]
    return {
        "observations": observations,
        "system_defects": [
            item for item in observations if item.get("category") == "system_defect"
        ],
        "base_phoenix_candidates": [
            item
            for item in observations
            if item.get("category") == "base_phoenix_candidate"
        ],
        "corrections": [
            item
            for item in observations
            if item.get("category") == "correction_signal"
        ],
        "development_proposals": proposals,
        "human_review_items": sorted(
            [*review_items, *proposal_review],
            key=lambda item: item.get("created_at") or "", reverse=True,
        ),
        "memory_triage": {
            "status_counts": memory_status_counts,
            "review_items": memory_review,
            "queued_count": memory_status_counts.get("queued", 0),
        },
        "review_feedback": feedback,
        "progression": development_progression(instance_id=instance_id),
        # Reserved read-model extension points. They do not imply stores,
        # taxonomies, scores, or active presentation control today.
        "presentation_development": [],
        "presentation_contract_version": 1,
        "growth_assessment": None,
        "growth_assessment_status": "deferred",
    }
