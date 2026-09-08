from src.memory.development_cycle import run_development_cycle
from src.memory.development_store import save_development_proposal
from src.runtime.personal_recording import RecordingPolicyStore
from src.memory.archive_context import require_archive_source_learning, filter_memory_learning_context, ArchiveContextReviewRequired


def _require_correction_learning(instance_id, source_message_ids):
    _require_correction_policy(instance_id)
    require_archive_source_learning(instance_id=instance_id, source_message_ids=source_message_ids)
    _require_correction_policy(instance_id)


def _require_correction_policy(instance_id):
    if instance_id is not None:
        policy = RecordingPolicyStore(instance_id).latch()
        if not policy.memory_learning or not policy.personal_diagnostics:
            raise PermissionError("Correction-derived learning is disabled by recording policy")


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
    correction_context=(),
):
    """
    Turn an observed experience/correction into a persisted development
    proposal awaiting human approval.

    Fawkes may reason about and propose improvements, but this function
    never executes code changes automatically.
    """
    if not experience or not experience.strip():
        raise ValueError("experience cannot be empty")
    source_message_ids = tuple(source_message_ids)
    if origin == "user_correction":
        correction_context = tuple(correction_context)
        if filter_memory_learning_context(correction_context, instance_id=instance_id) != tuple(correction_context):
            raise ArchiveContextReviewRequired("Correction context eligibility changed before evaluation")
        _require_correction_learning(instance_id, source_message_ids)

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

    # The evaluator may have outlived the initiating setting. This conditional
    # guard is specific to correction-derived learning, not separately
    # authorized Development evidence with another origin.
    if origin == "user_correction":
        if filter_memory_learning_context(correction_context, instance_id=instance_id) != tuple(correction_context):
            raise ArchiveContextReviewRequired("Correction context eligibility changed before publication")
        _require_correction_learning(instance_id, source_message_ids)
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

    source_message_ids = tuple(source_message_ids)
    _require_correction_learning(instance_id, source_message_ids)
    conversation_context = filter_memory_learning_context(conversation_context, instance_id=instance_id)
    _require_correction_learning(instance_id, source_message_ids)

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
        correction_context=conversation_context,
    )

    return result
