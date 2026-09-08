from collections import Counter

from src.memory.extract import extract_memory_candidates
from src.memory.gate import gate_memory_candidates
from src.memory.import_router import route_import_batch
from src.memory.import_dry_run import build_import_dry_run


CONVERSATION_ID = "6a925b48-3ad8-83ea-aea0-3f55d335093b"


def main():
    print()
    print("============================================================")
    print("              FAWKES HISTORICAL IMPORT REHEARSAL")
    print("============================================================")
    print()
    print("MODE: LOCAL ONLY")
    print("API CALLS: NONE")
    print("MEMORY WRITES: NONE")
    print()

    candidates = extract_memory_candidates(
        CONVERSATION_ID
    )

    gated = gate_memory_candidates(
        candidates
    )

    routes = route_import_batch(
        gated
    )

    dry_run = build_import_dry_run(
        routes=routes,
        estimated_cost_per_candidate=0.012,
    )

    route_counts = Counter(
        route.route
        for route in routes
    )

    rejection_reasons = Counter(
        route.reason
        for route in routes
        if route.route == "local_reject"
    )

    print("===== CANDIDATE PIPELINE =====")
    print(f"Raw candidates:       {len(candidates)}")
    print(f"After artifact gate:  {len(gated)}")
    print(f"Local rejected:       {dry_run.local_rejected}")
    print(f"Model candidates:     {dry_run.model_candidates}")
    print()

    print("===== ROUTING =====")
    for route, count in sorted(
        route_counts.items()
    ):
        print(f"{route:20} {count}")
    print()

    print("===== LOCAL REJECTIONS =====")
    if rejection_reasons:
        for reason, count in rejection_reasons.most_common():
            print(f"{count:4}  {reason}")
    else:
        print("None")
    print()

    print("===== ESTIMATED EXTERNAL COST =====")
    print(
        f"Estimated candidates:  {dry_run.model_candidates}"
    )
    print(
        f"Estimated cost:        ${dry_run.estimated_cost:.4f}"
    )
    print()

    if dry_run.paid_provider_required:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(dry_run.warning)
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    else:
        print(dry_run.warning)

    print()
    print("===== SAFETY =====")
    print("No API calls were made.")
    print("No memories were persisted.")
    print("No import decisions were applied.")
    print()

    print("============================================================")


if __name__ == "__main__":
    main()
