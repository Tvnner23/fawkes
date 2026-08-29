from dataclasses import dataclass

from src.memory.semantic import SemanticMemoryAssessment
from src.memory.store import create_memory


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
