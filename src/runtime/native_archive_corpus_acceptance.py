"""Deterministic qualification runner for synthetic native Archive acceptance data."""

import copy
import hashlib
import json

from src.runtime.evidence_eligibility import EvidenceUseContext, ProductionEvidenceEligibilityPolicy
from src.runtime.native_continuity_projection import (
    NativeArchiveCandidateGenerator, NativeContinuityProjection,
    NativeSourceRepresentationPreference,
)
from src.runtime.native_retrieval_ambiguity import NativeRetrievalAmbiguityPolicy


ACCEPTANCE_VERSION = "native-archive-ambiguity-corpus-v1"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _metadata(record, instance_id, rider_id):
    item = copy.deepcopy(record)
    evidence_id = item["evidence_id"]
    item.setdefault("instance_id", instance_id)
    item.setdefault("domain", "native_archive")
    item.setdefault("authority_class", "native_canonical_evidence")
    item.setdefault("owner_principal_id", rider_id)
    item.setdefault("privacy_classification", "potentially_private")
    item.setdefault("original_evidence_reference", {
        "archive_id": "acceptance-archive-" + evidence_id,
        "message_id": "acceptance-message-" + evidence_id,
    })
    item.setdefault("provenance_valid", True)
    item.setdefault("automatic_use_enabled", True)
    item.setdefault("source_schema_version", 2)
    item.setdefault("eligibility_flags", [])
    item.setdefault("local_lexical_terms", [])
    return item


def _eligible(records, *, instance_id, rider_id):
    policy = ProductionEvidenceEligibilityPolicy()
    context = EvidenceUseContext(instance_id=instance_id, rider_principal_id=rider_id,
        capability_id="chat.respond", capability_authorized=True,
        provider_mode="configured_external_provider", provider_authorized=True)
    allowed, exclusions = [], []
    for record in records:
        decision = policy.evaluate(record, context)
        if decision["selected_for_context"]:
            allowed.append({**record, "eligibility": decision})
        else:
            exclusions.append({"evidence_id": record.get("evidence_id"),
                               "reason": decision["automatic_private_context"]["reason"]})
    return allowed, exclusions


def _run_generation(case, instance_id, rider_id):
    records = [_metadata(item, instance_id, rider_id) for item in case["records"]]
    eligible, exclusions = _eligible(records, instance_id=instance_id, rider_id=rider_id)
    generated, audit = NativeArchiveCandidateGenerator().generate(
        query=case["query"], eligible_metadata=eligible,
        request_timestamp=case.get("request_timestamp"), rider_timezone=case.get("rider_timezone"),
        max_total=case.get("max_total", 24), max_per_conversation=case.get("max_per_conversation", 4),
        max_thread_hops=case.get("max_thread_hops", 2),
        max_relationship_expansions=case.get("max_relationship_expansions", 8))
    if case.get("safe_joint_ambiguity"):
        ids = sorted(item["evidence_id"] for item in generated)
        ambiguity_id = "acceptance-safe-joint-" + _digest(ids)[:16]
        audit["reference_ambiguity_sets"] = [{"ambiguity_set_id": ambiguity_id,
            "candidate_evidence_ids": ids,
            "basis": "multiple_temporal_native_anchors_safe_joint_inclusion"}]
        audit["ambiguity_choice_descriptors"] = [{"ambiguity_set_id": ambiguity_id,
            "choices": [{"evidence_id": item["evidence_id"], "created_at": item.get("created_at")}
                        for item in generated]}]
    selected = [{**item, "text": "synthetic acceptance body", "estimated_chars": 25}
                for item in generated]
    ambiguity = NativeRetrievalAmbiguityPolicy().evaluate(
        instance_id=instance_id, rider_principal_id=rider_id,
        request_message_id="acceptance-request-" + case["case_id"],
        correlation_id="acceptance-request-" + case["case_id"],
        candidate_generation={"native_archive": audit}, selected_evidence=selected,
        planner_version="unified-retrieval-foundation-v1",
        eligibility_policy_version=ProductionEvidenceEligibilityPolicy.version,
        retrieval_plan_identity="acceptance-plan-" + _digest(audit)[:24],
        query_sha256=hashlib.sha256(case["query"].encode()).hexdigest())
    choice_ids = sorted(choice["evidence_id"] for group in ambiguity["ambiguity_sets"]
                        if group["clarification_required"] for choice in group["choices"])
    return {"case_id": case["case_id"], "kind": "generation",
        "generated_evidence_ids": sorted(item["evidence_id"] for item in generated),
        "clarification_required": ambiguity["clarification_required"],
        "clarification_choice_evidence_ids": choice_ids,
        "temporal_constraint": audit["interpretation"].get("temporal_constraint"),
        "exclusions": exclusions, "generation_sha256": audit["generation_sha256"],
        "ambiguity_replay_sha256": ambiguity["replay_sha256"],
        "automatic_inherited_history": audit["automatic_inherited_history"],
        "sensitive_content_logged": audit["sensitive_content_logged"]}


