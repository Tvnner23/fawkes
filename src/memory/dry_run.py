from src.capture.canonical import message_allows_memory_learning
from src.memory.archive_context import build_archive_context, memory_learning_enabled
from src.memory.extract import extract_memory_candidates
from src.memory.gate import gate_memory_candidates
from src.memory.preflight import preflight_candidate


def dry_run_conversation(
    conversation_id: str,
    *,
    evaluator,
    context_before=40,
    context_after=40,
    max_request_chars=100_000,
    instance_id=None,
    include_unscoped=False,
):
    """
    Evaluate a real archived conversation without persisting any memories.

    Each candidate receives a bounded context window centered on its source
    message. Oversized requests are rejected before reaching the provider.

    The archive and persistent memory store are never modified.
    """
    candidates = (extract_memory_candidates(conversation_id, instance_id=instance_id,
                  include_unscoped=include_unscoped) if memory_learning_enabled(instance_id) else [])
    gated_candidates = gate_memory_candidates(candidates)

    results = []
    rejected = []

    for candidate in gated_candidates:
        if not memory_learning_enabled(instance_id):
            break
        if (not message_allows_memory_learning(candidate)
                or not memory_learning_enabled(candidate.get("instance_id"))):
            continue
        source_message_ids = candidate.get(
            "source_message_ids",
            (),
        )

        if not source_message_ids:
            rejected.append({
                "candidate": candidate,
                "reason": "candidate has no source message",
            })
            continue

        center_message_id = source_message_ids[0]

        context = build_archive_context(
            conversation_id,
            center_message_id=center_message_id,
            before=context_before,
            after=context_after,
            instance_id=instance_id,
            include_unscoped=include_unscoped,
            memory_learning_only=True,
        )

        try:
            request_chars = preflight_candidate(
                content=candidate["content"],
                conversation_context=context,
                max_request_chars=max_request_chars,
            )
        except ValueError as exc:
            rejected.append({
                "candidate": candidate,
                "reason": str(exc),
            })
            continue

        assessment = evaluator.evaluate(
            content=candidate["content"],
            conversation_context=context,
        )

        results.append({
            "candidate": candidate,
            "assessment": assessment,
            "context_message_count": len(context),
            "request_chars": request_chars,
        })

    return {
        "conversation_id": conversation_id,
        "raw_candidate_count": len(candidates),
        "gated_candidate_count": len(gated_candidates),
        "evaluated_count": len(results),
        "rejected_count": len(rejected),
        "results": results,
        "rejected": rejected,
    }
