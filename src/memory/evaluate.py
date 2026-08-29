from src.memory.extract import extract_memory_candidates


def _looks_ephemeral(text: str):
    lowered = text.lower().strip()

    ephemeral_patterns = (
        "what is ",
        "what's ",
        "how do i ",
        "how can i ",
        "why does ",
        "why is ",
        "can you ",
        "could you ",
        "give me ",
        "show me ",
        "explain ",
        "next command",
        "paste the output",
        "reloaded",
        "refreshed",
    )

    command_patterns = (
        "(.venv)",
        "python -",
        "cat >",
        "sed ",
        "grep ",
        "find ",
        "echo ",
        "cp ",
        "cmp ",
    )

    return (
        lowered.startswith(ephemeral_patterns)
        or lowered.startswith(command_patterns)
    )


def _looks_durable(text: str):
    lowered = text.lower().strip()

    durable_patterns = (
        "i want ",
        "i prefer ",
        "i like ",
        "i don't like ",
        "i dislike ",
        "i hate ",
        "my goal ",
        "my plan ",
        "i decided ",
        "i chose ",
        "i'm considering ",
        "im considering ",
        "we decided ",
        "we're going to ",
        "we are going to ",
        "remember ",
        "i'm trying to ",
        "im trying to ",
        "i need to ",
        "i'm interested in ",
        "im interested in ",
        "i'm working on ",
        "im working on ",
    )

    durable_words = (
        "goal",
        "plan",
        "prefer",
        "preference",
        "favorite",
        "interested",
        "working on",
        "building",
        "career",
        "degree",
        "school",
        "job",
        "project",
        "decided",
        "chosen",
        "want to",
        "trying to",
        "considering",
    )

    if lowered.startswith(durable_patterns):
        return True

    return any(word in lowered for word in durable_words)


def evaluate_candidate(candidate: dict):
    text = candidate["content"].strip()

    if not text:
        return {
            **candidate,
            "decision": "likely_ephemeral",
            "evaluation_confidence": 1.0,
            "importance": 0.0,
        }

    if _looks_ephemeral(text):
        return {
            **candidate,
            "decision": "likely_ephemeral",
            "evaluation_confidence": 0.9,
            "importance": 0.1,
        }

    if _looks_durable(text):
        return {
            **candidate,
            "decision": "likely_memory",
            "evaluation_confidence": 0.7,
            "importance": 0.7,
        }

    return {
        **candidate,
        "decision": "needs_review",
        "evaluation_confidence": 0.4,
        "importance": 0.5,
    }


def evaluate_conversation(conversation_id: str):
    candidates = extract_memory_candidates(conversation_id)

    return [
        evaluate_candidate(candidate)
        for candidate in candidates
    ]