def _run_projection(case, instance_id, rider_id):
    records = [_metadata(item, instance_id, rider_id) for item in case["records"]]
    candidates = [{**item, "text": item.get("body", "synthetic acceptance body")}
                  for item in records]
    catalog = [{key: item.get(key) for key in ("instance_id", "domain", "evidence_id",
        "conversation_id", "created_at", "original_evidence_reference")} for item in records]
    projected, audit = NativeContinuityProjection().project(instance_id=instance_id,
        query=case["query"], candidates=candidates, metadata_catalog=catalog,
        built_from_frontier_sha256=("deliberately-stale" if case.get("stale") else None))
    return {"case_id": case["case_id"], "kind": "projection",
        "projected_evidence_ids": sorted(item["evidence_id"] for item in projected),
        "status": audit["status"], "projection_applied": audit["projection_applied"],
        "duplicate_group_count": len(audit["duplicate_group_ids"]),
        "contradiction_group_ids": audit["contradiction_group_ids"],
        "canonical_records_merged": audit["canonical_records_merged"],
        "truth_resolution_performed": audit["truth_resolution_performed"],
        "automatic_inherited_history": audit["automatic_inherited_history"],
        "sensitive_content_logged": audit["sensitive_content_logged"]}


def _run_preference(case, instance_id, rider_id):
    records = [_metadata(item, instance_id, rider_id) for item in case["records"]]
    eligible, exclusions = _eligible(records, instance_id=instance_id, rider_id=rider_id)
    selected, audit = NativeSourceRepresentationPreference().apply(
        generated_candidates=eligible, eligible_metadata=eligible)
    return {"case_id": case["case_id"], "kind": "preference",
        "selected_evidence_ids": sorted(item["evidence_id"] for item in selected),
        "exclusions": exclusions, "context_redundancy_reduction": audit["context_redundancy_reduction"],
        "canonical_records_mutated": audit["canonical_records_mutated"],
        "truth_resolution_performed": audit["truth_resolution_performed"],
        "preference_sha256": audit["preference_sha256"],
        "automatic_inherited_history": audit["automatic_inherited_history"],
        "sensitive_content_logged": audit["sensitive_content_logged"]}


