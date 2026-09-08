from dataclasses import dataclass

from src.capture.canonical import message_allows_memory_learning
from src.memory.archive_context import (
    ArchiveContextReviewRequired, require_memory_learning, require_archive_source_learning,
    filter_memory_learning_context,
)
from src.memory.semantic import SemanticMemoryAssessment
from src.memory.store import (
    create_memory,
    MemoryOwnershipReview,
    list_memories_for_context,
    memory_fingerprint,
    mark_memory_superseded,
    merge_duplicate_memories,
    revise_memory,
    strengthen_memory,
    supersede_memory,
)


@dataclass(frozen=True)
class ConsolidationResult:
    action: str
    memory_id: str | None
    assessment: SemanticMemoryAssessment


def consolidate_assessment(
    assessment: SemanticMemoryAssessment,
    *,
    source_message_ids=(),
    source_archive_ids=(),
    matcher=None,
    existing_memories=(),
    conversation_context=(),
    instance_id=None,
    source_work_item_ids=(),
    include_unscoped=False,
):
    """
    Convert a semantic assessment into persistent Phoenix memory state.

    This layer decides what to do with interpreted meaning.
    It does not care which model/provider produced the assessment.

    Existing-memory comparison, revision, strengthening, merging,
    contradiction handling, and supersession are intentionally separate
    concerns that will be added here without changing the semantic contract.
    """
    if not assessment.should_remember:
        return ConsolidationResult(
            action="ignored",
            memory_id=None,
            assessment=assessment,
        )

    if not assessment.memory_type:
        return ConsolidationResult(
            action="needs_review",
            memory_id=None,
            assessment=assessment,
        )

    if not assessment.meaning:
        return ConsolidationResult(
            action="needs_review",
            memory_id=None,
            assessment=assessment,
        )

    source_message_ids, source_archive_ids = tuple(source_message_ids), tuple(source_archive_ids)
    def require_learning_sources():
        require_memory_learning(instance_id)
        require_archive_source_learning(instance_id=instance_id, source_message_ids=source_message_ids,
                                        source_archive_ids=source_archive_ids)
        if filter_memory_learning_context(conversation_context, instance_id=instance_id,
                                          include_unscoped=include_unscoped) != conversation_context:
            raise ArchiveContextReviewRequired("Learning context eligibility changed before mutation")
        require_memory_learning(instance_id)
    require_memory_learning(instance_id)
    conversation_context = tuple(conversation_context)
    if any(not message_allows_memory_learning(message)
           and (message.get("message_id") in source_message_ids
                or message.get("source_archive_id") in source_archive_ids)
           for message in conversation_context):
        raise ArchiveContextReviewRequired("Memory evidence does not allow learning")
    conversation_context = filter_memory_learning_context(conversation_context, instance_id=instance_id,
                                                          include_unscoped=include_unscoped)
    require_learning_sources()

    # When an evaluator identifies its evidence, persistence must receive the
    # complete attribution. This prevents a multi-message conclusion from
    # silently losing supporting provenance at the mutation boundary.
    if assessment.supporting_message_ids and not set(
        assessment.supporting_message_ids
    ).issubset(set(source_message_ids)):
        return ConsolidationResult(
            action="needs_review",
            memory_id=None,
            assessment=assessment,
        )
    if assessment.supporting_archive_ids and not set(
        assessment.supporting_archive_ids
    ).issubset(set(source_archive_ids)):
        return ConsolidationResult(
            action="needs_review",
            memory_id=None,
            assessment=assessment,
        )

    # If a semantic matcher is available, let it determine the
    # relationship before applying deterministic duplicate handling.
    #
    # This preserves the richer consolidation semantics:
    # supports, revises, supersedes, and contradicts.
    if matcher is not None and not existing_memories:
        existing_memories = list_memories_for_context(
            status="active",
            instance_id=instance_id,
        )

    if any(existing.get('instance_id') != instance_id for existing in existing_memories):
        raise MemoryOwnershipReview('Existing Memory comparison requires a matching explicit instance; legacy unscoped Memory needs an explicit migration decision')

    if matcher is not None and existing_memories:
        for existing in existing_memories:
            require_learning_sources()
            comparison = matcher.compare(
                new_meaning=assessment.meaning,
                new_memory_type=assessment.memory_type,
                existing_memory=existing,
                conversation_context=tuple(conversation_context),
            )

            if comparison.relation == "duplicate":
                require_learning_sources()
                strengthen_memory(
                    existing["memory_id"],
                    confidence=assessment.confidence,
                    source_message_ids=source_message_ids,
                    source_archive_ids=source_archive_ids,
                    source_work_item_ids=source_work_item_ids,
                    instance_id=instance_id,
                )
                return ConsolidationResult(
                    action="duplicate_strengthened",
                    memory_id=existing["memory_id"],
                    assessment=assessment,
                )

            if comparison.relation == "supports":
                require_learning_sources()
                strengthen_memory(
                    existing["memory_id"],
                    confidence=assessment.confidence,
                    source_message_ids=source_message_ids,
                    source_archive_ids=source_archive_ids,
                    source_work_item_ids=source_work_item_ids,
                    instance_id=instance_id,
                )
                return ConsolidationResult(
                    action="strengthened",
                    memory_id=existing["memory_id"],
                    assessment=assessment,
                )

            if comparison.relation == "revises":
                require_learning_sources()
                revise_memory(
                    existing["memory_id"],
                    content=assessment.meaning,
                    memory_type=assessment.memory_type,
                    confidence=assessment.confidence,
                    importance=assessment.importance,
                    source_message_ids=source_message_ids,
                    source_archive_ids=source_archive_ids,
                    source_work_item_ids=source_work_item_ids,
                    instance_id=instance_id,
                )
                return ConsolidationResult(
                    action="revised",
                    memory_id=existing["memory_id"],
                    assessment=assessment,
                )

            if comparison.relation == "supersedes":
                require_learning_sources()
                new_memory = supersede_memory(
                    existing["memory_id"],
                    assessment.memory_type,
                    assessment.meaning,
                    confidence=assessment.confidence,
                    importance=assessment.importance,
                    source_message_ids=source_message_ids,
                    source_archive_ids=source_archive_ids,
                    instance_id=instance_id,
                    source_work_item_ids=source_work_item_ids,
                )
                if new_memory is None:
                    return ConsolidationResult(
                        action="needs_review",
                        memory_id=None,
                        assessment=assessment,
                    )
                return ConsolidationResult(
                    action="superseded",
                    memory_id=new_memory.memory_id,
                    assessment=assessment,
                )

            if comparison.relation == "contradicts":
                return ConsolidationResult(
                    action="conflict_detected",
                    memory_id=existing["memory_id"],
                    assessment=assessment,
                )

    # Deterministic exact-duplicate protection is the final guard
    # before creation when semantic comparison did not resolve the item.
    candidate_memory = {
        "memory_type": assessment.memory_type,
        "content": assessment.meaning,
    }

    candidate_fingerprint = memory_fingerprint(
        candidate_memory
    )

    for existing in existing_memories:
        if (
            memory_fingerprint(existing) == candidate_fingerprint
            and existing.get("status", "active") == "active"
        ):
            require_learning_sources()
            strengthen_memory(
                existing["memory_id"],
                confidence=assessment.confidence,
                source_message_ids=source_message_ids,
                source_archive_ids=source_archive_ids,
                source_work_item_ids=source_work_item_ids,
                instance_id=instance_id,
            )

            return ConsolidationResult(
                action="duplicate_strengthened",
                memory_id=existing["memory_id"],
                assessment=assessment,
            )

    require_learning_sources()
    memory = create_memory(
        assessment.memory_type,
        assessment.meaning,
        confidence=assessment.confidence,
        importance=assessment.importance,
        source_message_ids=source_message_ids,
        source_archive_ids=source_archive_ids,
        instance_id=instance_id,
        source_work_item_ids=source_work_item_ids,
    )

    return ConsolidationResult(
        action="created",
        memory_id=memory.memory_id,
        assessment=assessment,
    )


