from src.capture.canonical import canonical_messages
from src.memory.consolidate import consolidate_assessment
from src.memory.retrieval import retrieve_memories
from src.memory.semantic import evaluate_semantically
from src.memory.extract import extract_memory_candidates


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
            conversation_context=conversation_context,
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
        conversation_context=conversation_context,
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



def process_conversation(
    conversation_id: str,
    *,
    evaluator,
    matcher=None,
    retrieval_limit=5,
):
    """
    Process one canonical conversation through the memory pipeline.

    Canonical conversation history is the sole source of semantic context.
    The archive itself remains untouched.
    """
    conversation = tuple(canonical_messages(conversation_id))
    candidates = extract_memory_candidates(conversation_id)

    return process_candidates(
        candidates,
        evaluator=evaluator,
        matcher=matcher,
        conversation_context=conversation,
        retrieval_limit=retrieval_limit,
    )
