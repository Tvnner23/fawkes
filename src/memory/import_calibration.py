import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
FEEDBACK_DIR = ROOT / "memory" / "development" / "feedback"


def build_import_calibration_report(
    *,
    feedback_dir=FEEDBACK_DIR,
):
    """
    Analyze human corrections to historical import decisions.

    This is deliberately provider-independent and makes no API calls.
    It measures how Fawkes's confidence and tiering correlate with
    human review outcomes.
    """
    feedback_dir = Path(feedback_dir)

    if not feedback_dir.exists():
        return {
            "total_reviewed": 0,
            "accepted": 0,
            "rejected": 0,
            "acceptance_rate": 0.0,
            "average_confidence": 0.0,
            "accepted_average_confidence": 0.0,
            "rejected_average_confidence": 0.0,
            "tier_counts": {},
            "tier_outcomes": {},
            "memory_type_outcomes": {},
        }

    records = []

    for path in sorted(feedback_dir.glob("*.json")):
        try:
            record = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue

        if record.get("human_decision") not in {
            "accept",
            "reject",
        }:
            continue

        records.append(record)

    total = len(records)

    if not total:
        return {
            "total_reviewed": 0,
            "accepted": 0,
            "rejected": 0,
            "acceptance_rate": 0.0,
            "average_confidence": 0.0,
            "accepted_average_confidence": 0.0,
            "rejected_average_confidence": 0.0,
            "tier_counts": {},
            "tier_outcomes": {},
            "memory_type_outcomes": {},
        }

    accepted = [
        record
        for record in records
        if record["human_decision"] == "accept"
    ]

    rejected = [
        record
        for record in records
        if record["human_decision"] == "reject"
    ]

    confidences = [
        float(record.get("fawkes_confidence", 0.0))
        for record in records
    ]

    accepted_confidences = [
        float(record.get("fawkes_confidence", 0.0))
        for record in accepted
    ]

    rejected_confidences = [
        float(record.get("fawkes_confidence", 0.0))
        for record in rejected
    ]

    tier_counts = Counter(
        record.get("fawkes_tier")
        for record in records
    )

    tier_outcomes = {}

    for tier in sorted(
        {
            record.get("fawkes_tier")
            for record in records
        }
    ):
        tier_records = [
            record
            for record in records
            if record.get("fawkes_tier") == tier
        ]

        tier_outcomes[tier] = {
            "reviewed": len(tier_records),
            "accepted": sum(
                record["human_decision"] == "accept"
                for record in tier_records
            ),
            "rejected": sum(
                record["human_decision"] == "reject"
                for record in tier_records
            ),
        }

    memory_type_outcomes = {}

    for memory_type in sorted(
        {
            record.get("memory_type")
            for record in records
        }
    ):
        type_records = [
            record
            for record in records
            if record.get("memory_type") == memory_type
        ]

        memory_type_outcomes[memory_type] = {
            "reviewed": len(type_records),
            "accepted": sum(
                record["human_decision"] == "accept"
                for record in type_records
            ),
            "rejected": sum(
                record["human_decision"] == "reject"
                for record in type_records
            ),
        }

    return {
        "total_reviewed": total,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "acceptance_rate": len(accepted) / total,
        "average_confidence": sum(confidences) / total,
        "accepted_average_confidence": (
            sum(accepted_confidences) / len(accepted)
            if accepted
            else 0.0
        ),
        "rejected_average_confidence": (
            sum(rejected_confidences) / len(rejected)
            if rejected
            else 0.0
        ),
        "tier_counts": dict(tier_counts),
        "tier_outcomes": tier_outcomes,
        "memory_type_outcomes": memory_type_outcomes,
    }
