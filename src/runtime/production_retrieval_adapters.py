"""Two-stage production retrieval adapters.

Stage A emits body-free metadata. Eligibility is decided centrally. Stage B
materializes and ranks only allowed references. No adapter writes source state.
"""

from abc import ABC, abstractmethod
from pathlib import Path
import copy
import hashlib
import json
import re
import sqlite3

from src.memory.archive_retrieval import INDEX_PATH, META_DIR
from src.capture.storage import read_metadata
from src.memory.store import list_memories, load_memory
from src.library.store import list_sources, list_extractions
from src.runtime.evidence_eligibility import ProductionEvidenceEligibilityPolicy
from src.runtime.legacy_compatibility import derive_legacy_compatibility, apply_legacy_compatibility
from src.runtime.retrieval_planner import StaticEvidenceAdapter, UnifiedRetrievalPlanner, retain_complete_groups, contradiction_group_ids
from src.runtime.native_continuity_projection import (
    NativeContinuityProjection, NativeArchiveCandidateGenerator, stable_native_evidence_id,
    NativeSourceRepresentationPreference,
)
from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract

PRODUCTION_ADAPTERS_DEFINITION = CapabilityDefinition(
    name="retrieval.production_adapters", version="1.1",
    display_name="Two-stage Production Evidence Adapters",
    description="Enumerate body-free evidence metadata, enforce eligibility, then materialize and rank only allowed Archive, Memory, and Library candidates.",
    effect="read_only_retrieval_projection",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read",), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="eligibility_before_materialization_ranking_and_provider_processing",
    features=("metadata_first_enumeration", "central_policy_gate", "eligible_only_materialization", "eligible_only_ranking", "local_degraded_ranking"),
    appropriate_use=("prepare policy-compliant evidence plans",),
    inappropriate_use=("bypass provider denial", "automatic inherited-history retrieval", "canonical mutation"),
    limitations=("served planner Chat is default with explicit legacy rollback", "metadata enumeration is currently bounded by local store implementation rather than a streaming catalog"),
    dependencies=("production evidence eligibility policy", "Unified Retrieval Planner"),
    provenance_requirements=("stable evidence reference", "authority class", "eligibility decision", "adapter version"),
)


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", str(text).casefold()))


