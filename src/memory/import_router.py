from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ImportRoute:
    """
    Determines whether a candidate needs model-level semantic evaluation.
    """
    candidate_id: str
    route: str
    reason: str


OBVIOUS_EPHEMERAL = {
    "reloaded",
    "refreshed",
    "thanks",
    "thank you",
    "okay",
    "ok",
    "k",
    "lol",
    "lmao",
}


def route_import_candidate(candidate):
    """
    Route a historical candidate using cheap deterministic checks.

    Routes:
      local_reject  -> obvious artifact / useless content
      model         -> requires semantic judgment

    Deterministic routing should remain conservative. It must not
    eliminate candidates merely because they are short or unusual.
    """
    candidate_id = candidate["candidate_id"]
    content = candidate.get("content", "").strip()

    if not content:
        return ImportRoute(
            candidate_id=candidate_id,
            route="local_reject",
            reason="empty candidate",
        )

    normalized = re.sub(
        r"\\s+",
        " ",
        content.lower(),
    ).strip()

    if normalized in OBVIOUS_EPHEMERAL:
        return ImportRoute(
            candidate_id=candidate_id,
            route="local_reject",
            reason="known ephemeral interaction artifact",
        )

    if candidate.get("is_artifact") is True:
        return ImportRoute(
            candidate_id=candidate_id,
            route="local_reject",
            reason="candidate explicitly marked as artifact",
        )

    return ImportRoute(
        candidate_id=candidate_id,
        route="model",
        reason="semantic judgment required",
    )


def route_import_batch(candidates):
    """
    Route candidates without making any API calls.
    """
    return [
        route_import_candidate(candidate)
        for candidate in candidates
    ]
