from dataclasses import dataclass


@dataclass(frozen=True)
class ImportDecision:
    """
    Human decision applied to an import audit.

    The original audit remains unchanged. This records the human's
    explicit disposition of that candidate.
    """
    candidate_id: str
    decision: str
    reviewer: str = "user"
    note: str = ""

    def __post_init__(self):
        if self.decision not in {
            "accept",
            "reject",
        }:
            raise ValueError(
                f"Invalid import decision: {self.decision}"
            )

        if not self.candidate_id:
            raise ValueError(
                "candidate_id cannot be empty"
            )


def create_import_decision(
    *,
    candidate_id,
    decision,
    reviewer="user",
    note="",
):
    return ImportDecision(
        candidate_id=candidate_id,
        decision=decision,
        reviewer=reviewer,
        note=note.strip(),
    )
