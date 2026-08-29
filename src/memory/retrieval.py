import re

from src.memory.store import list_memories


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _score(query: str, memory: dict) -> float:
    query_tokens = _tokens(query)
    memory_tokens = _tokens(memory.get("content", ""))

    if not query_tokens or not memory_tokens:
        return 0.0

    overlap = len(query_tokens & memory_tokens)
    if overlap == 0:
        return 0.0

    coverage = overlap / len(query_tokens)

    importance = float(memory.get("importance", 0.5))
    confidence = float(memory.get("confidence", 1.0))

    return (
        (coverage * 0.70)
        + (importance * 0.15)
        + (confidence * 0.15)
    )


def retrieve_memories(
    query: str,
    *,
    limit: int = 5,
) -> list[dict]:
    """
    Retrieve active memories relevant to a query.

    Retrieval is intentionally isolated from memory storage and
    consolidation so the scoring strategy can later be replaced by
    embeddings or hybrid retrieval without changing callers.
    """
    memories = list_memories(status="active")

    ranked = []

    for memory in memories:
        score = _score(query, memory)

        if score <= 0.0:
            continue

        ranked.append(
            {
                **memory,
                "retrieval_score": score,
            }
        )

    ranked.sort(
        key=lambda memory: (
            memory["retrieval_score"],
            float(memory.get("importance", 0.5)),
            float(memory.get("confidence", 1.0)),
        ),
        reverse=True,
    )

    return ranked[:limit]
