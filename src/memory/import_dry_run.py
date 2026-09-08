from dataclasses import dataclass


@dataclass(frozen=True)
class ImportDryRunResult:
    total_candidates: int
    local_rejected: int
    model_candidates: int
    estimated_cost: float
    paid_provider_required: bool
    warning: str


def estimate_import_cost(
    *,
    model_candidates,
    estimated_cost_per_candidate,
):
    if model_candidates < 0:
        raise ValueError(
            "model_candidates cannot be negative"
        )

    if estimated_cost_per_candidate < 0:
        raise ValueError(
            "estimated_cost_per_candidate cannot be negative"
        )

    return (
        float(model_candidates)
        * float(estimated_cost_per_candidate)
    )


def build_import_dry_run(
    *,
    routes,
    estimated_cost_per_candidate=0.0,
):
    total = len(routes)

    local_rejected = sum(
        route.route == "local_reject"
        for route in routes
    )

    model_candidates = sum(
        route.route == "model"
        for route in routes
    )

    estimated_cost = estimate_import_cost(
        model_candidates=model_candidates,
        estimated_cost_per_candidate=estimated_cost_per_candidate,
    )

    paid_provider_required = (
        model_candidates > 0
        and estimated_cost > 0
    )

    if paid_provider_required:
        warning = (
            "PAID PROVIDER REQUIRED: "
            f"{model_candidates} candidates could incur approximately "
            f"${estimated_cost:.4f} in external API cost. "
            "No provider call was made by this dry run."
        )
    else:
        warning = (
            "NO PAID PROVIDER REQUIRED FOR THIS DRY RUN. "
            "No provider call was made."
        )

    return ImportDryRunResult(
        total_candidates=total,
        local_rejected=local_rejected,
        model_candidates=model_candidates,
        estimated_cost=estimated_cost,
        paid_provider_required=paid_provider_required,
        warning=warning,
    )
