from src.memory.consolidate import consolidate_assessment
from src.memory.retrieval import retrieve_memories
from src.memory.semantic import evaluate_semantically


def process_memory_candidate(
    candidate: dict,
    *,
    evaluator,
    matcher=None,
    conversation_context=(),
    retrieval_limit=5,
):
    """
    Process one extracted candidate through the memory pipeline.

    Flow:
        candidate
          -> semantic evaluation
          -> relevant existing-memory retrieval
          -> semantic comparison
          -> consolidation

    The archive remains untouched throughout this process.
    """
    assessment = evaluate_semantically(
        evaluator,
        content=candidate["content"],
        conversation_context=conversation_context,
    )

    if not assessment.should_remember:
        return consolidate_assessment(
            assessment,
            source_message_ids=candidate.get("source_message_ids", ()),
            source_archive_ids=candidate.get("source_archive_ids", ()),
        )

    existing_memories = retrieve_memories(
        assessment.meaning or candidate["content"],
        limit=retrieval_limit,
    )

    return consolidate_assessment(
        assessment,
        source_message_ids=candidate.get("source_message_ids", ()),
        source_archive_ids=candidate.get("source_archive_ids", ()),
        matcher=matcher,
        existing_memories=existing_memories,
    )


def process_candidates(
    candidates,
    *,
    evaluator,
    matcher=None,
    conversation_context=(),
    retrieval_limit=5,
):
    """
    Process extracted candidates without modifying the source archive.
    """
    results = []

    for candidate in candidates:
        results.append(
            process_memory_candidate(
                candidate,
                evaluator=evaluator,
                matcher=matcher,
                conversation_context=conversation_context,
                retrieval_limit=retrieval_limit,
            )
        )

    return results
