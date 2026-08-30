from src.capture.canonical import canonical_messages


def build_archive_context(
    conversation_id: str,
    *,
    center_message_id=None,
    before=40,
    after=40,
    max_messages=None,
):
    """
    Build bounded model-ready context from the canonical conversation.

    When center_message_id is supplied, context is centered around that
    message so short or referential statements retain their local meaning.

    The canonical conversation remains derived from the immutable Archive.
    This function only prepares context; it does not modify archived data.
    """
    messages = canonical_messages(conversation_id)

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
            raise ValueError(
                f"Message {center_message_id!r} was not found "
                f"in conversation {conversation_id!r}"
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
        }
        for message in messages
    )
