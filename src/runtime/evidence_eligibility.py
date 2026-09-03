"""Versioned production policy for distinct evidence-use authorities.

Knowledge/storage access, private-context retrieval, provider transmission,
external disclosure, and cross-principal disclosure are independent decisions.
The policy is pure and records no evidence content.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
import re

from src.library.artifacts import PRIVACY_CLASSES, require_id
from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract


POLICY_VERSION = "production-evidence-eligibility-v1"
SOURCE_DISCLOSURE_POLICY_VERSION = "reviewer-source-evidence-v1"
SOURCE_DISCLOSURE_LIMIT = 256_000
_PROTECTED_ROOTS = {".git", "archive", "memory", "library", "conversations", "continuity",
    "database", "backups", "worker_exchange", "worker-exchange", "runtime-state",
    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
_PROTECTED_NAMES = {".env", ".env.local", ".env.production", "credentials.json",
    "secrets.json", "credentials", "tokens", "token", "private.key"}
_SECRET_RULES = (
    ("private_key_pem", re.compile(br"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("openai_token", re.compile(br"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(br"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("discord_webhook", re.compile(br"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]{20,}")),
)


def classify_reviewer_source_evidence(*, path, before, after, expected_before=None,
                                        expected_after=None, evidence_limit=SOURCE_DISCLOSURE_LIMIT):
    """Return a deterministic body-free disclosure decision for exact source bytes."""
    if not isinstance(path, str) or not path or "\\" in path:
        raise ValueError("normalized repository-relative path is required")
    relative = PurePosixPath(path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("source evidence path escapes the repository")
    if before is not None and not isinstance(before, bytes) or after is not None and not isinstance(after, bytes):
        raise TypeError("source evidence must be exact bytes or absence")
    states = {}
    for name, body, expected in (("before", before, expected_before), ("after", after, expected_after)):
        state = None if body is None else {"sha256": hashlib.sha256(body).hexdigest(), "byte_length": len(body)}
        if expected is not None and state != expected:
            raise ValueError(name + " evidence digest or length mismatch")
        states[name] = state
    rules=[]; result="eligible_source_evidence"; allowed=True
    lower={part.lower() for part in relative.parts}; name=relative.name.lower()
    if relative.parts[0].lower() in _PROTECTED_ROOTS or name in _PROTECTED_NAMES or name.startswith(".env") or name.endswith((".pem", ".p12", ".pfx", ".key", ".crt")):
        result="blocked_protected_path"; rules.append("protected_path"); allowed=False
    total=sum(len(body) for body in (before,after) if body is not None)
    if allowed and total > evidence_limit:
        result="blocked_size"; rules.append("bounded_exact_evidence"); allowed=False
    for body in (before,after):
        if body is None: continue
        if allowed and (b"\0" in body or _cannot_decode(body)):
            result="blocked_unsupported_content"; rules.append("ambiguous_binary"); allowed=False
        matches=[rule for rule,pattern in _SECRET_RULES if pattern.search(body)]
        if matches:
            result="blocked_high_confidence_secret"; rules.extend(matches); allowed=False
    policy_digest=_digest({"version":SOURCE_DISCLOSURE_POLICY_VERSION,"limit":evidence_limit,
        "protected_roots":sorted(_PROTECTED_ROOTS),"protected_names":sorted(_PROTECTED_NAMES),
        "secret_rules":[name for name,_ in _SECRET_RULES]})
    receipt={"schema_version":1,"record_type":"reviewer_source_evidence_eligibility",
        "classification":result,"disclosure_allowed":allowed,"path":relative.as_posix(),
        "before":states["before"],"after":states["after"],"applicable_rule_ids":sorted(set(rules)),
        "classifier_version":SOURCE_DISCLOSURE_POLICY_VERSION,"policy_sha256":policy_digest,
        "secret_assurance":"no_configured_high_confidence_secret_detected" if allowed else None,
        "source_content_retained":False,"creates_authority":False}
    receipt["record_sha256"]=_digest(receipt)
    return receipt


def _cannot_decode(body):
    try: body.decode("utf-8")
    except UnicodeDecodeError: return True
    return False
PRIVATE_CONTEXT = "authenticated_primary_rider_private_chat"
PROVIDER_MODES = {"local_only", "configured_external_provider"}
LEGACY_PRIVATE = "legacy_private_unclassified"

EVIDENCE_ELIGIBILITY_DEFINITION = CapabilityDefinition(
    name="retrieval.evidence_eligibility", version="1.0",
    display_name="Production Evidence Eligibility Policy",
    description="Decide private-context retrieval and separate provider, external, and cross-principal authority without changing evidence.",
    effect="read_only_policy_decision",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read",), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="metadata_only_fail_closed_no_evidence_content_in_decisions",
    features=("separate_use_authorities", "sensitive_relevance_gate", "restricted_explicit_authorization", "provider_transmission_gate", "stable_exclusion_reasons"),
    appropriate_use=("evaluate evidence before automatic private-context inclusion", "enforce provider transmission decisions"),
    inappropriate_use=("downgrade privacy", "grant external or cross-principal disclosure implicitly", "activate inherited-history retrieval"),
    limitations=("ordinary Chat planner integration remains disabled until production adapters enforce eligibility before ranking/provider processing", "provider gateway enforcement applies when an eligibility decision is supplied; legacy call sites are not reclassified by inference"),
    platform_support=("server", "provider_neutral", "platform_independent"),
    presentation_options=("text",),
    dependencies=("explicit Phoenix ownership", "owner principal", "privacy classification", "valid provenance", "capability authorization"),
    provenance_requirements=("evidence identity", "source domain", "authority class", "privacy classification", "original evidence reference digest", "policy version"),
)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class EvidenceUseContext:
    instance_id: str
    rider_principal_id: str
    capability_id: str
    context_kind: str = PRIVATE_CONTEXT
    capability_authorized: bool = False
    provider_mode: str = "local_only"
    provider_authorized: bool = False
    sensitive_request_categories: tuple[str, ...] = ()
    grants: tuple[str, ...] = ()
    external_recipient_id: str | None = None
    target_instance_id: str | None = None
    target_rider_principal_id: str | None = None

    def __post_init__(self):
        for value, name in ((self.instance_id, "instance_id"),
                            (self.rider_principal_id, "rider_principal_id"),
                            (self.capability_id, "capability_id")):
            require_id(value, name)
        if self.context_kind != PRIVATE_CONTEXT:
            raise ValueError("unsupported evidence-use context")
        if self.provider_mode not in PROVIDER_MODES:
            raise ValueError("invalid provider mode")


class ProductionEvidenceEligibilityPolicy:
    version = POLICY_VERSION

    def evaluate(self, evidence, context):
        if not isinstance(context, EvidenceUseContext):
            raise TypeError("EvidenceUseContext is required")
        base = self._metadata(evidence, context)
        if base["failure"]:
            return self._decision(base, context, automatic=False,
                                  automatic_reason=base["failure"], provider=False,
                                  provider_reason=base["failure"])

        privacy = base["privacy_classification"]
        evidence_id = base["evidence_id"]
        grants = frozenset(context.grants)
        automatic, automatic_reason = self._automatic(
            privacy, base, context, grants
        )
        provider, provider_reason = self._provider(
            privacy, evidence_id, context, grants, automatic
        )
        # Context selection that requires an external inference provider must
        # fail closed when transmission is denied.
        eligible = automatic and (
            context.provider_mode == "local_only" or provider
        )
        if automatic and not eligible:
            automatic_reason = "provider_transmission_denied"

        external_grant = f"external.disclose:{evidence_id}" in grants
        external = bool(context.external_recipient_id and external_grant)
        cross_target = (
            context.target_instance_id not in {None, context.instance_id}
            or context.target_rider_principal_id not in {None, context.rider_principal_id}
        )
        cross_grant = f"cross_principal.disclose:{evidence_id}" in grants
        cross = bool(cross_target and cross_grant)
        result = self._decision(base, context, automatic=eligible,
            automatic_reason=automatic_reason, provider=provider,
            provider_reason=provider_reason, external=external,
            external_reason=("explicit_evidence_disclosure_grant" if external
                             else "external_disclosure_not_authorized"),
            cross=cross, cross_reason=("explicit_cross_principal_grant" if cross
                                       else "cross_principal_disclosure_not_authorized"))
        return result

    def _metadata(self, evidence, context):
        failure = None
        if not isinstance(evidence, dict):
            evidence = {}; failure = "provenance_invalid"
        instance_id = evidence.get("instance_id")
        evidence_id = evidence.get("evidence_id")
        domain = evidence.get("domain")
        authority = evidence.get("authority_class")
        owner = evidence.get("owner_principal_id")
        explicit_privacy = evidence.get("privacy_classification")
        compatibility = evidence.get("legacy_compatibility")
        privacy = explicit_privacy
        compatibility_valid = (
            explicit_privacy is None and isinstance(compatibility, dict)
            and compatibility.get("compatibility_version") == "legacy-private-compatibility-v1"
            and compatibility.get("migration_status") == "compatibility_eligible"
            and compatibility.get("derived_compatibility_classification") == LEGACY_PRIVATE
            and compatibility.get("source_domain") == domain
            and compatibility.get("evidence_id") == evidence_id
            and compatibility.get("canonical_record_modified") is False
        )
        if compatibility_valid:
            privacy = LEGACY_PRIVATE
        reference = evidence.get("original_evidence_reference")
        if instance_id != context.instance_id:
            failure = "foreign_phoenix"
        elif owner != context.rider_principal_id:
            failure = "cross_principal_denied"
        elif privacy not in PRIVACY_CLASSES | {LEGACY_PRIVATE}:
            failure = "privacy_classification_invalid"
        elif not all(isinstance(value, str) and value.strip()
                     for value in (evidence_id, domain, authority)):
            failure = "provenance_invalid"
        elif not isinstance(reference, dict) or not reference:
            failure = "provenance_invalid"
        elif evidence.get("provenance_valid") is not True:
            failure = "provenance_invalid"
        elif set(evidence.get("eligibility_flags") or ()) & {
            "foreign", "shared", "restricted", "synthetic_inappropriate",
            "revoked", "quarantined", "suppressed", "unauthorized",
            "ownership_conflict",
        }:
            failure = "explicit_ineligible_state"
        elif evidence.get("automatic_use_enabled") is not True:
            failure = "automatic_use_disabled"
        elif not context.capability_authorized:
            failure = "capability_not_authorized"
        elif domain == "inherited_history":
            # No grant can activate this in policy v1.
            failure = "automatic_use_disabled"
        return {"failure": failure, "instance_id": instance_id,
                "evidence_id": evidence_id, "domain": domain,
                "authority_class": authority, "owner_principal_id": owner,
                "privacy_classification": privacy,
                "explicit_modern_classification": explicit_privacy is not None,
                "legacy_compatibility": compatibility if compatibility_valid else None,
                "sensitive_category": evidence.get("sensitive_category"),
                "original_evidence_reference": reference}

    def _automatic(self, privacy, base, context, grants):
        if privacy in {"standard", "potentially_private", LEGACY_PRIVATE}:
            return True, "eligible_authenticated_private_rider_context"
        if privacy == "highly_private":
            category = base["sensitive_category"]
            relevant = isinstance(category, str) and category in context.sensitive_request_categories
            authorized = ("evidence.highly_private.auto" in grants or
                          (isinstance(category, str) and
                           f"evidence.highly_private.auto:{category}" in grants))
            if relevant or authorized:
                return True, ("sensitive_category_explicitly_relevant" if relevant
                              else "explicit_sensitive_category_authorization")
            return False, "privacy_requires_explicit_authorization"
        if privacy == "restricted":
            if f"evidence.restricted.auto:{base['evidence_id']}" in grants:
                return True, "explicit_restricted_evidence_authorization"
            return False, "privacy_requires_explicit_authorization"
        return False, "privacy_classification_invalid"

    @staticmethod
    def _provider(privacy, evidence_id, context, grants, automatic):
        if context.provider_mode == "local_only":
            return True, "local_processing_no_provider_transmission"
        if not automatic or not context.provider_authorized:
            return False, "provider_transmission_denied"
        if privacy in {"standard", "potentially_private", LEGACY_PRIVATE}:
            return True, "authorized_private_context_provider_processing"
        if f"provider.transmit:{privacy}" in grants or f"provider.transmit:{evidence_id}" in grants:
            return True, "explicit_sensitive_provider_authorization"
        return False, "provider_transmission_denied"

    def _decision(self, base, context, *, automatic, automatic_reason,
                  provider, provider_reason, external=False,
                  external_reason="external_disclosure_not_authorized",
                  cross=False, cross_reason="cross_principal_disclosure_not_authorized"):
        reference_digest = (_digest(base["original_evidence_reference"])
                            if isinstance(base["original_evidence_reference"], dict) else None)
        return {"schema_version": 1, "record_type": "evidence_eligibility_decision",
                "policy_version": self.version, "instance_id": context.instance_id,
                "evidence_id": base["evidence_id"], "source_domain": base["domain"],
                "authority_class": base["authority_class"],
                "privacy_classification": base["privacy_classification"],
                "explicit_modern_classification": base.get("explicit_modern_classification", False),
                "legacy_compatibility": ({key: base["legacy_compatibility"].get(key) for key in (
                    "compatibility_version", "derived_compatibility_classification",
                    "original_metadata_status", "migration_status", "review_status",
                    "ownership_provenance_basis", "source_schema_version", "reason",
                    "canonical_record_modified")}
                    if isinstance(base.get("legacy_compatibility"), dict) else None),
                "original_evidence_reference_sha256": reference_digest,
                "storage_access": {"allowed": base["failure"] not in {
                    "foreign_phoenix", "cross_principal_denied", "provenance_invalid"},
                    "reason": base["failure"] or "owned_provenance_valid"},
                "automatic_private_context": {"allowed": automatic,
                                               "reason": automatic_reason},
                "provider_transmission": {"allowed": provider,
                                           "reason": provider_reason,
                                           "mode": context.provider_mode},
                "external_disclosure": {"allowed": external, "reason": external_reason},
                "cross_principal_disclosure": {"allowed": cross, "reason": cross_reason},
                "selected_for_context": automatic,
                "sensitive_content_logged": False}
