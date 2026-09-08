from src.memory.development_retrieval import (
    retrieve_development_proposals,
)


def retrieve_relevant_development(
    experience: str,
    *,
    similarity,
    candidate_limit=20,
    result_limit=5,
    instance_id=None,
):
    """
    Retrieve and semantically rank Fawkes's prior development history.

    Deterministic retrieval narrows the search space first. Semantic
    similarity then identifies conceptually related prior experiences.
    """
    candidates = retrieve_development_proposals(
        experience,
        limit=candidate_limit,
        instance_id=instance_id,
    )

    if not candidates:
        return []

    return similarity.rank(
        experience=experience,
        proposals=candidates,
        limit=result_limit,
    )
