from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MemoryComparison:
    """
    Semantic relationship between new evidence and an existing memory.

    Valid relations:
      duplicate   - same underlying memory; consolidate evidence
      supports    - distinct evidence reinforcing the existing memory
      related     - conceptually related but independently useful; keep both
      revises     - updates/refines the existing memory
      supersedes  - replaces the existing memory
      contradicts - conflicts with the existing memory

    This is an interpretation, not persistent state.
    """
    relation: str
    confidence: float
    reasoning: str | None = None


class MemoryMatcher(Protocol):
    """
    Provider-independent interface for comparing new semantic meaning
    against an existing Phoenix memory.

    Implementations may use local models, remote models, embeddings,
    future Phoenix models, or combinations of them.
    """

    def compare(
        self,
        *,
        new_meaning: str,
        new_memory_type: str,
        existing_memory: dict,
        conversation_context: tuple[dict, ...] = (),
    ) -> MemoryComparison:
        ...


def compare_memory(
    matcher: MemoryMatcher,
    *,
    new_meaning: str,
    new_memory_type: str,
    existing_memory: dict,
    conversation_context=(),
) -> MemoryComparison:
    return matcher.compare(
        new_meaning=new_meaning,
        new_memory_type=new_memory_type,
        existing_memory=existing_memory,
        conversation_context=tuple(conversation_context),
    )
