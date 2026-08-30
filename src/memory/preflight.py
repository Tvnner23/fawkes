import json


def estimate_context_chars(conversation_context):
    """
    Estimate the serialized size of model context in characters.

    This is deliberately provider-independent. It is a safety check,
    not an exact billing/token calculator.
    """
    return len(
        json.dumps(
            list(conversation_context),
            ensure_ascii=False,
        )
    )


def estimate_request_chars(
    *,
    content,
    conversation_context,
):
    """
    Estimate the total character payload for one semantic evaluation.
    """
    context_chars = estimate_context_chars(conversation_context)

    return context_chars + len(content)


def preflight_candidate(
    *,
    content,
    conversation_context,
    max_request_chars=100_000,
):
    """
    Refuse oversized semantic-evaluation requests before they reach a model.

    The limit is intentionally conservative because character count is only
    an approximation of token usage.
    """
    request_chars = estimate_request_chars(
        content=content,
        conversation_context=conversation_context,
    )

    if request_chars > max_request_chars:
        raise ValueError(
            "Semantic memory request exceeds preflight size limit: "
            f"{request_chars} chars > {max_request_chars} chars"
        )

    return request_chars
