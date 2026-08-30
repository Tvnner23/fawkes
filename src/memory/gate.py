import re


ARTIFACT_PATTERNS = (
    r"^\(\.venv\).*",
    r"^\$ ",
    r"^>\s*(JS|PY|JSON|EOF)\s*$",
    r"^Tanner_ChatGPT_Continuity_File\.docx$",
    r"^Pasted text(?:\(\d+\))?\.txt$",
    r"^Document$",
    r"^VM\d+:",
    r"^console\.log\(",
    r"^undefined$",
    r"^sudo apt install",
    r"^python -[cPm]",
    r"^python - <<",
    r"^git (?:add|commit|status|diff|log|restore|rm|stat)",
    r"^(?:sed|grep|cat|tail|head|find|printf) ",
    r"^bash: ",
    r"^Command '.*' not found",
    r"^Traceback \(most recent call last\):",
    r"^\*\*Context\*\*$",
    r"^\[https?://",
)


def _is_artifact_line(line: str) -> bool:
    line = line.strip()

    if not line:
        return False

    return any(
        re.search(pattern, line, re.IGNORECASE)
        for pattern in ARTIFACT_PATTERNS
    )


def looks_like_artifact(text: str) -> bool:
    """
    Detect candidates that are overwhelmingly capture artifacts.

    A single artifact-looking line does not invalidate a multiline candidate.
    The candidate is rejected only when the entire candidate consists of
    artifact/noise material.
    """
    text = text.strip()

    if not text:
        return True

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    if not lines:
        return True

    artifact_lines = sum(_is_artifact_line(line) for line in lines)

    # A single-line candidate is an artifact if that line is an artifact.
    if len(lines) == 1:
        return artifact_lines == 1

    # Multiline candidates are artifacts only when every meaningful line
    # appears to be capture/terminal/browser noise.
    return artifact_lines == len(lines)


def gate_memory_candidates(candidates):
    """
    Remove only candidates that are clearly capture artifacts.

    This layer does NOT decide whether something deserves memory.
    Semantic evaluation remains responsible for that decision.
    """
    return [
        candidate
        for candidate in candidates
        if not looks_like_artifact(candidate["content"])
    ]
