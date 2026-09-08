"""Provider-neutral Phase 7 retrieval planning contracts.

The planner coordinates read-only evidence adapters. It never turns federation
into shared authority, and it owns no canonical evidence or derived index.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
import json
import re

from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract
from src.library.artifacts import require_id


UNIFIED_RETRIEVAL_PLANNER_DEFINITION = CapabilityDefinition(
    name="retrieval.plan", version="1.0",
    display_name="Unified Retrieval Planner Foundation",
    description="Plan bounded retrieval across distinct evidence authorities without combining their truth or storage.",
    effect="read_only_derived_retrieval_plan",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read",), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="eligibility_before_ranking_instance_scoped_evidence",
    features=("versioned_domain_adapters", "pre_ranking_eligibility", "deterministic_budgeting",
              "explicit_exclusions", "projection_provenance", "replay_observability"),
    appropriate_use=("build an inspectable retrieval plan", "compare bounded provider-neutral retrieval policies"),
    inappropriate_use=("treat all domains as one truth store", "automatically retrieve inherited history before qualification", "resolve contradictions or classify identity"),
    limitations=("served planner Chat is default with explicit legacy rollback", "production ranking is local unless a separately authorized semantic ranker is configured", "character budgets are conservative approximations, not exact model tokens", "complete candidate instrumentation depends on each adapter"),
    platform_support=("server", "provider_neutral", "platform_independent"),
    presentation_options=("text",),
    dependencies=("Phoenix-scoped evidence adapters", "domain authorization and provenance metadata"),
    provenance_requirements=("domain", "authority class", "original evidence reference", "adapter and projection version", "Phoenix ownership"),
)

POLICY_VERSION = "unified-retrieval-foundation-v1"
SAFE_DOMAIN = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
CORE_DOMAINS = ("native_archive", "memory", "library", "inherited_history")
INHERITED_REQUIRED = (
    "history_era", "relationship_provenance", "identity_attribution",
    "native_boundary_status", "provider_source", "export_id",
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def contradiction_group_ids(item):
    """Preserve all explicitly recorded memberships; never infer a relation."""
    groups = item.get("contradiction_group_ids", [])
    if not isinstance(groups, (list, tuple)) or not all(isinstance(g, str) and g.strip() for g in groups):
        raise ValueError("malformed contradiction group metadata")
    groups = list(groups)
    if "contradiction_group_id" in item:
        singular = item["contradiction_group_id"]
        if not isinstance(singular, str) or not singular.strip():
            raise ValueError("malformed contradiction group metadata")
        groups.append(singular)
    return sorted(set(groups))


def contradiction_units(items):
    """Connected groups among observed evidence, not a claim of global truth."""
    parents, group_owner = {}, {}
    def find(key):
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key
    for item in items:
        key = (item["domain"], item["evidence_id"])
        parents.setdefault(key, key)
        groups = contradiction_group_ids(item)
        for group in groups:
            if group in group_owner:
                parents[find(key)] = find(group_owner[group])
            else:
                group_owner[group] = key
    units = {}
    for key in parents:
        units.setdefault(find(key), []).append(key)
    return list(units.values())


def retain_complete_groups(selected, catalog):
    present = {(item["domain"], item["evidence_id"]) for item in selected}
    omitted = set()
    for members in contradiction_units(catalog):
        if not set(members) <= present:
            omitted.update(set(members) & present)
    return ([item for item in selected if (item["domain"], item["evidence_id"]) not in omitted], omitted)


@dataclass(frozen=True)
class ProjectionDescriptor:
    domain: str
    processor_id: str
    processor_version: str
    method: str
    source_frontier_sha256: str
    built_from_frontier_sha256: str
    model_id: str | None = None
    model_version: str | None = None

    def __post_init__(self):
        if not SAFE_DOMAIN.fullmatch(self.domain):
            raise ValueError("invalid projection domain")
        for name in ("processor_id", "processor_version", "method",
                     "source_frontier_sha256", "built_from_frontier_sha256"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"projection {name} is required")
        if self.method == "semantic" and not self.model_id:
            raise ValueError("semantic projection model identity is required")

    @property
    def projection_id(self):
        return "projection-" + _digest({
            "domain": self.domain, "processor_id": self.processor_id,
            "processor_version": self.processor_version, "method": self.method,
            "built_from_frontier_sha256": self.built_from_frontier_sha256,
            "model_id": self.model_id, "model_version": self.model_version,
        })[:32]

    @property
    def status(self):
        return "current" if self.source_frontier_sha256 == self.built_from_frontier_sha256 else "stale"

    def public(self):
        return {"projection_id": self.projection_id, "domain": self.domain,
                "processor_id": self.processor_id, "processor_version": self.processor_version,
                "method": self.method, "model_id": self.model_id,
                "model_version": self.model_version,
                "source_frontier_sha256": self.source_frontier_sha256,
                "built_from_frontier_sha256": self.built_from_frontier_sha256,
                "status": self.status, "derived": True, "rebuildable": True,
                "originals_authoritative": True}


class EvidenceDomainAdapter(ABC):
    """Explicit extension seam; adapters remain responsible for their domain."""

    domain_id = None
    adapter_version = None
    authority_class = None
    automatic_enabled = True
    required_grants = ()

    @abstractmethod
    def health(self):
        """Return status/reason without reading candidate payloads."""

    @abstractmethod
    def retrieve(self, query, *, instance_id, limit):
        """Return ranked domain-native candidate envelopes."""

    def projection(self):
        return None


class StaticEvidenceAdapter(EvidenceDomainAdapter):
    """Deterministic adapter for tests and local policy evaluation."""

    def __init__(self, domain_id, candidates=(), *, authority_class,
                 adapter_version="static-v1", available=True, degraded_reason=None,
                 automatic_enabled=True, required_grants=(), projection=None):
        self.domain_id = domain_id; self.adapter_version = adapter_version
        self.authority_class = authority_class; self._candidates = tuple(candidates)
        self._available = available; self._degraded_reason = degraded_reason
        self.automatic_enabled = automatic_enabled
        self.required_grants = tuple(required_grants); self._projection = projection

    def health(self):
        if not self._available:
            return {"status": "unavailable", "reason": "domain adapter is unavailable"}
        if self._degraded_reason:
            return {"status": "degraded", "reason": self._degraded_reason}
        return {"status": "available", "reason": "domain adapter is configured"}

    def retrieve(self, query, *, instance_id, limit):
        selected, _ = retain_complete_groups(self._candidates[:limit], self._candidates)
        return [dict(item) for item in selected]

    def projection(self):
        return self._projection


class UnifiedRetrievalPlanner:
    def __init__(self, instance_id, *, adapters, policy_version=POLICY_VERSION,
                 eligibility_policy=None):
        self.instance_id = require_id(instance_id, "instance_id")
        self.policy_version = require_id(policy_version, "policy_version")
        self.eligibility_policy = eligibility_policy
        self.adapters = {}
        for adapter in adapters:
            if not isinstance(adapter, EvidenceDomainAdapter):
                raise TypeError("retrieval adapters must implement EvidenceDomainAdapter")
            if not SAFE_DOMAIN.fullmatch(str(adapter.domain_id or "")):
                raise ValueError("invalid retrieval domain id")
            if adapter.domain_id in self.adapters:
                raise ValueError("duplicate retrieval domain adapter")
            for field in ("adapter_version", "authority_class"):
                require_id(getattr(adapter, field, None), f"adapter {field}")
            self.adapters[adapter.domain_id] = adapter

    def plan(self, query, *, requested_domains=None, grants=(), total_budget_chars=8000,
             max_candidates_per_domain=20, evidence_use_context=None):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("retrieval query is required")
        if not isinstance(total_budget_chars, int) or total_budget_chars < 256:
            raise ValueError("retrieval character budget must be at least 256")
        if not isinstance(max_candidates_per_domain, int) or not 1 <= max_candidates_per_domain <= 100:
            raise ValueError("invalid per-domain candidate limit")
        requested = tuple(dict.fromkeys(requested_domains or self.adapters.keys()))
        if not requested or any(not SAFE_DOMAIN.fullmatch(str(item)) for item in requested):
            raise ValueError("invalid requested retrieval domains")
        grants = frozenset(grants)
        statuses, candidates, exclusions, warnings = {}, {}, [], []
        observed_candidates = []

        # Eligibility is complete before any adapter is permitted to retrieve.
        eligible = []
        for domain in requested:
            adapter = self.adapters.get(domain)
            if adapter is None:
                statuses[domain] = {"status": "excluded", "reason": "adapter_not_configured"}
                exclusions.append({"domain": domain, "stage": "eligibility", "reason": "adapter_not_configured"})
                continue
            if not adapter.automatic_enabled:
                statuses[domain] = {"status": "excluded", "reason": "automatic_retrieval_disabled"}
                exclusions.append({"domain": domain, "stage": "eligibility", "reason": "automatic_retrieval_disabled"})
                continue
            missing = sorted(set(adapter.required_grants) - grants)
            if missing:
                statuses[domain] = {"status": "excluded", "reason": "authorization_missing", "missing_grants": missing}
                exclusions.append({"domain": domain, "stage": "eligibility", "reason": "authorization_missing", "missing_grants": missing})
                continue
            health = adapter.health()
            if health.get("status") != "available":
                reason = "domain_unavailable" if health.get("status") == "unavailable" else "domain_degraded"
                statuses[domain] = {"status": "excluded", "reason": reason, "detail": health.get("reason")}
                exclusions.append({"domain": domain, "stage": "eligibility", "reason": reason})
                warnings.append(f"{domain}: {health.get('reason') or reason}")
                continue
            projection = adapter.projection()
            if projection is not None:
                if not isinstance(projection, ProjectionDescriptor):
                    statuses[domain] = {"status": "excluded", "reason": "projection_malformed"}
                    exclusions.append({"domain": domain, "stage": "eligibility", "reason": "projection_malformed"})
                    warnings.append(f"{domain}: projection metadata is malformed")
                    continue
                if projection.domain != domain or projection.status == "stale":
                    reason = "projection_domain_mismatch" if projection.domain != domain else "projection_stale"
                    statuses[domain] = {"status": "excluded", "reason": reason,
                                        "projection": projection.public()}
                    exclusions.append({"domain": domain, "stage": "eligibility", "reason": reason})
                    warnings.append(f"{domain}: {reason.replace('_', ' ')}")
                    continue
            statuses[domain] = {"status": "eligible", "reason": "authorization_health_and_projection_checks_passed"}
            eligible.append(domain)

        for domain in eligible:
            adapter = self.adapters[domain]
            try:
                raw = adapter.retrieve(query, instance_id=self.instance_id,
                                       limit=max_candidates_per_domain)
                domain_candidates = [self._candidate(domain, adapter, item, position)
                                     for position, item in enumerate(raw, 1)]
                observed_candidates.extend(domain_candidates)
                candidates[domain] = []
                for item in domain_candidates:
                    if self.eligibility_policy is None:
                        candidates[domain].append(item)
                        continue
                    decision = self.eligibility_policy.evaluate(item, evidence_use_context)
                    audit = {key: decision[key] for key in (
                        "policy_version", "source_domain", "authority_class",
                        "privacy_classification", "original_evidence_reference_sha256",
                        "automatic_private_context", "provider_transmission",
                        "external_disclosure", "cross_principal_disclosure",
                        "sensitive_content_logged")}
                    if decision["selected_for_context"]:
                        item["eligibility"] = audit
                        candidates[domain].append(item)
                    else:
                        exclusions.append({"domain": domain, "stage": "eligibility",
                            "reason": decision["automatic_private_context"]["reason"],
                            "evidence_id": item["evidence_id"], "eligibility": audit})
                statuses[domain]["candidate_count"] = len(candidates[domain])
            except (ValueError, PermissionError, LookupError, OSError) as exc:
                candidates[domain] = []
                statuses[domain] = {"status": "excluded", "reason": "retrieval_degraded",
                                    "detail": type(exc).__name__}
                exclusions.append({"domain": domain, "stage": "retrieval", "reason": "retrieval_degraded"})
                warnings.append(f"{domain}: retrieval failed ({type(exc).__name__})")

        active = [domain for domain in eligible if statuses[domain]["status"] == "eligible"]
        complete, omitted = retain_complete_groups(
            [item for domain in active for item in candidates.get(domain, ())], observed_candidates)
        keep = {(item["domain"],item["evidence_id"]) for item in complete}
        if omitted:
            warnings.append("Known contradiction group incomplete after eligibility; remaining members omitted")
            exclusions.extend({"domain":d,"evidence_id":eid,"stage":"group_integrity","reason":"known_contradiction_group_incomplete"} for d,eid in sorted(omitted))
            candidates = {domain:[item for item in items if (domain,item["evidence_id"]) in keep] for domain,items in candidates.items()}
        allocations = self._allocations(active, total_budget_chars)
        selected, used = [], {domain: 0 for domain in active}
        # Fair deterministic rounds prevent one noisy domain starving all peers.
        cursor = 0
        ranked_rounds = []
        maximum_candidates = max((len(candidates.get(d, ())) for d in active), default=0)
        while cursor < maximum_candidates:
            for domain in active:
                items = candidates.get(domain, ())
                if cursor >= len(items):
                    continue
                ranked_rounds.append(items[cursor])
            cursor += 1
        by_key = {(item["domain"],item["evidence_id"]):item for item in ranked_rounds}
        if len(by_key) != len(ranked_rounds): raise ValueError("duplicate candidate evidence identity")
        for keys in contradiction_units(ranked_rounds):
            unit = [by_key[key] for key in keys]
            costs = {domain:sum(item["estimated_chars"] for item in unit if item["domain"] == domain) for domain in active}
            if all(used[domain] + costs[domain] <= allocations[domain] for domain in active):
                selected.extend(unit)
                for domain in active: used[domain] += costs[domain]
            else:
                if len(unit) > 1: warnings.append("Contradiction group omitted because its complete observed membership exceeds the domain budget")
                exclusions.extend({"domain":item["domain"],"stage":"budget","reason":"domain_budget_exhausted",
                    "candidate_id":item["candidate_id"],"atomic_group_size":len(unit)} for item in unit)

        plan = {"schema_version": 1, "record_type": "unified_retrieval_plan",
                "instance_id": self.instance_id, "policy_version": self.policy_version,
                "query": query, "requested_domains": list(requested),
                "eligible_domains": active, "domain_status": statuses,
                "candidates": [item for domain in requested for item in candidates.get(domain, ())],
                "selected_evidence": selected, "exclusions": exclusions,
                "allocation": {"unit": "estimated_characters", "precision": "conservative_approximation",
                               "total_budget": total_budget_chars,
                               "per_domain_budget": allocations, "per_domain_used": used,
                               "policy": "equal_floor_then_domain_local_rank_round_robin",
                               "contradiction_policy":"atomic_observed_groups_no_truth_selection",
                               "membership_scope":"adapter_observations_not_global_completeness"},
                "warnings": warnings, "side_effects": {"archive": False, "memory": False,
                    "library": False, "inherited_history": False, "development": False,
                    "identity_classification": False, "native_boundary_change": False}}
        plan["deterministic_replay_input_sha256"] = _digest({k: v for k, v in plan.items()
                                                              if k != "deterministic_replay_input_sha256"})
        return plan

    def _candidate(self, domain, adapter, item, position):
        if not isinstance(item, dict):
            raise ValueError("retrieval candidate must be an object")
        if item.get("instance_id") != self.instance_id:
            raise PermissionError("retrieval candidate Phoenix ownership mismatch")
        evidence_id = require_id(item.get("evidence_id"), "candidate evidence_id")
        if item.get("domain") != domain:
            raise ValueError("retrieval candidate domain mismatch")
        if item.get("authority_class") != adapter.authority_class:
            raise ValueError("retrieval candidate authority mismatch")
        reference = item.get("original_evidence_reference")
        if not isinstance(reference, dict) or not reference:
            raise ValueError("retrieval candidate original evidence reference is required")
        if domain == "inherited_history":
            missing = [key for key in INHERITED_REQUIRED if key not in item]
            if missing:
                raise ValueError("inherited candidate provenance is incomplete")
            if item["history_era"] != "inherited_history":
                raise ValueError("inherited candidate history era changed")
            if item["identity_attribution"] == "proven_native":
                raise ValueError("retrieval cannot assign proven_native")
        text = item.get("text")
        if not isinstance(text, str):
            raise ValueError("retrieval candidate text is required")
        projection = adapter.projection()
        envelope = {**item, "candidate_id": "candidate-" + _digest({
            "instance_id": self.instance_id, "domain": domain,
            "evidence_id": evidence_id, "adapter_version": adapter.adapter_version,
            "projection_id": projection.projection_id if projection else None})[:32],
            "adapter_version": adapter.adapter_version,
            "projection": projection.public() if projection else None,
            "domain_rank": position, "estimated_chars": len(text),
            "original_authoritative": True, "derived_candidate": True}
        return envelope

    @staticmethod
    def _allocations(domains, total):
        if not domains:
            return {}
        base, remainder = divmod(total, len(domains))
        return {domain: base + (1 if position < remainder else 0)
                for position, domain in enumerate(domains)}
