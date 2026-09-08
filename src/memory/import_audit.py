from dataclasses import dataclass


IMPORT_TIERS = {
    "S": "core",
    "A": "durable",
    "B": "useful",
    "C": "contextual",
    "D": "ephemeral",
    "X": "artifact",
}


@dataclass(frozen=True)
class ImportAudit:
    """
    Human-auditable decision record for historical memory import.

    Every candidate can be inspected before becoming persistent memory.
    """
    candidate_id: str
    content: str
    memory_type: str
    tier: str
    decision: str
    confidence: float
    importance: float
    reasoning: str
    source_message_ids: tuple = ()
    source_archive_ids: tuple = ()

    def __post_init__(self):
        if self.tier not in IMPORT_TIERS:
            raise ValueError(f"Invalid import tier: {self.tier}")

        if self.decision not in {
            "accept",
            "review",
            "reject",
        }:
            raise ValueError(f"Invalid import decision: {self.decision}")

        if not self.content.strip():
            raise ValueError("content cannot be empty")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

        if not 0.0 <= self.importance <= 1.0:
            raise ValueError("importance must be between 0 and 1")

        if not self.reasoning.strip():
            raise ValueError("reasoning cannot be empty")


def create_import_audit(
    *,
    candidate_id,
    content,
    memory_type,
    tier,
    decision,
    confidence,
    importance,
    reasoning,
    source_message_ids=(),
    source_archive_ids=(),
):
    return ImportAudit(
        candidate_id=candidate_id,
        content=content.strip(),
        memory_type=memory_type,
        tier=tier,
        decision=decision,
        confidence=float(confidence),
        importance=float(importance),
        reasoning=reasoning.strip(),
        source_message_ids=tuple(source_message_ids),
        source_archive_ids=tuple(source_archive_ids),
    )
