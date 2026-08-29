TERMINAL_ASSISTANT_MARKER = "\ue200memcite\ue201"


def normalize_message_text(role: str, text: str) -> str:
    if (
        role == "assistant"
        and text.endswith(TERMINAL_ASSISTANT_MARKER)
    ):
        return text[:-len(TERMINAL_ASSISTANT_MARKER)]

    return text
