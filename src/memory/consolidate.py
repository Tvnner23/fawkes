from dataclasses import dataclass

from src.memory.semantic import SemanticMemoryAssessment
from src.memory.store import (
    create_memory,
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

    if matcher is not None and existing_memories:
        for existing in existing_memories:
            comparison = matcher.compare(
                new_meaning=assessment.meaning,
                new_memory_type=assessment.memory_type,
                existing_memory=existing,
                conversation_context=(),
            )

            if comparison.relation == "supports":
                strengthen_memory(
                    existing["memory_id"],
                    confidence=assessment.confidence,
                    source_message_ids=source_message_ids,
                    source_archive_ids=source_archive_ids,
                )
                return ConsolidationResult(
                    action="strengthened",
                    memory_id=existing["memory_id"],
                    assessment=assessment,
                )

            if comparison.relation == "revises":
                revise_memory(
                    existing["memory_id"],
                    content=assessment.meaning,
                    memory_type=assessment.memory_type,
                    confidence=assessment.confidence,
                    importance=assessment.importance,
                    source_message_ids=source_message_ids,
                    source_archive_ids=source_archive_ids,
                )
                return ConsolidationResult(
                    action="revised",
                    memory_id=existing["memory_id"],
                    assessment=assessment,
                )

            if comparison.relation == "supersedes":
                new_memory = supersede_memory(
                    existing["memory_id"],
                    assessment.memory_type,
                    assessment.meaning,
                    confidence=assessment.confidence,
                    importance=assessment.importance,
                    source_message_ids=source_message_ids,
                    source_archive_ids=source_archive_ids,
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

    memory = create_memory(
        assessment.memory_type,
        assessment.meaning,
        confidence=assessment.confidence,
        importance=assessment.importance,
        source_message_ids=source_message_ids,
        source_archive_ids=source_archive_ids,
    )

    return ConsolidationResult(
        action="created",
        memory_id=memory.memory_id,
        assessment=assessment,
    )
