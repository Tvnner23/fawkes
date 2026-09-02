from dataclasses import dataclass


@dataclass(frozen=True)
class CostEstimate:
    """
    Estimated external cost for one Fawkes operation.

    Costs are tracked internally so the eventual consumer experience
    can remain subscription-based rather than per-request billing.
    """
    provider: str
    model: str
    estimated_cost: float
    reason: str

    def __post_init__(self):
        if self.estimated_cost < 0:
            raise ValueError("estimated_cost cannot be negative")

        if not self.provider.strip():
            raise ValueError("provider cannot be empty")

        if not self.model.strip():
            raise ValueError("model cannot be empty")

        if not self.reason.strip():
            raise ValueError("reason cannot be empty")


@dataclass(frozen=True)
class CostBudget:
    """
    Internal spending guardrail.

    This is an infrastructure control, not a consumer-facing
    per-request billing mechanism.
    """
    limit: float
    spent: float = 0.0

    def __post_init__(self):
        if self.limit < 0:
            raise ValueError("limit cannot be negative")

        if self.spent < 0:
            raise ValueError("spent cannot be negative")

    @property
    def remaining(self):
        return max(0.0, self.limit - self.spent)

    def can_afford(self, estimate: CostEstimate):
        return estimate.estimated_cost <= self.remaining

    def record(self, estimate: CostEstimate):
        if not self.can_afford(estimate):
            raise RuntimeError(
                "Operation exceeds the configured Fawkes cost budget"
            )

        return CostBudget(
            limit=self.limit,
            spent=self.spent + estimate.estimated_cost,
        )
