"""Small, auditable execution boundary for Phoenix capabilities.

Capabilities may produce evidence and artifacts. They do not gain access to
Memory, personality, Development, or the canonical Archive merely by being
registered here.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import uuid

from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract


ROOT = Path(__file__).resolve().parent.parent.parent
STATE_ROOT = Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
RECEIPTS_DIR = STATE_ROOT / "database" / "capability_receipts"
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class CapabilityDefinition:
    name: str
    version: str
    description: str
    permissions: tuple[str, ...] = ()
    effect: str = "read_only"
    modalities: MultimodalCapabilityContract = MultimodalCapabilityContract()
    authority: AuthorityContract = AuthorityContract()
    privacy_handling: str = "standard_rider_visible"
    features: tuple[str, ...] = ()
    display_name: str = ""
    appropriate_use: tuple[str, ...] = ()
    inappropriate_use: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    platform_support: tuple[str, ...] = ("server", "web", "future_native_clients")
    presentation_options: tuple[str, ...] = ("text",)
    dependencies: tuple[str, ...] = ()
    provenance_requirements: tuple[str, ...] = ()

    def __post_init__(self):
        for field in ("name", "version", "description", "effect"):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise ValueError(f"capability {field} is required")
        if not SAFE_IDENTIFIER.fullmatch(self.name):
            raise ValueError("capability name contains unsafe characters")
        if any(not isinstance(item, str) or not item.strip() for item in self.permissions):
            raise ValueError("capability permissions must be non-empty strings")
        if not isinstance(self.modalities, MultimodalCapabilityContract):
            raise TypeError("capability modalities contract is required")
        if not isinstance(self.authority, AuthorityContract):
            raise TypeError("capability authority contract is required")
        if not isinstance(self.privacy_handling, str) or not self.privacy_handling.strip():
            raise ValueError("capability privacy handling is required")
        if any(not isinstance(item, str) or not item.strip() for item in self.features):
            raise ValueError("capability features must be non-empty strings")
        for field in (
            "appropriate_use", "inappropriate_use", "limitations", "platform_support",
            "presentation_options", "dependencies", "provenance_requirements",
        ):
            if any(not isinstance(item, str) or not item.strip() for item in getattr(self, field)):
                raise ValueError(f"capability {field} must contain non-empty strings")

    def public_manifest(self):
        """Describe usable scope without exposing providers, secrets, or internals."""
        return {
            "name": self.name,
            "display_name": self.display_name or self.name.replace(".", " ").title(),
            "description": self.description,
            "input_modalities": list(self.modalities.input_modalities),
            "output_modalities": list(self.modalities.output_modalities),
            "authority_actions": list(self.authority.actions),
            "execution_boundary": self.authority.execution_boundary,
            "authorization_mode": self.authority.authorization_mode,
            "privacy_handling": self.privacy_handling,
            "features": list(self.features),
            "appropriate_use": list(self.appropriate_use),
            "inappropriate_use": list(self.inappropriate_use),
            "limitations": list(self.limitations),
            "platform_support": list(self.platform_support),
            "presentation_options": list(self.presentation_options),
            "dependencies": list(self.dependencies),
            "provenance_requirements": list(self.provenance_requirements),
        }


@dataclass(frozen=True)
class CapabilityRequest:
    instance_id: str
    capability: str
    arguments: dict
    requested_by: str = "rider"
    conversation_id: str | None = None
    request_message_id: str | None = None
    task_authorized: bool = False
    explicitly_confirmed: bool = False


class CapabilityRegistry:
    def __init__(self):
        self._entries = {}

    def register(self, definition, handler):
        if not isinstance(definition, CapabilityDefinition):
            raise TypeError("definition must be a CapabilityDefinition")
        if definition.name in self._entries:
            raise ValueError(f"capability already registered: {definition.name}")
        if not callable(handler):
            raise TypeError("capability handler must be callable")
        self._entries[definition.name] = (definition, handler)

    def resolve(self, name):
        try:
            return self._entries[name]
        except KeyError as exc:
            raise ValueError(f"unknown capability: {name}") from exc

    def definitions(self):
        return tuple(entry[0] for entry in self._entries.values())


class CapabilityAvailabilityCatalog:
    """Runtime truth for capability awareness; extension points are not live entries."""

    def __init__(self):
        self._entries = {}

    HEALTH_STATES = {
        "live", "partial", "degraded", "failed", "rate_limited",
        "permission_blocked", "disabled", "untested", "environmentally_unverifiable",
        "unavailable",
    }

    def advertise(self, definition, *, effects, availability="live", availability_reason="registered and configured"):
        if not isinstance(definition, CapabilityDefinition):
            raise TypeError("definition must be a CapabilityDefinition")
        if availability not in self.HEALTH_STATES:
            raise ValueError("unknown capability availability")
        self._entries[definition.name] = {
            "definition": definition, "effects": str(effects),
            "health": availability, "reason": str(availability_reason),
            "checked_at": datetime.now(timezone.utc).isoformat(), "failure_code": None,
        }

    def set_health(self, name, health, *, reason, failure_code=None):
        if health not in self.HEALTH_STATES:
            raise ValueError("unknown capability health")
        if name not in self._entries:
            raise ValueError("unknown capability")
        self._entries[name].update(
            health=health, reason=str(reason), failure_code=failure_code,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def manifests(self, *, acceptance_statuses=None):
        acceptance_statuses = acceptance_statuses or {}
        return tuple({
            **entry["definition"].public_manifest(),
            "availability": entry["health"], "availability_reason": entry["reason"],
            "health": {"status": entry["health"], "reason": entry["reason"],
                       "checked_at": entry["checked_at"], "failure_code": entry["failure_code"]},
            "acceptance_status": acceptance_statuses.get(entry["definition"].name, "not_tested"),
            "effects": entry["effects"],
        } for entry in self._entries.values())


def enforce_capability_authority(definition, request, *, granted_permissions=()):
    """One authority decision shared by direct and registry-backed capabilities."""
    missing = set(definition.permissions) - set(granted_permissions)
    if missing:
        raise PermissionError(
            "capability permission not granted: " + ", ".join(sorted(missing))
        )
    mode = definition.authority.authorization_mode
    if mode == "prohibited":
        raise PermissionError("capability is prohibited")
    if mode == "task_request" and not request.task_authorized:
        raise PermissionError("capability requires authorization by the rider's task")
    if mode == "explicit_confirmation" and not request.explicitly_confirmed:
        raise PermissionError("capability requires explicit rider confirmation")


def _write_once(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise ValueError("capability receipt already exists with different data")
        return existing
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)
    return payload


class CapabilityExecutor:
    """Execute an explicitly permitted capability and append an audit receipt."""

    def __init__(self, registry, *, receipt_dir=None):
        self.registry = registry
        self.receipt_dir = Path(receipt_dir) if receipt_dir else RECEIPTS_DIR

    def execute(self, request, *, granted_permissions=()):
        if not isinstance(request, CapabilityRequest):
            raise TypeError("request must be a CapabilityRequest")
        if not request.instance_id or not request.capability:
            raise ValueError("instance_id and capability are required")
        if not SAFE_IDENTIFIER.fullmatch(request.instance_id):
            raise ValueError("instance_id contains unsafe characters")
        if not isinstance(request.arguments, dict):
            raise ValueError("capability arguments must be an object")
        definition, handler = self.registry.resolve(request.capability)
        enforce_capability_authority(
            definition, request, granted_permissions=granted_permissions
        )

        invocation_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        argument_digest = hashlib.sha256(
            json.dumps(request.arguments, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        failure = None
        try:
            result = handler(request)
            if not isinstance(result, dict):
                raise TypeError("capability handler must return a dictionary")
            status = "completed"
            error_code = None
        except Exception as exc:
            failure = exc
            status = "failed"
            error_code = type(exc).__name__
            result = None

        receipt = {
            "schema_version": 1,
            "record_type": "capability_execution_receipt",
            "invocation_id": invocation_id,
            "instance_id": request.instance_id,
            "capability": definition.name,
            "capability_version": definition.version,
            "effect": definition.effect,
            "permissions": list(definition.permissions),
            "input_modalities": list(definition.modalities.input_modalities),
            "output_modalities": list(definition.modalities.output_modalities),
            "authority_actions": list(definition.authority.actions),
            "execution_boundary": definition.authority.execution_boundary,
            "authorization_mode": definition.authority.authorization_mode,
            "task_authorized": request.task_authorized,
            "explicitly_confirmed": request.explicitly_confirmed,
            "privacy_handling": definition.privacy_handling,
            "requested_by": request.requested_by,
            "conversation_id": request.conversation_id,
            "request_message_id": request.request_message_id,
            "argument_sha256": argument_digest,
            "status": status,
            "result_references": list((result or {}).get("result_references", ())),
            "error_code": error_code,
            "created_at": created_at,
        }
        _write_once(
            self.receipt_dir / request.instance_id / f"{invocation_id}.json", receipt
        )
        if status == "failed":
            raise RuntimeError("capability execution failed") from failure
        return {**result, "capability_receipt_id": invocation_id}
