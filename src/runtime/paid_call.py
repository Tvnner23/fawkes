from dataclasses import dataclass


@dataclass(frozen=True)
class PaidCallEstimate:
    provider: str
    model: str
    estimated_cost: float
    reason: str
    estimated_calls: int = 1


class PaidCallGuard:
    """
    Single checkpoint for external paid model calls.

    The guard estimates cost before execution and requires explicit
    authorization when a paid provider would be used.

    This is infrastructure accounting, not consumer-facing billing.
    """

    def __init__(
        self,
        *,
        provider="openai",
        require_confirmation=True,
        cost_per_call=0.0,
        notifier=None,
    ):
        self.provider = provider
        self.require_confirmation = require_confirmation
        self.cost_per_call = float(cost_per_call)
        self.notifier = notifier

        if self.cost_per_call < 0:
            raise ValueError(
                "cost_per_call cannot be negative"
            )

    def estimate(
        self,
        *,
        model,
        reason,
        estimated_calls=1,
    ):
        if estimated_calls < 1:
            raise ValueError(
                "estimated_calls must be at least 1"
            )

        estimated_calls = int(estimated_calls)

        return PaidCallEstimate(
            provider=self.provider,
            model=model,
            estimated_cost=(
                self.cost_per_call * estimated_calls
            ),
            reason=reason,
            estimated_calls=estimated_calls,
        )

    def authorize(
        self,
        *,
        model,
        reason,
        estimated_calls=1,
        explicit_authorization=False,
    ):
        estimate = self.estimate(
            model=model,
            reason=reason,
            estimated_calls=estimated_calls,
        )

        if estimate.estimated_cost > 0:
            message = (
                "PAID PROVIDER CALL: "
                f"{estimate.provider}/{estimate.model} "
                f"estimated at approximately "
                f"${estimate.estimated_cost:.4f} "
                f"for up to {estimate.estimated_calls} "
                f"provider call(s) during this turn "
                f"({estimate.reason})."
            )

            if self.notifier is not None:
                self.notifier(message)

            if self.require_confirmation and not explicit_authorization:
                raise PermissionError(
                    message
                    + " Explicit authorization required."
                )

        return estimate