@dataclass(frozen=True)
class DuplicateCleanupResult:
    canonical_memory_id: str
    superseded_memory_id: str
    confidence: float
    reasoning: str | None = None


def _canonical_memory(memories):
    """
    Choose the deterministic survivor from a group of semantic duplicates.

    Preference order:
      1. higher importance
      2. higher confidence
      3. older memory
      4. stable memory ID tie-breaker
    """
    return min(
        memories,
        key=lambda memory: (
            -float(memory.get("importance", 0.5)),
            -float(memory.get("confidence", 1.0)),
            memory.get("created_at", ""),
            memory.get("memory_id", ""),
        ),
    )


def cleanup_semantic_duplicates(
    *,
    matcher,
    memories=None,
    minimum_confidence=0.90,
    conversation_context=(),
    instance_id=None,
):
    """
    Consolidate active memories that are semantically duplicate.

    Historical records are preserved. The selected canonical memory remains
    active while redundant memories are marked superseded.
    """
    if memories is None:
        memories = list_memories_for_context(status="active", instance_id=instance_id)

    active = list(memories)
    if any(memory.get('instance_id') != instance_id for memory in active):
        raise ValueError('Duplicate cleanup requires matching explicit instance ownership')
    results = []

    changed = True

    while changed:
        changed = False

        for i, first in enumerate(active):
            for j, second in enumerate(active):
                if j <= i:
                    continue

                comparison = matcher.compare(
                    new_meaning=first["content"],
                    new_memory_type=first["memory_type"],
                    existing_memory=second,
                    conversation_context=tuple(conversation_context),
                )

                if (
                    comparison.relation != "duplicate"
                    or comparison.confidence < minimum_confidence
                ):
                    continue

                canonical = _canonical_memory(
                    [first, second]
                )

                duplicate = (
                    second
                    if canonical["memory_id"] == first["memory_id"]
                    else first
                )

                strengthened = merge_duplicate_memories(
                    canonical['memory_id'],duplicate['memory_id'],instance_id=instance_id,
                )

                if strengthened is None:
                    continue

                results.append(
                    DuplicateCleanupResult(
                        canonical_memory_id=canonical["memory_id"],
                        superseded_memory_id=duplicate["memory_id"],
                        confidence=comparison.confidence,
                        reasoning=comparison.reasoning,
                    )
                )

                active = [
                    memory
                    for memory in active
                    if memory["memory_id"]
                    != duplicate["memory_id"]
                ]

                changed = True
                break

            if changed:
                break

    return results