def run_corpus(corpus, expectations):
    """Run acceptance inputs twice, then assess only against separate annotations."""
    instance_id = corpus["instance_id"]; rider_id = corpus["rider_principal_id"]
    runners = {"generation": _run_generation, "projection": _run_projection,
               "preference": _run_preference}
    first = [runners[item["kind"]](item, instance_id, rider_id) for item in corpus["cases"]]
    second = [runners[item["kind"]](copy.deepcopy(item), instance_id, rider_id)
              for item in corpus["cases"]]
    actual = {item["case_id"]: item for item in first}
    expected = {item["case_id"]: item for item in expectations["cases"]}

    material = [item for item in expected.values() if item.get("requires_clarification") is True]
    answerable = [item for item in expected.values() if item.get("requires_clarification") is False]
    material_hits = sum(actual[item["case_id"]].get("clarification_required") is True for item in material)
    false_positives = sum(actual[item["case_id"]].get("clarification_required") is True for item in answerable)
    safe_joint = [item for item in expected.values() if item.get("safe_joint")]
    safe_joint_hits = sum(actual[item["case_id"]].get("clarification_required") is False for item in safe_joint)
    choice_cases = [item for item in expected.values() if "expected_choice_ids" in item]
    choice_hits = sum(actual[item["case_id"]].get("clarification_choice_evidence_ids")
                      == sorted(item["expected_choice_ids"]) for item in choice_cases)
    traversal_cases = [item for item in expected.values() if "expected_generated_ids" in item]
    traversal_tp = traversal_total = traversal_extra = 0
    for item in traversal_cases:
        observed = set(actual[item["case_id"]].get("generated_evidence_ids", ()))
        wanted = set(item["expected_generated_ids"])
        traversal_tp += len(observed & wanted); traversal_total += len(wanted)
        traversal_extra += len(observed - wanted)
    temporal_cases = [item for item in expected.values() if "expected_temporal" in item]
    temporal_hits = sum(actual[item["case_id"]].get("temporal_constraint") == item["expected_temporal"]
                        for item in temporal_cases)
    security_checks = []
    for item in expected.values():
        observed = actual[item["case_id"]]
        surfaced = (set(observed.get("generated_evidence_ids", ()))
                    | set(observed.get("clarification_choice_evidence_ids", ()))
                    | set(observed.get("selected_evidence_ids", ())))
        security_checks.append(not (surfaced & set(item.get("forbidden_ids", ()))))
        security_checks.append(observed.get("automatic_inherited_history") is False)
        security_checks.append(observed.get("sensitive_content_logged") is False)
        if observed["kind"] == "projection":
            security_checks.extend([not observed["canonical_records_merged"], not observed["truth_resolution_performed"]])
        if observed["kind"] == "preference":
            security_checks.extend([not observed["canonical_records_mutated"], not observed["truth_resolution_performed"]])

    def ratio(numerator, denominator): return 1.0 if not denominator else numerator / denominator
    metrics = {
        "material_ambiguity_recall": {"passed": material_hits, "total": len(material), "rate": ratio(material_hits, len(material))},
        "false_positive_clarification_rate": {"false_positives": false_positives, "total": len(answerable), "rate": ratio(false_positives, len(answerable)) if answerable else 0.0},
        "safe_joint_inclusion_accuracy": {"passed": safe_joint_hits, "total": len(safe_joint), "rate": ratio(safe_joint_hits, len(safe_joint))},
        "choice_quality": {"passed": choice_hits, "total": len(choice_cases), "rate": ratio(choice_hits, len(choice_cases))},
        "reference_traversal_precision": {"true_positive": traversal_tp, "expected": traversal_total,
            "unexpected": traversal_extra, "rate": ratio(traversal_tp, traversal_tp + traversal_extra)},
        "temporal_interpretation_accuracy": {"passed": temporal_hits, "total": len(temporal_cases), "rate": ratio(temporal_hits, len(temporal_cases))},
        "fail_closed_security": {"passed": sum(security_checks), "total": len(security_checks), "rate": ratio(sum(security_checks), len(security_checks))},
        "determinism": {"passed": sum(a == b for a, b in zip(first, second)), "total": len(first),
            "rate": ratio(sum(a == b for a, b in zip(first, second)), len(first))},
    }
    thresholds = expectations["thresholds"]
    checks = {
        "material_ambiguity_recall": metrics["material_ambiguity_recall"]["rate"] >= thresholds["material_ambiguity_recall_min"],
        "false_positive_clarification_rate": metrics["false_positive_clarification_rate"]["rate"] <= thresholds["false_positive_clarification_rate_max"],
        "safe_joint_inclusion_accuracy": metrics["safe_joint_inclusion_accuracy"]["rate"] >= thresholds["safe_joint_inclusion_accuracy_min"],
        "choice_quality": metrics["choice_quality"]["rate"] >= thresholds["choice_quality_min"],
        "reference_traversal_precision": metrics["reference_traversal_precision"]["rate"] >= thresholds["reference_traversal_precision_min"],
        "temporal_interpretation_accuracy": metrics["temporal_interpretation_accuracy"]["rate"] >= thresholds["temporal_interpretation_accuracy_min"],
        "fail_closed_security": metrics["fail_closed_security"]["rate"] >= thresholds["fail_closed_security_min"],
        "determinism": metrics["determinism"]["rate"] >= thresholds["determinism_min"],
    }
    result = {"schema_version": 1, "record_type": "native_archive_corpus_acceptance",
        "acceptance_version": ACCEPTANCE_VERSION, "synthetic_disposable_data": True,
        "real_history_accessed": False, "scenario_count": len(first), "thresholds": thresholds,
        "metrics": metrics, "threshold_checks": checks, "passed": all(checks.values()),
        "case_results": first}
    result["result_sha256"] = _digest(result)
    result["summary"] = (f"{len(first)} synthetic native Archive scenarios; "
        f"ambiguity recall {material_hits}/{len(material)}, false positives {false_positives}/{len(answerable)}, "
        f"choice quality {choice_hits}/{len(choice_cases)}, security {sum(security_checks)}/{len(security_checks)}, "
        f"determinism {metrics['determinism']['passed']}/{len(first)}; "
        f"acceptance {'passed' if result['passed'] else 'failed'}.")
    return result
