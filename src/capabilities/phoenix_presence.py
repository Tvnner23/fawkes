"""Instance-scoped Phoenix Presence profile and renderer-neutral capability.

Presence is presentation state belonging to one Phoenix.  It is not Memory,
personality, authentication, or the renderer itself.  Clients may safely ignore
this contract or fall back when its declared asset cannot be rendered.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import struct
import uuid

from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract


ROOT = Path(__file__).resolve().parent.parent.parent
PRESENCE_ROOT = ROOT / "database" / "presentation"
PROFILE_SCHEMA_VERSION = 2
RIG_CONTRACT_VERSION = "presence-rig-1"
WORKSHOP_STATIC_CONTRACT_VERSION = "presence-workshop-static-1"
ASSET_CONTRACT_VERSIONS = {RIG_CONTRACT_VERSION, WORKSHOP_STATIC_CONTRACT_VERSION}
REQUIRED_BONES = ("phoenix_root", "body", "head", "wing_left", "wing_right", "tail")
MATERIAL_CHANNELS = (
    "plumage_primary", "plumage_secondary", "expression_crest",
    "expression_feather_tips", "flame_accent",
)
CHANNEL_ROLES = {
    "plumage_primary": "stable_rider_primary",
    "plumage_secondary": "stable_phoenix_secondary",
    "expression_crest": "transient_expression_crest",
    "expression_feather_tips": "transient_expression_feather_tips",
    "flame_accent": "separable_flame_effect",
}
SEMANTIC_STATES = ("idle", "invoked", "thinking", "responding", "task_complete", "unavailable")
MOTION_POLICIES = {"off", "subtle", "expressive"}
ASSET_STATUSES = {"development_asset", "canonical_asset"}
MAX_GLB_BYTES = 8 * 1024 * 1024
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
INVOCATION = re.compile(r"^[^\x00-\x1f\x7f]{1,80}$")
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


PRESENCE_DEFINITION = CapabilityDefinition(
    name="presentation.phoenix_presence", version="1.0",
    display_name="Phoenix Presence",
    description="Manifest the current Phoenix through an instance-bound accessible visual presence.",
    effect="client_presentation",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("image",)),
    authority=AuthorityContract(actions=("read", "create"), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="instance_scoped_presentation_preferences_no_memory_or_personality",
    features=("instance_bound_profile", "three_dimensional_manifestation", "semantic_expression_states", "accessible_invocation", "motion_policy", "static_fallback", "renderer_health", "invocation_phrase"),
    appropriate_use=("make the current Phoenix visibly present", "communicate bounded task state nonverbally", "provide an accessible route into Chat"),
    inappropriate_use=("authenticate a rider", "authorize an action", "infer permanent personality", "claim biological emotion", "execute asset metadata"),
    limitations=("3D requires a compatible local GLB and WebGL2 client", "physical visibility requires rider/device verification", "invocation phrase is not authentication"),
    platform_support=("server_contract", "web", "desktop_web", "mobile_web", "future_native_clients"),
    presentation_options=("three_dimensional", "static_fallback", "off"),
    dependencies=("registered Phoenix instance", "compatible client", "versioned embodiment profile", "local validated asset for 3D"),
    provenance_requirements=("Phoenix instance id", "profile revision", "asset id and digest", "semantic occurrence id"),
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _require_id(value, name):
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise ValueError(f"valid {name} is required")
    return value


def presence_asset_root(instance_id, *, root=None):
    return (Path(root) if root else PRESENCE_ROOT) / _require_id(instance_id, "phoenix_instance_id") / "assets"


def normalize_invocation_phrase(value):
    if not isinstance(value, str):
        raise ValueError("invocation phrase must be text")
    value = " ".join(value.strip().split())
    if not INVOCATION.fullmatch(value):
        raise ValueError("invocation phrase must contain 1 to 80 printable characters")
    return value


def default_presence_profile(instance_id, *, phoenix_name="Fawkes"):
    _require_id(instance_id, "phoenix_instance_id")
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "record_type": "phoenix_embodiment_profile",
        "profile_id": f"presence:{instance_id}",
        "phoenix_instance_id": instance_id,
        "profile_revision": 1,
        "canonical_archetype_id": "phoenix.v1",
        "archetype_compatibility_version": 1,
        "asset": None,
        "rig": {"contract_version": RIG_CONTRACT_VERSION,
                "required_actions": list(SEMANTIC_STATES[:-1]),
                "required_bones": list(REQUIRED_BONES),
                "material_channels": list(MATERIAL_CHANNELS),
                "optional_morph_channels": []},
        # Palette is presentation state, not identity. Each named material may
        # be driven independently without changing the Phoenix or the asset.
        "palette": {"rider_base": "#d86e3c", "channels": {
            "plumage_primary": {"role": "stable_rider_primary", "base": "#d86e3c", "emissive": "#1a0500", "emissive_intensity": 0.12},
            "plumage_secondary": {"role": "stable_phoenix_secondary", "base": "#f2b35f", "emissive": "#2a0d00", "emissive_intensity": 0.08},
            "expression_crest": {"role": "transient_expression_crest", "base": "#f2b35f", "emissive": "#2a0d00", "emissive_intensity": 0.08},
            "expression_feather_tips": {"role": "transient_expression_feather_tips", "base": "#f2b35f", "emissive": "#2a0d00", "emissive_intensity": 0.08},
            "flame_accent": {"role": "separable_flame_effect", "base": "#ffd27a", "emissive": "#ff6a00", "emissive_intensity": 1.0},
        }},
        "presentation_policy": {"enabled": True, "motion": "subtle",
                                "reduced_motion": False,
                                "invocation_phrase": f"Hey {phoenix_name}"},
        "fallback": {"kind": "css_phoenix_mark", "accessible_name": f"{phoenix_name} is present",
                     "message": "Fawkes's 3D embodiment asset is not installed yet."},
        "provenance": {"created_by": "phoenix_runtime_bootstrap", "authority": "rider_configurable_presentation",
                       "prior_revision": None, "created_at": _now(), "updated_at": _now()},
    }


def upgrade_presence_profile(profile):
    """Upgrade the sole pre-asset Presence schema with explicit provenance."""
    if not isinstance(profile, dict) or profile.get("schema_version") != 1:
        return profile
    channels = profile.get("palette", {}).get("channels", {})
    legacy = {"plumage_primary", "plumage_secondary", "flame_accent"}
    if set(channels) != legacy or profile.get("asset") is not None:
        raise ValueError("Presence schema 1 cannot be safely upgraded automatically")
    upgraded = json.loads(json.dumps(profile))
    secondary = dict(upgraded["palette"]["channels"]["plumage_secondary"])
    upgraded["palette"]["channels"]["expression_crest"] = {
        **secondary, "role": CHANNEL_ROLES["expression_crest"],
    }
    upgraded["palette"]["channels"]["expression_feather_tips"] = {
        **secondary, "role": CHANNEL_ROLES["expression_feather_tips"],
    }
    for name, role in CHANNEL_ROLES.items():
        upgraded["palette"]["channels"][name]["role"] = role
    upgraded["rig"]["material_channels"] = list(MATERIAL_CHANNELS)
    prior_revision = upgraded["profile_revision"]
    upgraded["schema_version"] = PROFILE_SCHEMA_VERSION
    upgraded["profile_revision"] += 1
    upgraded["provenance"] = {
        **upgraded.get("provenance", {}), "updated_at": _now(),
        "prior_revision": prior_revision, "prior_schema_version": 1,
        "last_changed_by": "system:presence_schema_migration",
        "change_kind": "schema_upgrade_1_to_2_material_segmentation",
    }
    return upgraded


def validate_asset(asset, *, asset_root=None):
    if asset is None:
        return None
    if not isinstance(asset, dict):
        raise ValueError("presence asset must be an object or null")
    _require_id(asset.get("asset_id"), "asset_id")
    if asset.get("status") not in ASSET_STATUSES:
        raise ValueError("asset status must be development_asset or canonical_asset")
    if not isinstance(asset.get("revision"), int) or asset["revision"] < 1:
        raise ValueError("asset revision must be a positive integer")
    filename = asset.get("filename")
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.lower().endswith(".glb"):
        raise ValueError("presence asset must be a local GLB filename")
    digest = asset.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("presence asset sha256 is required")
    if asset.get("rig_contract_version") not in ASSET_CONTRACT_VERSIONS:
        raise ValueError("presence asset rig contract is incompatible")
    if not isinstance(asset.get("rights"), dict) or not asset["rights"].get("license"):
        raise ValueError("presence asset rights and license provenance are required")
    path = Path(asset_root) / filename if asset_root is not None else None
    if path is not None and path.is_file():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError("presence asset digest mismatch")
    return dict(asset)


def inspect_presence_glb(payload, *, contract_version=RIG_CONTRACT_VERSION):
    """Validate the bounded declarative portions of a GLB without rendering it."""
    if contract_version not in ASSET_CONTRACT_VERSIONS:
        raise ValueError("unsupported Presence asset contract")
    if not isinstance(payload, bytes) or len(payload) < 20 or len(payload) > MAX_GLB_BYTES:
        raise ValueError("Presence GLB must be between 20 bytes and 8 MiB")
    magic, version, declared_length = struct.unpack_from("<4sII", payload, 0)
    if magic != b"glTF" or version != 2 or declared_length != len(payload):
        raise ValueError("Presence asset must be a structurally valid glTF 2.0 binary")
    offset = 12; document = None
    while offset + 8 <= len(payload):
        length, kind = struct.unpack_from("<II", payload, offset); offset += 8
        if offset + length > len(payload): raise ValueError("GLB chunk exceeds declared length")
        chunk = payload[offset:offset + length]; offset += length
        if kind == 0x4E4F534A and document is None:
            try: document = json.loads(chunk.rstrip(b" \x00").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise ValueError("GLB JSON chunk is invalid") from exc
    if offset != len(payload) or not isinstance(document, dict) or str(document.get("asset", {}).get("version")) != "2.0":
        raise ValueError("GLB requires one valid glTF 2.0 JSON document")
    if not document.get("scenes") or not document.get("meshes"):
        raise ValueError("Presence GLB requires a renderable scene and mesh")
    external_uris = []
    for collection in ("buffers", "images"):
        for item in document.get(collection, ()):
            if isinstance(item, dict) and isinstance(item.get("uri"), str) and not item["uri"].startswith("data:"):
                external_uris.append(item["uri"])
    if external_uris:
        raise ValueError("Presence GLB must not depend on external resources")
    animations = {item.get("name") for item in document.get("animations", ()) if isinstance(item, dict)}
    required = {f"presence.{name}" for name in SEMANTIC_STATES[:-1]}
    materials = {item.get("name") for item in document.get("materials", ()) if isinstance(item, dict)}
    required_materials = set(MATERIAL_CHANNELS)
    node_names = {item.get("name") for item in document.get("nodes", ()) if isinstance(item, dict)}
    if contract_version == RIG_CONTRACT_VERSION:
        missing = sorted(required - animations)
        if missing: raise ValueError("GLB lacks required named animations: " + ", ".join(missing))
        missing_materials = sorted(required_materials - materials)
        if missing_materials: raise ValueError("GLB lacks required material channels: " + ", ".join(missing_materials))
        missing_bones = sorted(set(REQUIRED_BONES) - node_names)
        if missing_bones or not document.get("skins"):
            raise ValueError("GLB lacks the required skinned semantic rig: " + ", ".join(missing_bones or ("skin",)))
    joint_union = {joint for skin in document.get("skins", ()) if isinstance(skin, dict)
                   for joint in skin.get("joints", ()) if isinstance(joint, int)}
    morph_target_count = sum(len(primitive.get("targets", ()))
        for mesh in document.get("meshes", ()) if isinstance(mesh, dict)
        for primitive in mesh.get("primitives", ()) if isinstance(primitive, dict))
    return {"format": "glTF 2.0 binary", "size_bytes": len(payload),
            "contract_version": contract_version,
            "mesh_count": len(document.get("meshes", ())),
            "material_count": len(document.get("materials", ())),
            "texture_count": len(document.get("textures", ())),
            "skin_count": len(document.get("skins", ())),
            "joint_union_count": len(joint_union),
            "animation_names": sorted(name for name in animations if isinstance(name, str)),
            "animations": sorted(required if contract_version == RIG_CONTRACT_VERSION else animations),
            "material_channels": sorted(required_materials & materials),
            "required_bones": [name for name in REQUIRED_BONES if name in node_names],
            "morph_target_count": morph_target_count,
            "external_resource_count": 0,
            "production_contract_complete": (required <= animations and required_materials <= materials
                                                and set(REQUIRED_BONES) <= node_names and bool(document.get("skins"))),
            "generator": str(document.get("asset", {}).get("generator", "unknown"))[:160]}


def validate_profile(profile, *, expected_instance_id=None, asset_root=None):
    if not isinstance(profile, dict) or profile.get("record_type") != "phoenix_embodiment_profile":
        raise ValueError("invalid Phoenix embodiment profile")
    instance_id = _require_id(profile.get("phoenix_instance_id"), "phoenix_instance_id")
    if expected_instance_id is not None and instance_id != expected_instance_id:
        raise PermissionError("Presence profile belongs to another Phoenix")
    if profile.get("profile_id") != f"presence:{instance_id}":
        raise ValueError("Presence profile identity does not match its Phoenix")
    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValueError("unsupported Presence profile schema")
    if not isinstance(profile.get("profile_revision"), int) or profile["profile_revision"] < 1:
        raise ValueError("invalid Presence profile revision")
    policy = profile.get("presentation_policy")
    if not isinstance(policy, dict) or not isinstance(policy.get("enabled"), bool):
        raise ValueError("Presence enabled policy is required")
    if policy.get("motion") not in MOTION_POLICIES or not isinstance(policy.get("reduced_motion"), bool):
        raise ValueError("invalid Presence motion policy")
    normalize_invocation_phrase(policy.get("invocation_phrase"))
    palette = profile.get("palette")
    channels = palette.get("channels") if isinstance(palette, dict) else None
    required_channels = MATERIAL_CHANNELS
    if (not isinstance(palette, dict) or not HEX_COLOR.fullmatch(str(palette.get("rider_base", "")))
            or not isinstance(channels, dict) or set(channels) != set(required_channels)):
        raise ValueError("Presence palette requires the renderer-neutral material channel contract")
    for name in required_channels:
        channel = channels.get(name)
        if (not isinstance(channel, dict)
                or channel.get("role") != CHANNEL_ROLES[name]
                or not HEX_COLOR.fullmatch(str(channel.get("base", "")))
                or not HEX_COLOR.fullmatch(str(channel.get("emissive", "")))
                or not isinstance(channel.get("emissive_intensity"), (int, float))
                or not 0 <= channel["emissive_intensity"] <= 8):
            raise ValueError(f"Presence palette channel {name} is invalid")
    rig = profile.get("rig")
    if not isinstance(rig, dict) or rig.get("contract_version") != RIG_CONTRACT_VERSION:
        raise ValueError("invalid Presence rig contract")
    if tuple(rig.get("required_actions", ())) != SEMANTIC_STATES[:-1]:
        raise ValueError("Presence semantic action contract is incomplete")
    if tuple(rig.get("required_bones", ())) != REQUIRED_BONES:
        raise ValueError("Presence semantic bone contract is incomplete")
    fallback = profile.get("fallback")
    if not isinstance(fallback, dict) or not fallback.get("accessible_name"):
        raise ValueError("accessible Presence fallback is required")
    validate_asset(profile.get("asset"), asset_root=asset_root or presence_asset_root(instance_id))
    forbidden = {"memory", "personality", "relationship_memory", "traits"}.intersection(profile)
    if forbidden:
        raise ValueError("Memory and personality do not belong in Presence profiles")
    return dict(profile)


def presence_health(profile, *, asset_root=None):
    try:
        validate_profile(profile, expected_instance_id=profile.get("phoenix_instance_id"), asset_root=asset_root)
    except Exception as exc:
        return {"status": "failed", "reason": "Presence profile validation failed", "failure_code": type(exc).__name__}
    if not profile["presentation_policy"]["enabled"]:
        return {"status": "disabled", "reason": "Presence is disabled by the rider", "failure_code": None}
    asset = profile.get("asset")
    if asset is None:
        return {"status": "unavailable", "reason": "No rider-approved or development Phoenix GLB is installed", "failure_code": "asset_missing"}
    root = Path(asset_root) if asset_root else presence_asset_root(profile["phoenix_instance_id"])
    if not (root / asset["filename"]).is_file():
        return {"status": "unavailable", "reason": "The configured Phoenix GLB is not installed", "failure_code": "asset_missing"}
    return {"status": "live", "reason": f"Validated local {asset['status']} revision {asset['revision']} is installed", "failure_code": None}


class PresenceProfileStore:
    def __init__(self, instance_id, *, root=None, asset_root=None, phoenix_name="Fawkes"):
        self.instance_id = _require_id(instance_id, "phoenix_instance_id")
        self.root = Path(root) if root else PRESENCE_ROOT
        self.asset_root = Path(asset_root) if asset_root else presence_asset_root(self.instance_id, root=self.root)
        self.phoenix_name = phoenix_name
        self.path = self.root / instance_id / "profile.json"

    def load(self):
        if not self.path.exists():
            return default_presence_profile(self.instance_id, phoenix_name=self.phoenix_name)
        try:
            profile = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Presence profile is unreadable") from exc
        profile = upgrade_presence_profile(profile)
        return validate_profile(profile, expected_instance_id=self.instance_id, asset_root=self.asset_root)

    def _write(self, profile):
        validate_profile(profile, expected_instance_id=self.instance_id, asset_root=self.asset_root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return profile

    def ensure(self):
        """Persist genesis presentation state without implying continuity genesis."""
        if self.path.exists():
            stored_schema = json.loads(self.path.read_text(encoding="utf-8")).get("schema_version")
            profile = self.load()
            return self._write(profile) if stored_schema != PROFILE_SCHEMA_VERSION else profile
        return self._write(default_presence_profile(self.instance_id, phoenix_name=self.phoenix_name))

    def update_preferences(self, changes, *, actor_principal_id):
        _require_id(actor_principal_id, "actor_principal_id")
        if not isinstance(changes, dict):
            raise ValueError("Presence preferences must be an object")
        allowed = {"enabled", "motion", "reduced_motion", "invocation_phrase"}
        if set(changes) - allowed:
            raise ValueError("unknown or protected Presence preference")
        current = self.load()
        policy = dict(current["presentation_policy"])
        if "enabled" in changes:
            if not isinstance(changes["enabled"], bool): raise ValueError("enabled must be true or false")
            policy["enabled"] = changes["enabled"]
        if "motion" in changes:
            if changes["motion"] not in MOTION_POLICIES: raise ValueError("invalid motion policy")
            policy["motion"] = changes["motion"]
        if "reduced_motion" in changes:
            if not isinstance(changes["reduced_motion"], bool): raise ValueError("reduced_motion must be true or false")
            policy["reduced_motion"] = changes["reduced_motion"]
        if "invocation_phrase" in changes:
            policy["invocation_phrase"] = normalize_invocation_phrase(changes["invocation_phrase"])
        prior_revision = current["profile_revision"]
        current["profile_revision"] += 1
        current["presentation_policy"] = policy
        current["provenance"] = {**current["provenance"], "updated_at": _now(),
                                 "prior_revision": prior_revision,
                                 "last_changed_by": actor_principal_id}
        validate_profile(current, expected_instance_id=self.instance_id, asset_root=self.asset_root)
        return self._write(current)

    def install_development_asset(self, source_path, *, asset_id, revision, rights,
                                  actor_principal_id, source_reference=None,
                                  contract_version=RIG_CONTRACT_VERSION):
        """Developer-only registration; intentionally not exposed through Chat/API."""
        _require_id(actor_principal_id, "actor_principal_id")
        _require_id(asset_id, "asset_id")
        if not isinstance(revision, int) or revision < 1: raise ValueError("asset revision must be positive")
        if not isinstance(rights, dict) or not rights.get("license"): raise ValueError("asset license provenance is required")
        source = Path(source_path); payload = source.read_bytes()
        inspection = inspect_presence_glb(payload, contract_version=contract_version)
        digest = hashlib.sha256(payload).hexdigest()
        filename = f"{asset_id.replace(':', '-')}-r{revision}-{digest[:12]}.glb"
        self.asset_root.mkdir(parents=True, exist_ok=True); target = self.asset_root / filename
        if target.exists() and target.read_bytes() != payload: raise ValueError("asset destination collision")
        if not target.exists():
            temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            temporary.write_bytes(payload); temporary.replace(target)
        current = self.load(); prior_revision = current["profile_revision"]
        current["asset"] = {"asset_id": asset_id, "revision": revision,
            "status": "development_asset", "filename": filename, "sha256": digest,
            "rig_contract_version": contract_version, "rights": dict(rights),
            "source_reference": source_reference, "inspection": inspection}
        current["profile_revision"] += 1
        current["provenance"] = {**current["provenance"], "updated_at": _now(),
            "prior_revision": prior_revision, "last_changed_by": actor_principal_id,
            "change_kind": ("workshop_static_asset_registered"
                            if contract_version == WORKSHOP_STATIC_CONTRACT_VERSION
                            else "development_asset_registered")}
        validate_profile(current, expected_instance_id=self.instance_id, asset_root=self.asset_root)
        return self._write(current)

    def public(self):
        profile = self.ensure()
        health = presence_health(profile, asset_root=self.asset_root)
        asset = profile.get("asset")
        return {**profile, "asset": ({**asset, "url": f"/assets/presence/{asset['filename']}"} if asset else None),
                "health": health, "invocation_is_authentication": False}
