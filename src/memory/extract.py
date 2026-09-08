from src.capture.canonical import canonical_messages, message_allows_memory_learning
from src.memory.archive_context import memory_learning_enabled


def extract_memory_candidates(conversation_id: str, *, instance_id=None, include_unscoped=False):
    """
    Produce potential memories from canonical conversation history.

    This layer deliberately does NOT save memories.
    It identifies user-authored messages that may contain durable
    information and preserves their provenance for later evaluation.
    """
    if not memory_learning_enabled(instance_id):
        return []
    messages = canonical_messages(conversation_id,instance_id=instance_id,include_unscoped=include_unscoped)
    candidates = []

    for message in messages:
        if (message["role"] != "user" or not message_allows_memory_learning(message)
                or not memory_learning_enabled(message.get("instance_id"))):
            continue

        text = message["content"].strip()

        if not text:
            continue

        candidates.append(
            {
                "candidate_id": message["message_id"],
                "instance_id": message.get("instance_id"),
                "memory_learning_eligible": True,
                "memory_type": "unclassified",
                "content": text,
                "importance": None,
                "confidence": None,
                "source_message_ids": (
                    message["message_id"],
                ),
                "source_archive_ids": (
                    message["source_archive_id"],
                ),
                "created_at": message["created_at"],
            }
        )

    return candidates
