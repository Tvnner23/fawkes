from datetime import datetime, timezone
import re

from src.memory.store import list_memories_for_context


DURABLE_MEMORY_TYPES = {
    "user_fact",
    "preference",
    "goal",
    "plan",
    "decision",
    "project",
    "relationship",
    "personality_development",
    "self_history",
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _recency_score(created_at: str) -> float:
    try:
        created = datetime.fromisoformat(created_at)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        age_days = max(
            0.0,
            (datetime.now(timezone.utc) - created).total_seconds() / 86400,
        )

        return 1.0 / (1.0 + (age_days / 30.0))
    except (TypeError, ValueError):
        return 0.5


def _durability_score(memory: dict) -> float:
    return 1.0 if memory.get("memory_type") in DURABLE_MEMORY_TYPES else 0.5


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
    durability = _durability_score(memory)
    recency = _recency_score(memory.get("created_at", ""))

    return (
        (coverage * 0.55)
        + (importance * 0.20)
        + (confidence * 0.10)
        + (durability * 0.10)
        + (recency * 0.05)
    )


def retrieve_memories(
    query: str,
    *,
    limit: int = 5,
    instance_id=None,
    include_unscoped=False,
) -> list[dict]:
    """
    Retrieve active memories relevant to a query.

    Importance and durability remain meaningful even when a memory
    has not been mentioned recently. Recency is only a ranking bonus.
    Retrieval can later be replaced by embeddings or hybrid search
    without changing callers.
    """
    memories = list_memories_for_context(
        status="active",
        instance_id=instance_id,
        include_unscoped=include_unscoped,
    )

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