def _observation(value):
    """Pin the local authorized observation, including body and authority state."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _require_observation(reference, value):
    expected = reference.get("observation_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected) or expected != _observation(value):
        raise LookupError("evidence changed since authorization; re-enumeration required")


class TwoStageEvidenceAdapter(ABC):
    domain_id = None
    authority_class = None
    adapter_version = None
    automatic_enabled = True

    @abstractmethod
    def enumerate_metadata(self, *, instance_id):
        """Return body-free candidate metadata and stable references."""

    @abstractmethod
    def materialize(self, reference, *, instance_id):
        """Resolve one already-eligible reference locally."""

    def rank_local(self, query, candidates, *, limit):
        terms = _tokens(query)
        ranked = []
        for item in candidates:
            overlap = len(terms & _tokens(item["text"]))
            if overlap:
                ranked.append({**item, "retrieval_score": overlap / max(1, len(terms)),
                               "rank_basis": "local_lexical_after_eligibility"})
        return sorted(ranked, key=lambda x: (-x["retrieval_score"], x["evidence_id"]))[:limit]

    def enrich_ranked(self, query, candidates, *, metadata_catalog):
        return list(candidates), None

    def generate_candidate_metadata(self, query, eligible_metadata, *, request_timestamp=None, rider_timezone=None):
        return list(eligible_metadata), None

    def prefer_representations(self, generated_metadata, *, eligible_metadata):
        return list(generated_metadata), None


class NativeArchiveProductionAdapter(TwoStageEvidenceAdapter):
    domain_id = "native_archive"; authority_class = "native_canonical_evidence"
    adapter_version = "native-archive-two-stage-v4-bound-observation"

    def __init__(self, *, index_path=None, meta_dir=None):
        self.index_path = Path(index_path or INDEX_PATH)
        self.meta_dir = Path(meta_dir) if meta_dir is not None else META_DIR
        self.continuity_projection = NativeContinuityProjection()
        self.candidate_generator = NativeArchiveCandidateGenerator()
        self.representation_preference = NativeSourceRepresentationPreference()

    def _metadata(self, row):
        archive_id = row["source_archive_id"]
        if not isinstance(archive_id, str) or Path(archive_id).name != archive_id or archive_id in {".", ".."}:
            raise ValueError("invalid retained Archive reference")
        meta = read_metadata(self.meta_dir / f"{archive_id}.json")
        if (meta.get("instance_id") != row["instance_id"]
                or meta.get("conversation_id") not in {None, row["conversation_id"]}
                or not row["canonicalizer_version"]):
            raise ValueError("Archive index and retained metadata binding disagree")
        # Historical metadata may omit conversation_id. Its exact archive ID
        # and explicit Phoenix owner remain mandatory; a missing field never
        # becomes an invented source assertion or an unreadable-metadata fallback.
        if not isinstance(meta.get("privacy", {}), dict):
            raise ValueError("Archive privacy metadata is malformed")
        if type(meta.get("schema_version", 1)) is not int or meta.get("schema_version", 1) < 1:
            raise ValueError("Archive schema metadata is malformed")
        return meta

    def enumerate_metadata(self, *, instance_id):
        if not self.index_path.exists(): return []
        db = sqlite3.connect(self.index_path); db.row_factory = sqlite3.Row
        try:
            rows = db.execute("SELECT instance_id,conversation_id,message_id,created_at,content,source_archive_id,canonicalizer_version,role FROM canonical_message_projection WHERE instance_id=? ORDER BY created_at,message_id", (instance_id,)).fetchall()
        finally: db.close()
        results = []
        for row in rows:
            meta = self._metadata(row)
            privacy = meta.get("privacy", {}).get("classification")
            identity_fields = {"instance_id": row["instance_id"], "conversation_id": row["conversation_id"],
                               "message_id": row["message_id"], "source_archive_id": row["source_archive_id"]}
            results.append({"instance_id": row["instance_id"], "domain": self.domain_id,
                "evidence_id": stable_native_evidence_id(identity_fields),
                "source_message_id": row["message_id"], "authority_class": self.authority_class,
                "conversation_id": row["conversation_id"], "created_at": row["created_at"],
                "local_lexical_terms": sorted(_tokens(row["content"])),
                "representation_provenance": meta.get("representation_provenance"),
                "contradiction_group_ids": contradiction_group_ids(meta),
                "native_reference_relationships": [dict(edge) for edge in
                    (meta.get("native_reference_relationships", {}).get(row["message_id"], ())
                     if isinstance(meta.get("native_reference_relationships"), dict) else ())
                    if isinstance(edge, dict)],
                "owner_principal_id": meta.get("owner_principal_id"), "privacy_classification": privacy,
                "original_evidence_reference": {"archive_id": row["source_archive_id"], "message_id": row["message_id"],
                    "observation_sha256": _observation({"metadata": meta, "projection": dict(row)})},
                "provenance_valid": True,
                "automatic_use_enabled": True, "continuity_ownership_basis": "scoped_instance_record",
                "source_schema_version": int(meta.get("schema_version", 1)),
                "eligibility_flags": [x for x in (meta.get("status"),) if x in {"restricted","revoked","quarantined","suppressed","shared"}]})
        return results

    def generate_candidate_metadata(self, query, eligible_metadata, *, request_timestamp=None, rider_timezone=None):
        return self.candidate_generator.generate(query=query, eligible_metadata=eligible_metadata,
            request_timestamp=request_timestamp, rider_timezone=rider_timezone)

    def rank_local(self, query, candidates, *, limit):
        terms = _tokens(query); ranked = []
        reason_weight = {"direct_lexical_metadata_match": 1.0,
                         "explicit_temporal_constraint": 0.75,
                         "qualified_source_original_for_copy": 0.9,
                         "reference_recent_conversation_anchor": 0.6,
                         "conversation_neighbor": 0.5,
                         "conversation_thread_hop": 0.45,
                         "verified_native_reference": 0.55}
        for item in candidates:
            overlap = len(terms & _tokens(item["text"]))
            reasons = [x.get("reason") for x in item.get("candidate_generation_reasons", ())]
            relationship_score = max((reason_weight.get(reason, 0) for reason in reasons), default=0)
            if overlap or relationship_score:
                ranked.append({**item, "retrieval_score": max(
                    overlap / max(1, len(terms)), relationship_score),
                    "rank_basis": "local_lexical_and_continuity_generation_after_eligibility"})
        return sorted(ranked, key=lambda x: (-x["retrieval_score"], x["evidence_id"]))[:limit]

    def prefer_representations(self, generated_metadata, *, eligible_metadata):
        return self.representation_preference.apply(
            generated_candidates=generated_metadata, eligible_metadata=eligible_metadata)

    def enrich_ranked(self, query, candidates, *, metadata_catalog):
        return self.continuity_projection.project(
            instance_id=candidates[0]["instance_id"] if candidates else "unused",
            query=query, candidates=candidates, metadata_catalog=metadata_catalog,
        ) if candidates else ([], None)

    def materialize(self, reference, *, instance_id):
        db = sqlite3.connect(self.index_path); db.row_factory = sqlite3.Row
        try:
            row = db.execute("SELECT instance_id,conversation_id,message_id,created_at,content,source_archive_id,canonicalizer_version,role FROM canonical_message_projection WHERE instance_id=? AND message_id=? AND source_archive_id=?", (instance_id, reference["message_id"], reference["archive_id"])).fetchone()
        finally: db.close()
        if row is None: raise LookupError("archive evidence unavailable")
        _require_observation(reference, {"metadata": self._metadata(row), "projection": dict(row)})
        return dict(row)


class MemoryProductionAdapter(TwoStageEvidenceAdapter):
    domain_id = "memory"; authority_class = "derived_memory_evidence"
    adapter_version = "memory-two-stage-v3-bound-observation"

    def enumerate_metadata(self, *, instance_id):
        results = []
        for item in list_memories(status="active", instance_id=instance_id, include_unscoped=False):
            privacy = item.get("privacy", {}).get("classification") or item.get("privacy_classification")
            results.append({"instance_id": item.get("instance_id"), "domain": self.domain_id,
                "evidence_id": item["memory_id"], "authority_class": self.authority_class,
                "owner_principal_id": item.get("owner_principal_id"), "privacy_classification": privacy,
                "original_evidence_reference": {"memory_id": item["memory_id"], "source_archive_ids": list(item.get("source_archive_ids", ())),
                    "observation_sha256": _observation(item)},
                "contradiction_group_ids": contradiction_group_ids(item),
                "provenance_valid": bool(item.get("source_archive_ids") or item.get("source_message_ids")),
                "automatic_use_enabled": item.get("status") == "active",
                "continuity_ownership_basis": "scoped_memory_source_archive_chain" if item.get("source_archive_ids") else "scoped_instance_record",
                "source_schema_version": int(item.get("schema_version", 1)),
                "eligibility_flags": [item.get("status")] if item.get("status") in {"revoked","quarantined","suppressed","shared","restricted"} else []})
        return results

    def materialize(self, reference, *, instance_id):
        item = load_memory(reference["memory_id"])
        if not item or item.get("instance_id") != instance_id or item.get('status') != 'active' or item.get('memory_id') != reference['memory_id']:
            raise LookupError("memory evidence unavailable")
        _require_observation(reference, item)
        return {"content": item["content"], "text": item["content"], "memory_type": item.get("memory_type"),
                **{key:copy.deepcopy(item[key]) for key in ('confidence','created_at','updated_at',
                    'uncertainty','ambiguity_set_ids') if key in item},
                "contradiction_group_ids": contradiction_group_ids(item),
                "source_archive_ids": list(item.get("source_archive_ids", ())) }


class LibraryProductionAdapter(TwoStageEvidenceAdapter):
    domain_id = "library"; authority_class = "immutable_library_source"
    adapter_version = "library-two-stage-v2-bound-observation"

    def __init__(self, *, library_root=None): self.library_root = library_root

    def enumerate_metadata(self, *, instance_id):
        sources = {x["source_id"]: x for x in list_sources(instance_id=instance_id, library_root=self.library_root)}
        results = []
        for extraction in list_extractions(instance_id=instance_id, library_root=self.library_root):
            source = sources.get(extraction.get("source_id"))
            if not source: continue
            artifact = source.get("artifact", {}); privacy = artifact.get("privacy", {}).get("classification")
            for segment in extraction.get("segments", ()):
                results.append({"instance_id": source.get("instance_id"), "domain": self.domain_id,
                    "evidence_id": segment["segment_id"], "authority_class": self.authority_class,
                    "owner_principal_id": artifact.get("owner_principal_id"), "privacy_classification": privacy,
                    "original_evidence_reference": {"source_id": source["source_id"], "extraction_id": extraction["extraction_id"], "segment_id": segment["segment_id"],
                        "observation_sha256": _observation({"source":source,"extraction":extraction})},
                    "provenance_valid": bool(source.get("sha256") and extraction.get("source_sha256") == source.get("sha256")),
                    "automatic_use_enabled": artifact.get("lifecycle", {}).get("state") not in {"quarantined","suppressed","revoked"},
                    "source_schema_version": int(source.get("schema_version", 1)),
                    "eligibility_flags": [artifact.get("lifecycle", {}).get("state")] if artifact.get("lifecycle", {}).get("state") in {"quarantined","suppressed","revoked","restricted"} else []})
        return results

    def materialize(self, reference, *, instance_id):
        sources = [item for item in list_sources(instance_id=instance_id, library_root=self.library_root)
                   if item.get("source_id") == reference["source_id"] and item.get("instance_id") == instance_id]
        if len(sources) != 1: raise LookupError("library source unavailable or ambiguous")
        for extraction in list_extractions(instance_id=instance_id, source_id=reference["source_id"], library_root=self.library_root):
            if extraction.get("extraction_id") != reference["extraction_id"]: continue
            _require_observation(reference, {"source":sources[0], "extraction":extraction})
            for segment in extraction.get("segments", ()):
                if segment.get("segment_id") == reference["segment_id"]:
                    return {"text": segment["text"], "location": segment.get("location"),
                            "source_id": reference["source_id"], "extraction_id": reference["extraction_id"]}
        raise LookupError("library evidence unavailable")


class TwoStageRetrievalCoordinator:
    def __init__(self, instance_id, rider_principal_id, *, adapters, eligibility_policy=None,
                 semantic_ranker=None, provider_route=None):
        self.instance_id = instance_id; self.rider_principal_id = rider_principal_id
        self.adapters = tuple(adapters); self.policy = eligibility_policy or ProductionEvidenceEligibilityPolicy()
        self.semantic_ranker = semantic_ranker
        self.provider_route = copy.deepcopy(provider_route)

    def plan(self, query, *, evidence_use_context, total_budget_chars=8000, limit_per_domain=20,
             excluded_evidence_ids=(), request_timestamp=None, rider_timezone=None):
        prepared, exclusions, ordering, warnings, domain_projections, candidate_generation, representation_preference = [], [], [], [], {}, {}, {}
        complete_catalog = []
        failed_domains = set()
        excluded_evidence_ids = frozenset(x for x in excluded_evidence_ids if x)
        for adapter in self.adapters:
            ordering.append({"domain": adapter.domain_id, "event": "enumerate_metadata"})
            eligible_metadata = []
            try:
                metadata_catalog = list(adapter.enumerate_metadata(instance_id=self.instance_id))
            except (OSError, ValueError, LookupError) as exc:
                exclusions.append({"domain":adapter.domain_id, "stage":"metadata", "reason":"metadata_unavailable_or_invalid", "error_type":type(exc).__name__})
                warnings.append(f"{adapter.domain_id}: metadata unavailable; no legacy authority inferred")
                failed_domains.add(adapter.domain_id)
                prepared.append((adapter, []))
                continue
            complete_catalog.extend(metadata_catalog)
            for metadata in metadata_catalog:
                candidate = dict(metadata)
                if (candidate.get("evidence_id") in excluded_evidence_ids
                        or candidate.get("source_message_id") in excluded_evidence_ids):
                    exclusions.append({"domain": adapter.domain_id, "stage": "working_context",
                        "reason": "working_context_excluded", "evidence_id": candidate.get("evidence_id")})
                    continue
                if candidate.get("privacy_classification") is None:
                    compatibility = derive_legacy_compatibility(candidate, instance_id=self.instance_id,
                        rider_principal_id=self.rider_principal_id)
                    candidate = apply_legacy_compatibility(candidate, compatibility)
                ordering.append({"domain": adapter.domain_id, "event": "eligibility", "evidence_id": candidate.get("evidence_id")})
                decision = self.policy.evaluate(candidate, evidence_use_context)
                if (self.provider_route is not None
                        and decision.get("provider_transmission", {}).get("allowed") is True):
                    decision = copy.deepcopy(decision)
                    decision["provider_transmission"]["provider_route"] = copy.deepcopy(self.provider_route)
                if not decision["selected_for_context"]:
                    exclusions.append({"domain": adapter.domain_id, "stage": "eligibility",
                        "reason": decision["automatic_private_context"]["reason"],
                        "evidence_id": candidate.get("evidence_id"), "eligibility": decision})
                    continue
                candidate["privacy_classification"] = decision["privacy_classification"]
                candidate["eligibility"] = decision
                eligible_metadata.append(candidate)
            generated_metadata, generation_audit = adapter.generate_candidate_metadata(
                query, eligible_metadata, request_timestamp=request_timestamp,
                rider_timezone=rider_timezone,
            )
            if generation_audit is not None:
                candidate_generation[adapter.domain_id] = generation_audit
            generated_metadata, preference_audit = adapter.prefer_representations(
                generated_metadata, eligible_metadata=eligible_metadata)
            if preference_audit is not None:
                representation_preference[adapter.domain_id] = preference_audit
                for decision in preference_audit.get("decisions", ()):
                    if decision.get("decision") == "suppress_redundant_context_copy":
                        exclusions.append({"domain":adapter.domain_id,
                            "stage":"representation_preference",
                            "reason":"redundant_explicit_copy",
                            "evidence_id":decision.get("evidence_id"),
                            "preferred_evidence_id":decision.get("preferred_evidence_id")})
            ranked_input = []
            for candidate in generated_metadata:
                ordering.append({"domain": adapter.domain_id, "event": "materialize", "evidence_id": candidate["evidence_id"]})
                try:
                    body = adapter.materialize(candidate["original_evidence_reference"], instance_id=self.instance_id)
                except (OSError, ValueError, LookupError) as exc:
                    exclusions.append({"domain":adapter.domain_id, "stage":"materialization", "reason":"authorized_observation_unavailable", "evidence_id":candidate["evidence_id"], "error_type":type(exc).__name__})
                    warnings.append(f"{adapter.domain_id}: evidence observation changed or unavailable")
                    continue
                if "text" not in body and isinstance(body.get("content"), str):
                    body = {**body, "text": body["content"]}
                ranked_input.append({**candidate, **body})
            ordering.append({"domain": adapter.domain_id, "event": "rank", "candidate_count": len(ranked_input)})
            try:
                if self.semantic_ranker is not None and ranked_input:
                    ranked = self.semantic_ranker.rank(query=query, candidates=tuple(ranked_input), limit=limit_per_domain)
                else:
                    ranked = adapter.rank_local(query, ranked_input, limit=limit_per_domain)
            except Exception as exc:
                warnings.append(f"{adapter.domain_id}: ranking degraded to local ({type(exc).__name__})")
                ranked = adapter.rank_local(query, ranked_input, limit=limit_per_domain)
            ranked, projection = adapter.enrich_ranked(
                query, ranked, metadata_catalog=metadata_catalog,
            )
            if projection is not None:
                if projection.get("status") != "current":
                    warnings.append(f"{adapter.domain_id}: continuity projection is stale")
                domain_projections[adapter.domain_id] = projection
            prepared.append((adapter, ranked))
        # Ranking, working-context exclusion, or authorization changes must not
        # silently erase a known peer before the planner sees the group.
        ranked_all = [item for _, ranked in prepared for item in ranked]
        complete, omitted = retain_complete_groups(ranked_all, complete_catalog + ranked_all)
        keep = {(item["domain"], item["evidence_id"]) for item in complete}
        if omitted:
            warnings.append("Known contradiction group incomplete after eligibility/materialization/ranking; surviving members omitted")
            exclusions.extend({"domain":d,"evidence_id":eid,"stage":"group_integrity","reason":"known_contradiction_group_incomplete"} for d,eid in sorted(omitted))
        prepared = [StaticEvidenceAdapter(adapter.domain_id,
            [item for item in ranked if (item["domain"],item["evidence_id"]) in keep],
            authority_class=adapter.authority_class, adapter_version=adapter.adapter_version,
            available=adapter.domain_id not in failed_domains)
            for adapter,ranked in prepared]
        plan = UnifiedRetrievalPlanner(self.instance_id, adapters=prepared).plan(query,
            total_budget_chars=total_budget_chars, max_candidates_per_domain=limit_per_domain)
        plan["exclusions"] = exclusions + plan["exclusions"]
        plan["warnings"] = warnings + plan["warnings"]
        plan["enforcement_order"] = ordering
        plan["automatic_inherited_history"] = False
        plan["continuity_projections"] = domain_projections
        plan["candidate_generation"] = candidate_generation
        plan["representation_preference"] = representation_preference
        plan["deterministic_replay_input_sha256"] = hashlib.sha256(json.dumps(
            {key: value for key, value in plan.items() if key != "deterministic_replay_input_sha256"},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode()).hexdigest()
        return plan
