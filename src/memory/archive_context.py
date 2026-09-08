from src.capture.canonical import canonical_messages


class ArchiveContextReviewRequired(ValueError):
    """The retained candidate no longer has eligible attributable context."""


def build_archive_context(
    conversation_id: str,
    *,
    center_message_id=None,
    before=40,
    after=40,
    max_messages=None,
    instance_id=None,
    include_unscoped=False,
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

    return tuple(
        {
            "role": message["role"],
            "content": message["content"],
            "message_id": message["message_id"],
            "created_at": message.get("created_at"),
            "source_archive_id": message.get("source_archive_id"),
            "instance_id": message.get('instance_id'),
        }
        for message in messages
    )
