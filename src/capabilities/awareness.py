"""Operational self-knowledge and request-scoped capability selection.

This module describes powers, not personality. It never grants authority and it
cannot make an unavailable capability live.
"""

from dataclasses import dataclass
import json
import re


_CAPABILITY_QUESTION = re.compile(r"\b(?:what can you do|can you|are you able|your capabilities|your powers|have web research)\b", re.I)
_EXTERNAL_SPECIFIC = re.compile(
    r"\b(?:current|latest|today|schedule|availability|available|official|verify|actual|"
    r"my\s+(?:degree|program|curriculum|classes|courses)|qualified|qualifications?|"
    r"credentials?|professional background|academic background|laws?|regulations?|prices?|news)\b", re.I
)
_VISUAL = re.compile(r"\b(?:chart|graph|plot|diagram|flowchart|timeline|table|visual(?:ly|ization)?)\b", re.I)
_LIBRARY = re.compile(r"\b(?:my\s+(?:textbook|book|library)|chapter|page\s+\d+|saved\s+(?:book|document))\b", re.I)
_EXTERNAL_OPT_OUT = re.compile(
    r"\b(?:(?:do\s+not|don['’]?t)\s+(?:need|use|want)\s+(?:current\s+information|web\s+research|research)|"
    r"(?:do\s+not|don['’]?t)\s+research(?:\s+the\s+web)?)\b", re.I,
)
from src.capabilities.continuity import is_continuity_reference


@dataclass(frozen=True)
class CapabilitySelection:
    capability_id: str
    relevance: str
    required: bool = False
    missing_information: tuple[str, ...] = ()

    def as_dict(self):
        return {"capability_id": self.capability_id, "relevance": self.relevance,
                "required": self.required, "missing_information": list(self.missing_information)}


class CapabilityAwareness:
    """Read-only knowledge projection over authoritative runtime manifests."""

    def __init__(self, manifests):
        self.manifests = tuple(item for item in manifests if isinstance(item, dict))
        self.by_id = {item.get("name"): item for item in self.manifests if item.get("name")}

    def available(self, capability_id):
        item = self.by_id.get(capability_id)
        return bool(item and item.get("availability") in {"live", "partial"})

    def select(self, request, *, attachments=(), library_evidence=()):
        text = str(request or "")
        selected = []
        if is_continuity_reference(text) and self.available("continuity.retrieve"):
            selected.append(CapabilitySelection(
                "continuity.retrieve", "The request contains a natural reference to prior interaction context.", True,
                ("the specific prior interaction and its surrounding meaning",),
            ))
        if attachments and self.available("media.chat_analyze"):
            selected.append(CapabilitySelection(
                "media.chat_analyze", "The rider supplied media whose content is needed for this turn.", True,
                ("content contained in the attached media",),
            ))
        if _LIBRARY.search(text) and self.available("library.search"):
            selected.append(CapabilitySelection(
                "library.search", "The request refers to rider-retained Library material.", True,
                (() if library_evidence else ("the relevant retained source passage",)),
            ))
        if _EXTERNAL_SPECIFIC.search(text) and not _EXTERNAL_OPT_OUT.search(text) and self.available("web.research"):
            selected.append(CapabilitySelection(
                "web.research",
                "The answer depends on specific external facts that should be verified rather than guessed.",
                True, ("current authoritative external evidence",),
            ))
        if _VISUAL.search(text) and self.available("presentation.visualize"):
            selected.append(CapabilitySelection(
                "presentation.visualize", "The rider requested or would materially benefit from visual communication.",
                bool(re.search(r"\b(?:make|create|draw|plot|graph|show|visuali[sz]e)\b", text, re.I)),
            ))
        if _CAPABILITY_QUESTION.search(text):
            for manifest in self.manifests:
                name = manifest.get("name")
                if name and not any(item.capability_id == name for item in selected):
                    selected.append(CapabilitySelection(name, "The rider asked about actual capability availability."))
        return tuple(selected)

    def reasoning_context(self, selections):
        selected_ids = {item.capability_id for item in selections}
        knowledge = []
        for manifest in self.manifests:
            if manifest.get("name") not in selected_ids:
                continue
            knowledge.append({
                key: manifest.get(key) for key in (
                    "name", "display_name", "description", "availability", "availability_reason",
                    "acceptance_status", "input_modalities", "output_modalities", "features",
                    "appropriate_use", "inappropriate_use", "limitations", "authorization_mode",
                    "execution_boundary", "presentation_options", "dependencies",
                    "provenance_requirements", "effects",
                )
            })
        return json.dumps({"selected": [item.as_dict() for item in selections], "knowledge": knowledge}, ensure_ascii=False)
