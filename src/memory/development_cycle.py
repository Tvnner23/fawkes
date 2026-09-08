from src.memory.development_history import retrieve_relevant_development


def run_development_cycle(
    experience: str,
    *,
    evaluator,
    similarity,
    source_memory_ids=(),
    source_message_ids=(),
    candidate_limit=20,
    result_limit=5,
    instance_id=None,
):
    """
    Run one complete developmental reasoning cycle.

    Prior development history is retrieved first and supplied to the
    developmental evaluator. Nothing is persisted automatically.
    """
    prior_development = retrieve_relevant_development(
        experience,
        similarity=similarity,
        candidate_limit=candidate_limit,
        result_limit=result_limit,
        instance_id=instance_id,
    )

    proposal = evaluator.evaluate(
        experience=experience,
        prior_development=prior_development,
        source_memory_ids=source_memory_ids,
        source_message_ids=source_message_ids,
    )

    return {
        "experience": experience,
        "prior_development": prior_development,
        "proposal": proposal,
    }
