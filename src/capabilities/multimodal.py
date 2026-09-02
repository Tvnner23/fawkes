"""Provider-neutral modality, provenance, authority, and privacy contracts.

These contracts describe capability boundaries. They do not activate media
upload, provider transmission, device control, or any new permission.
"""

from dataclasses import dataclass
import re


MODALITIES = frozenset({
    "text", "document", "pdf", "image", "screenshot", "audio", "video",
    "chart", "diagram",
})
AUTHORITY_ACTIONS = frozenset({
    "read", "analyze", "create", "modify", "delete", "install",
    "communicate_external", "consequential_action",
})
AUTHORIZATION_MODES = frozenset({
    "pre_granted", "task_request", "explicit_confirmation", "prohibited",
})
EXECUTION_BOUNDARIES = frozenset({
    "internal", "external_read", "external_write", "protected_foundation",
})
PRIVACY_CLASSES = frozenset({
    "standard", "potentially_private", "highly_private", "restricted",
})
LOCATOR_KINDS = frozenset({
    "document_page", "document_section", "image_region", "audio_segment",
    "video_segment", "video_frame", "chart_data", "diagram_element",
    "native_locator",
})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_HIGH_CONSEQUENCE = frozenset({
    "delete", "install", "communicate_external", "consequential_action",
})


def _tuple_of_known(values, known, label):
    values = tuple(values)
    if any(item not in known for item in values):
        raise ValueError(f"unknown {label}")
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")
    return values


@dataclass(frozen=True)
class MultimodalCapabilityContract:
    """What a capability can perceive and produce, independently."""

    input_modalities: tuple[str, ...] = ("text",)
    output_modalities: tuple[str, ...] = ("text",)

    def __post_init__(self):
        object.__setattr__(self, "input_modalities", _tuple_of_known(
            self.input_modalities, MODALITIES, "input modality"
        ))
        object.__setattr__(self, "output_modalities", _tuple_of_known(
            self.output_modalities, MODALITIES, "output modality"
        ))
        if not self.input_modalities or not self.output_modalities:
            raise ValueError("capability modalities cannot be empty")


@dataclass(frozen=True)
class AuthorityContract:
    """Effects and authorization boundary; capability is not personality."""

    actions: tuple[str, ...] = ("read",)
    execution_boundary: str = "internal"
    authorization_mode: str = "pre_granted"

    def __post_init__(self):
        object.__setattr__(self, "actions", _tuple_of_known(
            self.actions, AUTHORITY_ACTIONS, "authority action"
        ))
        if self.execution_boundary not in EXECUTION_BOUNDARIES:
            raise ValueError("unknown execution boundary")
        if self.authorization_mode not in AUTHORIZATION_MODES:
            raise ValueError("unknown authorization mode")
        if _HIGH_CONSEQUENCE.intersection(self.actions) and self.authorization_mode not in {
            "explicit_confirmation", "prohibited",
        }:
            raise ValueError("consequential authority requires confirmation or prohibition")
        if self.execution_boundary in {"external_write", "protected_foundation"} and self.authorization_mode not in {
            "explicit_confirmation", "prohibited",
        }:
            raise ValueError("external writes and protected foundations require confirmation or prohibition")


@dataclass(frozen=True)
class PrivacyLabel:
    """Transparent, rider-visible classification; never a hidden Archive."""

    classification: str = "standard"
    reason: str = "Not classified as unusually private."
    assigned_by: str = "system"
    rider_visible: bool = True
    revisable: bool = True

    def __post_init__(self):
        if self.classification not in PRIVACY_CLASSES:
            raise ValueError("unknown privacy classification")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("privacy classification reason is required")
        if not isinstance(self.assigned_by, str) or not self.assigned_by.strip():
            raise ValueError("privacy classification actor is required")
        if not self.rider_visible or not self.revisable:
            raise ValueError("privacy classification must remain visible and revisable")


@dataclass(frozen=True)
class MediaEvidenceReference:
    """Trace a derived statement to a source and format-native location."""

    source_id: str
    modality: str
    locator_kind: str
    locator: dict
    derivation: str
    trust: str = "untrusted_user_content"
    privacy: PrivacyLabel = PrivacyLabel()

    def __post_init__(self):
        if not isinstance(self.source_id, str) or not _IDENTIFIER.fullmatch(self.source_id):
            raise ValueError("media evidence source_id is invalid")
        if self.modality not in MODALITIES - {"text"}:
            raise ValueError("media evidence modality is invalid")
        if self.locator_kind not in LOCATOR_KINDS:
            raise ValueError("media evidence locator kind is invalid")
        if not isinstance(self.locator, dict) or not self.locator:
            raise ValueError("media evidence requires a source locator")
        if not isinstance(self.derivation, str) or not self.derivation.strip():
            raise ValueError("media evidence derivation is required")
        if self.trust not in {"untrusted_user_content", "untrusted_external_content"}:
            raise ValueError("media content cannot grant instruction authority")

    def as_dict(self):
        return {
            "source_id": self.source_id,
            "modality": self.modality,
            "locator_kind": self.locator_kind,
            "locator": self.locator,
            "derivation": self.derivation,
            "trust": self.trust,
            "privacy": {
                "classification": self.privacy.classification,
                "reason": self.privacy.reason,
                "assigned_by": self.privacy.assigned_by,
                "rider_visible": self.privacy.rider_visible,
                "revisable": self.privacy.revisable,
            },
        }


def ensure_delegated_permissions(parent_permissions, requested_permissions):
    """Self-created workflows can narrow existing authority, never expand it."""
    parent, requested = set(parent_permissions), set(requested_permissions)
    escalation = requested - parent
    if escalation:
        raise PermissionError(
            "workflow cannot grant additional permissions: " + ", ".join(sorted(escalation))
        )
    return tuple(permission for permission in requested_permissions if permission in parent)
