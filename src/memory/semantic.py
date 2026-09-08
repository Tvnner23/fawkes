"""
Model-independent semantic evaluation contracts for Phoenix memory.

This module defines what Phoenix needs from semantic understanding
without defining how that understanding is produced.

No wording, prefix, keyword, or model-provider assumptions belong here.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SemanticMemoryAssessment:
    """
    A semantic interpretation of conversation evidence.

    This is an assessment, not persistent memory state. Memory
    consolidation decides what, if anything, should be stored.
    """

    should_remember: bool
    memory_type: str | None
    meaning: str | None
    confidence: float
    importance: float
    reasoning: str | None = None
    supporting_message_ids: tuple[str, ...] = ()
    supporting_archive_ids: tuple[str, ...] = ()
    contract_version: str = "semantic-memory-v2"


class SemanticMemoryEvaluator(Protocol):
    """
    Provider-independent interface for semantic memory evaluation.

    Implementations may use local models, remote models, future Phoenix
    models, or other semantic systems. Callers must not depend on the
    provider used.
    """

    def evaluate(
        self,
        *,
        content: str,
        conversation_context: tuple[dict, ...] = (),
    ) -> SemanticMemoryAssessment:
        ...


def evaluate_semantically(
    evaluator: SemanticMemoryEvaluator,
    *,
    content: str,
    conversation_context=(),
) -> SemanticMemoryAssessment:
    """
    Evaluate meaning through the supplied semantic provider.

    Conversation context is intentionally available so statements such
    as "yeah, that's the one" can be understood from surrounding history.
    """
    return evaluator.evaluate(
        content=content,
        conversation_context=tuple(conversation_context),
    )
