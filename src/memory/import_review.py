from collections import Counter

from src.memory.import_pipeline import audit_import_candidate


def build_import_review(candidates, assessments):
    """
    Build an in-memory audit report from candidates and semantic assessments.

    Nothing is persisted.
    """
    if len(candidates) != len(assessments):
        raise ValueError(
            "candidates and assessments must have the same length"
        )

    audits = [
        audit_import_candidate(
            candidate,
            assessment=assessment,
        )
        for candidate, assessment in zip(
            candidates,
            assessments,
        )
    ]

    tier_counts = Counter(
        audit.tier
        for audit in audits
    )

    decision_counts = Counter(
        audit.decision
        for audit in audits
    )

    review_queue = [
        audit
        for audit in audits
        if audit.decision == "review"
    ]

    accepted = [
        audit
        for audit in audits
        if audit.decision == "accept"
    ]

    rejected = [
        audit
        for audit in audits
        if audit.decision == "reject"
    ]

    return {
        "audits": audits,
        "tier_counts": dict(tier_counts),
        "decision_counts": dict(decision_counts),
        "accepted": accepted,
        "review_queue": review_queue,
        "rejected": rejected,
    }
