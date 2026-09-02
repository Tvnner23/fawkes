"""Semantic Phoenix event sounds and instance-scoped rider preferences.

The server publishes meaning, never playback instructions. Each client decides
whether it can play the rider-approved asset after applying these preferences.
Voice/TTS is intentionally outside this contract.
"""

from dataclasses import dataclass
from pathlib import Path
import json
import uuid

from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract


ROOT = Path(__file__).resolve().parent.parent.parent
PREFERENCES_ROOT = ROOT / "database" / "preferences"
ASSET_ROOT = ROOT / "src" / "app" / "static" / "assets" / "sounds"


@dataclass(frozen=True)
class SoundEvent:
    event_id: str
    label: str
    approved: bool
    asset_filename: str | None = None
    asset_identity: str | None = None
    default_enabled: bool = True

    def public(self):
        available = bool(self.approved and self.asset_filename and (ASSET_ROOT / self.asset_filename).is_file())
        return {
            "event_id": self.event_id, "label": self.label,
            "approved": self.approved, "available": available,
            "asset_identity": self.asset_identity,
            "asset_url": f"/assets/sounds/{self.asset_filename}" if available else None,
            "default_enabled": self.default_enabled,
        }


# Filenames are stable integration slots, not substitutes. Playback remains
# unavailable until the exact rider-approved files are placed at these paths.
SOUND_EVENTS = (
    SoundEvent("message.sent", "Message sent", True, "message-sent-clean-premium.wav", "Clean Premium 01"),
    SoundEvent("message.received", "Message received", True, "message-received-matching-soft.wav", "Matching Soft 02"),
    SoundEvent("ui.button_clicked", "Button click", True, "button-click-soft-futuristic.wav", "Soft Futuristic 03"),
    SoundEvent("task.research_completed", "Task / research complete", True, "task-complete-phoenix-signature.wav", "Phoenix Signature 04"),
    SoundEvent("thinking.started.male", "Thinking — male", False, default_enabled=False),
    SoundEvent("thinking.started.female", "Thinking — female", False, default_enabled=False),
    SoundEvent("notification.important", "Important notification", False, default_enabled=False),
    SoundEvent("notification.error", "Error", False, default_enabled=False),
)
EVENTS_BY_ID = {item.event_id: item for item in SOUND_EVENTS}

EVENT_SOUND_DEFINITION = CapabilityDefinition(
    name="presentation.event_sounds", version="1.0",
    display_name="Fawkes event sounds",
    description="Present semantic Phoenix events using rider-approved optional sounds.",
    effect="client_presentation",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("audio",)),
    authority=AuthorityContract(actions=("read", "create"), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="instance_scoped_preferences_no_personal_content",
    features=("semantic_events", "master_control", "event_controls", "volume", "duplicate_suppression"),
    appropriate_use=("confirm an accepted message", "announce a displayed response", "announce completed research", "appropriate rider UI interaction"),
    inappropriate_use=("internal retries or polling", "background rendering updates", "voice or speech output", "an event without an approved available asset"),
    limitations=("browser playback requires rider interaction", "physical audibility requires rider/device verification", "missing approved assets disable playback"),
    platform_support=("server_contract", "web", "desktop_web", "future_ios", "future_android"),
    presentation_options=("audio", "silent"),
    dependencies=("semantic client event", "rider preference", "rider-approved asset", "client audio support"),
    provenance_requirements=("semantic event id", "client-generated occurrence id"),
)


def default_preferences(instance_id=None):
    return {
        "schema_version": 2, "instance_id": instance_id,
        "master_enabled": True, "volume": 0.65,
        "events": {item.event_id: item.default_enabled for item in SOUND_EVENTS},
    }


class SoundPreferenceStore:
    def __init__(self, instance_id, *, root=None):
        if not isinstance(instance_id, str) or not instance_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in instance_id):
            raise ValueError("valid instance_id is required")
        self.path = (Path(root) if root else PREFERENCES_ROOT) / instance_id / "event_sounds.json"

    def load(self):
        defaults = default_preferences(self.path.parent.name)
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return defaults
        if not isinstance(stored, dict):
            return defaults
        events = stored.get("events") if isinstance(stored.get("events"), dict) else {}
        return {
            **defaults,
            "master_enabled": stored.get("master_enabled") if isinstance(stored.get("master_enabled"), bool) else defaults["master_enabled"],
            "volume": stored.get("volume") if isinstance(stored.get("volume"), (int, float)) and not isinstance(stored.get("volume"), bool) and 0 <= stored["volume"] <= 1 else defaults["volume"],
            "events": {key: events.get(key) if isinstance(events.get(key), bool) else value for key, value in defaults["events"].items()},
        }

    def update(self, changes):
        if not isinstance(changes, dict):
            raise ValueError("sound preferences must be an object")
        current = self.load()
        if "master_enabled" in changes:
            if not isinstance(changes["master_enabled"], bool):
                raise ValueError("master_enabled must be true or false")
            current["master_enabled"] = changes["master_enabled"]
        if "volume" in changes:
            value = changes["volume"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError("volume must be between 0 and 1")
            current["volume"] = float(value)
        if "events" in changes:
            if not isinstance(changes["events"], dict):
                raise ValueError("events must be an object")
            for event_id, enabled in changes["events"].items():
                if event_id not in EVENTS_BY_ID or not isinstance(enabled, bool):
                    raise ValueError("unknown sound event or invalid setting")
                current["events"][event_id] = enabled
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return current


def public_sound_settings(instance_id, *, root=None):
    preferences = SoundPreferenceStore(instance_id, root=root).load()
    return {"preferences": preferences, "events": [item.public() for item in SOUND_EVENTS],
            "voice_controls": "separate_not_implemented"}
