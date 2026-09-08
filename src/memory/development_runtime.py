from src.memory.development_cycle import run_development_cycle
from src.memory.development_store import save_development_proposal


def process_development_experience(
    experience: str,
    *,
    evaluator,
    similarity,
    source_memory_ids=(),
    source_message_ids=(),
    candidate_limit=20,
    result_limit=5,
    instance_id=None,
    origin="development_experience",
):
    """
    Turn an observed experience/correction into a persisted development
    proposal awaiting human approval.

    Fawkes may reason about and propose improvements, but this function
    never executes code changes automatically.
    """
    if not experience or not experience.strip():
        raise ValueError("experience cannot be empty")

    result = run_development_cycle(
        experience.strip(),
        evaluator=evaluator,
        similarity=similarity,
        source_memory_ids=source_memory_ids,
        source_message_ids=source_message_ids,
        candidate_limit=candidate_limit,
        result_limit=result_limit,
        instance_id=instance_id,
    )

    proposal = result["proposal"]

    if proposal is None:
        return {
            **result,
            "record": None,
        }

    if instance_id is None and origin == "development_experience":
        record = save_development_proposal(proposal)
    else:
        record = save_development_proposal(
            proposal,
            instance_id=instance_id,
            origin=origin,
        )

    return {
        **result,
        "record": record,
    }


def process_user_correction(
    correction: str,
    *,
    evaluator,
    similarity,
    conversation_context=(),
    source_memory_ids=(),
    source_message_ids=(),
    candidate_limit=20,
    result_limit=5,
    instance_id=None,
):
    """
    Process an explicit user correction as a developmental experience.

    The correction and surrounding conversation context are supplied to
    the developmental evaluator. Any resulting proposal is persisted for
    human review. No code is modified automatically.
    """
    if not correction or not correction.strip():
        raise ValueError("correction cannot be empty")

    experience = correction.strip()

    if conversation_context:
        context_text = "\n".join(
            f"{message.get('role', 'unknown')}: "
            f"{message.get('content', '')}"
            for message in conversation_context
        )

        experience = (
            f"User correction:\n{experience}\n\n"
            f"Conversation context:\n{context_text}"
        )

    result = process_development_experience(
        experience,
        evaluator=evaluator,
        similarity=similarity,
        source_memory_ids=source_memory_ids,
        source_message_ids=source_message_ids,
        candidate_limit=candidate_limit,
        result_limit=result_limit,
        instance_id=instance_id,
        origin="user_correction",
    )

    return result
