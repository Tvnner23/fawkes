from src.capture.canonical import canonical_messages, message_allows_memory_learning
from src.capture import canonical
from src.capture.storage import metadata_paths, read_metadata
from src.runtime.personal_recording import RecordingPolicyStore


class ArchiveContextReviewRequired(ValueError):
    """The retained candidate no longer has eligible attributable context."""


class ArchiveSourceLearningDenied(ArchiveContextReviewRequired):
    """A resolved source explicitly disallows learning, rather than being missing."""


class MemoryLearningPaused(PermissionError):
    """The current policy does not permit starting another learning step."""


def memory_learning_enabled(instance_id):
    """Read the current owner's setting without creating or changing state.

    Unscoped legacy callers retain their existing ownership-review behavior.
    Invalid/unreadable configured policy raises instead of assuming learning on.
    """
    return instance_id is None or RecordingPolicyStore(instance_id).latch().memory_learning is True


def require_memory_learning(instance_id):
    if not memory_learning_enabled(instance_id):
        raise MemoryLearningPaused("Memory learning is disabled by the current recording policy")


def require_archive_source_learning(*, instance_id=None, source_message_ids=(), source_archive_ids=()):
    """Resolve claimed Archive sources instead of trusting caller projections.

    A missing *stored marker* is eligible legacy evidence. A missing source is
    not. All revisions of a resolved message participate, including an older
    denied revision when a caller cites a newer allowed capture. This remains
    an Archive read: no historical bytes or processing queues are rewritten.
    """
    _require_archive_source_learning(instance_id=instance_id, source_message_ids=source_message_ids,
                                    source_archive_ids=source_archive_ids, cache={})


def _require_archive_source_learning(*, instance_id, source_message_ids, source_archive_ids, cache):
    def identities(values):
        if not isinstance(values, (tuple, list)) or any(not isinstance(value, str) or not value for value in values):
            raise ArchiveContextReviewRequired("Archive evidence identities are malformed")
        return set(values)
    message_ids, archive_ids = identities(source_message_ids), identities(source_archive_ids)
    if not message_ids and not archive_ids:
        return
    try:
        if "metadata" not in cache:
            cache["metadata"] = [read_metadata(path) for path in metadata_paths(canonical.META_DIR, allow_missing=True)]
        metadata = cache["metadata"]
        owned = [item for item in metadata if item.get("instance_id") == instance_id
                 and item.get("capture_type") == "message_state"]
        selected = [item for item in owned if item["archive_id"] in archive_ids]
        if archive_ids and {item["archive_id"] for item in selected} != archive_ids:
            raise ArchiveContextReviewRequired("Archive evidence is missing, foreign, or not a message capture")
        # Archive references provide an exact conversation boundary. Message-ID
        # only legacy callers need a scoped scan; ambiguous identities fail shut.
        conversations = {item.get("conversation_id") for item in (selected if archive_ids else owned)}
        if any(not isinstance(value, str) or not value for value in conversations):
            raise ArchiveContextReviewRequired("Archive evidence has no attributable conversation")
        resolved_messages, resolved_archives = {}, set()
        for conversation_id in conversations:
            key = (instance_id, conversation_id)
            if key not in cache:
                cache[key] = canonical.load_message_states(conversation_id, instance_id=instance_id, strict=True)
            states = cache[key]
            for (owner, message_id), revisions in states.items():
                if owner != instance_id:
                    continue
                revision_ids = {revision["archive_id"] for revision in revisions}
                if message_id not in message_ids and not archive_ids.intersection(revision_ids):
                    continue
                if not all(revision["memory_learning_eligible"] is True for revision in revisions):
                    raise ArchiveSourceLearningDenied("Referenced Archive message does not allow Memory learning")
                if message_id in resolved_messages and resolved_messages[message_id] != conversation_id:
                    raise ArchiveContextReviewRequired("Archive message identity is ambiguous across conversations")
                resolved_messages[message_id] = conversation_id
                resolved_archives.update(revision_ids)
        if not message_ids.issubset(resolved_messages) or not archive_ids.issubset(resolved_archives):
            raise ArchiveContextReviewRequired("Referenced Archive evidence cannot be resolved")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, ArchiveContextReviewRequired):
            raise
        raise ArchiveContextReviewRequired("Referenced Archive evidence cannot be validated") from exc


def filter_memory_learning_context(messages, *, instance_id=None, include_unscoped=False):
    """Filter denied neighbors by their stored decision, not projected claims.

    Missing/corrupt/foreign references still require review. The per-call cache
    reads metadata once and each needed conversation once; nothing is reused
    across evaluator/mutation boundaries or stored in a parallel ledger.
    Messages with no retained references remain ordinary supplied context.
    """
    cache, allowed = {}, []
    for message in messages:
        if not isinstance(message, dict):
            raise ArchiveContextReviewRequired("Conversation context is malformed")
        owner = message.get("instance_id", instance_id)
        if owner != instance_id and not (include_unscoped and owner is None):
            raise ArchiveContextReviewRequired("Conversation context contains a foreign instance")
        if not message_allows_memory_learning(message):
            continue
        message_ids = tuple(message.get("source_message_ids", ())) + (
            (message["message_id"],) if message.get("message_id") is not None else ())
        archive_ids = tuple(message.get("source_archive_ids", ())) + (
            (message["source_archive_id"],) if message.get("source_archive_id") is not None else ())
        try:
            _require_archive_source_learning(instance_id=owner, source_message_ids=message_ids,
                                            source_archive_ids=archive_ids, cache=cache)
        except ArchiveSourceLearningDenied:
            continue
        allowed.append(message)
    return tuple(allowed)


def build_archive_context(
    conversation_id: str,
    *,
    center_message_id=None,
    before=40,
    after=40,
    max_messages=None,
    instance_id=None,
    include_unscoped=False,
    memory_learning_only=False,
):
    """
    Build bounded model-ready context from the canonical conversation.

    When center_message_id is supplied, context is centered around that
    message so short or referential statements retain their local meaning.

    The canonical conversation remains derived from the immutable Archive.
    This function only prepares context; it does not modify archived data.
    """
    messages = canonical_messages(conversation_id,instance_id=instance_id,include_unscoped=include_unscoped)
    if instance_id is not None and any(message.get('instance_id') != instance_id and not
        (include_unscoped and message.get('instance_id') is None) for message in messages):
        raise ArchiveContextReviewRequired('Canonical context contains a foreign instance')

    if center_message_id is not None:
        center_index = next(
            (
                index
                for index, message in enumerate(messages)
                if message["message_id"] == center_message_id
            ),
            None,
        )

        if center_index is None:
            raise ArchiveContextReviewRequired(
                f"Message {center_message_id!r} was not found "
                f"in eligible context for conversation {conversation_id!r}; "
                "explicit evidence/ownership review is required"
            )

        start = max(0, center_index - before)
        end = center_index + after + 1
        messages = messages[start:end]

    elif max_messages is not None:
        messages = messages[-max_messages:]

    if memory_learning_only:
        messages = [message for message in messages if message_allows_memory_learning(message)]
        if center_message_id is not None and not any(
            message["message_id"] == center_message_id for message in messages
        ):
            raise ArchiveContextReviewRequired("Candidate does not allow Memory learning")

    return tuple(
        {
            "role": message["role"],
            "content": message["content"],
            "message_id": message["message_id"],
            "created_at": message.get("created_at"),
            "source_archive_id": message.get("source_archive_id"),
            "instance_id": message.get('instance_id'),
            **({"memory_learning_eligible": message_allows_memory_learning(message)}
               if "memory_learning_eligible" in message else {}),
        }
        for message in messages
    )
