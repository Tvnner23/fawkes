from src.memory.import_pipeline import audit_import_candidate


def audit_candidate_batch(
    candidates,
    *,
    evaluator,
    limit=10,
):
    """
    Audit a bounded batch of real candidates.

    Semantic evaluation may use a provider, but this function never
    persists memories or import decisions.
    """
    if limit <= 0:
        raise ValueError("limit must be greater than zero")

    selected = list(candidates)[:limit]
    audits = []

    for candidate in selected:
        assessment = evaluator.evaluate(
            content=candidate["content"],
            conversation_context=candidate.get(
                "conversation_context",
                (),
            ),
        )

        if assessment is None:
            continue

        audits.append(
            audit_import_candidate(
                candidate,
                assessment=assessment,
            )
        )

    return audits
