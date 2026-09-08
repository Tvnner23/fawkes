from src.capture.canonical import canonical_messages
from src.memory.consolidate import consolidate_assessment
from src.memory.retrieval import retrieve_memories
from src.memory.semantic import evaluate_semantically
from src.memory.extract import extract_memory_candidates
from src.memory.store import MemoryOwnershipReview, list_memories_for_context


def process_memory_candidate(
    candidate: dict,
    *,
    evaluator,
    matcher=None,
    semantic_retriever=None,
    conversation_context=(),
    retrieval_limit=5,
    instance_id=None,
    include_unscoped=False,
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
    # Retained ownership must survive extraction and be checked before any
    # provider sees the content. A legacy/default call is not an all-owner grant.
    # Low-level callers without an owner field retain their explicit call scope.
    if "instance_id" in candidate and candidate["instance_id"] != instance_id:
        raise MemoryOwnershipReview("Candidate ownership does not match the processing instance; explicit ownership review required")
    conversation_context = tuple(conversation_context)
    if any("instance_id" in message and message["instance_id"] != instance_id
           and not (include_unscoped and message["instance_id"] is None)
           for message in conversation_context):
        raise MemoryOwnershipReview("Conversation context contains a foreign instance")
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
            instance_id=instance_id,
        )

    if semantic_retriever is not None:
        all_active_memories = list_memories_for_context(
            status="active",
            instance_id=instance_id,
            include_unscoped=include_unscoped,
        )

        existing_memories = semantic_retriever.rank(
            query=assessment.meaning or candidate["content"],
            memories=all_active_memories,
            limit=retrieval_limit,
        )
    else:
        existing_memories = retrieve_memories(
            assessment.meaning or candidate["content"],
            limit=retrieval_limit,
            instance_id=instance_id,
            include_unscoped=include_unscoped,
        )

    return consolidate_assessment(
        assessment,
        source_message_ids=candidate.get("source_message_ids", ()),
        source_archive_ids=candidate.get("source_archive_ids", ()),
        matcher=matcher,
        existing_memories=existing_memories,
        conversation_context=conversation_context,
        instance_id=instance_id,
    )


def process_candidates(
    candidates,
    *,
    evaluator,
    matcher=None,
    semantic_retriever=None,
    conversation_context=(),
    retrieval_limit=5,
    instance_id=None,
    include_unscoped=False,
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
                semantic_retriever=semantic_retriever,
                conversation_context=conversation_context,
                retrieval_limit=retrieval_limit,
                instance_id=instance_id,
                include_unscoped=include_unscoped,
            )
        )

    return results



def process_conversation(
    conversation_id: str,
    *,
    evaluator,
    matcher=None,
    semantic_retriever=None,
    retrieval_limit=5,
    instance_id=None,
    include_unscoped=False,
):
    """
    Process one canonical conversation through the memory pipeline.

    Canonical conversation history is the sole source of semantic context.
    The archive itself remains untouched.
    """
    conversation = tuple(canonical_messages(conversation_id,instance_id=instance_id,include_unscoped=include_unscoped))
    candidates = extract_memory_candidates(conversation_id,instance_id=instance_id,include_unscoped=include_unscoped)

    return process_candidates(
        candidates,
        evaluator=evaluator,
        matcher=matcher,
        semantic_retriever=semantic_retriever,
        conversation_context=conversation,
        retrieval_limit=retrieval_limit,
        instance_id=instance_id,
        include_unscoped=include_unscoped,
    )
