import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
DEVELOPMENT_DIR = ROOT / "memory" / "development"


def retrieve_development_proposals(
    query: str,
    *,
    limit=5,
):
    """
    Retrieve previously recorded development proposals using simple
    deterministic text matching.

    This is intentionally provider-independent. Semantic retrieval can
    replace or augment this later without changing the stored format.
    """
    query_terms = {
        term.lower()
        for term in query.split()
        if term.strip()
    }

    if not query_terms:
        return []

    matches = []

    if not DEVELOPMENT_DIR.exists():
        return []

    for path in DEVELOPMENT_DIR.glob("*.json"):
        try:
            record = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue

        searchable = " ".join(
            str(record.get(field, ""))
            for field in (
                "category",
                "observation",
                "proposed_change",
                "rationale",
            )
        ).lower()

        score = sum(
            1
            for term in query_terms
            if term in searchable
        )

        if score:
            matches.append((score, record))

    matches.sort(
        key=lambda item: (
            -item[0],
            item[1].get("created_at", ""),
        )
    )

    return [
        record
        for _, record in matches[:limit]
    ]
