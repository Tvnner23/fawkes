from src.memory.import_policy import classify_import_candidate


def audit_import_candidate(
    candidate,
    *,
    assessment,
):
    """
    Convert a semantic memory assessment into a human-reviewable import audit.

    Nothing is persisted here. This is the decision/audit stage only.
    """
    memory_type = assessment.memory_type or "unclassified"

    return classify_import_candidate(
        candidate_id=candidate["candidate_id"],
        content=candidate["content"],
        memory_type=memory_type,
        confidence=assessment.confidence,
        importance=assessment.importance,
        reasoning=assessment.reasoning or "",
        source_message_ids=candidate.get(
            "source_message_ids",
            (),
        ),
        source_archive_ids=candidate.get(
            "source_archive_ids",
            (),
        ),
    )
