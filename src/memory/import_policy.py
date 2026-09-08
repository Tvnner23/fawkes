from src.memory.import_audit import create_import_audit


def classify_import_candidate(
    *,
    candidate_id,
    content,
    memory_type,
    confidence,
    importance,
    reasoning,
    source_message_ids=(),
    source_archive_ids=(),
):
    """
    Convert semantic confidence/importance into an import-review tier.

    The policy is intentionally deterministic so historical imports remain
    auditable and reproducible.
    """
    confidence = float(confidence)
    importance = float(importance)

    if memory_type == "artifact":
        tier = "X"
        decision = "reject"

    elif confidence >= 0.90 and importance >= 0.90:
        tier = "S"
        decision = "accept"

    elif confidence >= 0.85 and importance >= 0.70:
        tier = "A"
        decision = "accept"

    elif confidence >= 0.70 and importance >= 0.50:
        tier = "B"
        decision = "accept"

    elif confidence >= 0.55 and importance >= 0.35:
        tier = "C"
        decision = "review"

    else:
        tier = "D"
        decision = "reject"

    return create_import_audit(
        candidate_id=candidate_id,
        content=content,
        memory_type=memory_type,
        tier=tier,
        decision=decision,
        confidence=confidence,
        importance=importance,
        reasoning=reasoning,
        source_message_ids=source_message_ids,
        source_archive_ids=source_archive_ids,
    )
