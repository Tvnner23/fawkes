from dataclasses import dataclass


@dataclass(frozen=True)
class DevelopmentProposal:
    """
    A proposed improvement to Fawkes based on accumulated experience.

    Proposals are intentionally separate from executable code changes.
    Fawkes may identify and describe an improvement, but applying it
    requires an explicit external action.
    """
    category: str
    observation: str
    proposed_change: str
    rationale: str
    confidence: float
    source_memory_ids: tuple = ()
    source_message_ids: tuple = ()


def propose_development(
    *,
    observation: str,
    proposed_change: str,
    rationale: str,
    category: str = "system_improvement",
    confidence: float = 0.0,
    source_memory_ids=(),
    source_message_ids=(),
):
    if not observation.strip():
        raise ValueError("observation cannot be empty")

    if not proposed_change.strip():
        raise ValueError("proposed_change cannot be empty")

    if not rationale.strip():
        raise ValueError("rationale cannot be empty")

    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")

    return DevelopmentProposal(
        category=category,
        observation=observation.strip(),
        proposed_change=proposed_change.strip(),
        rationale=rationale.strip(),
        confidence=float(confidence),
        source_memory_ids=tuple(source_memory_ids),
        source_message_ids=tuple(source_message_ids),
    )
