"""Served-runtime assembly for the verified production retrieval path."""

import hashlib
import json
import os
import copy

from src.memory.archive_context import build_archive_context
from src.runtime.evidence_eligibility import (
    EvidenceUseContext, POLICY_VERSION as ELIGIBILITY_POLICY_VERSION,
)
from src.runtime.production_retrieval_adapters import (
    NativeArchiveProductionAdapter, MemoryProductionAdapter,
    LibraryProductionAdapter, TwoStageRetrievalCoordinator,
)
from src.runtime.retrieval_planner import POLICY_VERSION as PLANNER_VERSION
from src.runtime.native_retrieval_ambiguity import NativeRetrievalAmbiguityPolicy


class ServedProductionPlannerBuilder:
    """Compose existing adapters without adding a parallel policy path."""

    def __init__(self, *, instance_id, provider_route, context_messages=20,
                 archive_index_path=None, archive_meta_dir=None, library_root=None,
                 total_budget_chars=8000, limit_per_domain=20):
        self.instance_id = instance_id
        self.rider_principal_id = f"authenticated-rider:{instance_id}"
        self.provider_route = provider_route
        self.context_messages = context_messages
        self.total_budget_chars = total_budget_chars
        self.limit_per_domain = limit_per_domain
        self.adapters = (
            NativeArchiveProductionAdapter(index_path=archive_index_path, meta_dir=archive_meta_dir),
            MemoryProductionAdapter(),
            LibraryProductionAdapter(library_root=library_root),
        )
        self.coordinator = TwoStageRetrievalCoordinator(
            instance_id, self.rider_principal_id, adapters=self.adapters,
            provider_route=provider_route,
        )
        self.ambiguity_policy = NativeRetrievalAmbiguityPolicy()

    def __call__(self, *, instance_id, user_message, conversation_id,
                 request_message_id, request_timestamp=None, rider_timezone=None,
                 clarification_consumption=None):
        if instance_id != self.instance_id:
            raise PermissionError("foreign_phoenix")
        conversation = tuple(build_archive_context(
            conversation_id, max_messages=self.context_messages
        )) if conversation_id else ()
        conversation = tuple(
            item for item in conversation
            if item.get("message_id") != request_message_id
        )
        excluded = {request_message_id}
        excluded.update(item.get("message_id") for item in conversation)
        context = EvidenceUseContext(
            instance_id=self.instance_id,
            rider_principal_id=self.rider_principal_id,
            capability_id="chat.respond",
            capability_authorized=True,
            provider_mode="configured_external_provider",
            provider_authorized=True,
        )
        plan = self.coordinator.plan(
            user_message, evidence_use_context=context,
            total_budget_chars=self.total_budget_chars,
            limit_per_domain=self.limit_per_domain,
            excluded_evidence_ids=excluded,
            request_timestamp=request_timestamp,
            rider_timezone=(rider_timezone or os.getenv("FAWKES_TIMEZONE")),
        )
        plan["ambiguity_decision"] = self.ambiguity_policy.evaluate(
            instance_id=self.instance_id, rider_principal_id=self.rider_principal_id,
            request_message_id=request_message_id, correlation_id=request_message_id,
            candidate_generation=plan.get("candidate_generation", {}),
            selected_evidence=plan.get("selected_evidence", ()),
            planner_version=plan.get("policy_version"),
            eligibility_policy_version=ELIGIBILITY_POLICY_VERSION,
            retrieval_plan_identity=plan.get("deterministic_replay_input_sha256"),
            query_sha256=hashlib.sha256(user_message.encode()).hexdigest(),
        )
        if clarification_consumption is not None:
            chosen=clarification_consumption["selected_evidence_id"]
            ambiguity_ids=set(clarification_consumption["ambiguity_candidate_evidence_ids"])
            fresh={item.get("evidence_id"):item for item in plan.get("selected_evidence",())}
            if chosen not in fresh:
                raise PermissionError("clarification_candidate_no_longer_eligible_or_available")
            retained=[item for item in plan["selected_evidence"]
                      if item.get("evidence_id") not in ambiguity_ids or item.get("evidence_id")==chosen]
            plan["selected_evidence"]=retained
            for evidence_id in sorted(ambiguity_ids-{chosen}):
                plan.setdefault("exclusions",[]).append({"domain":"native_archive",
                    "stage":"clarification_consumption","reason":"rider_selected_other_ambiguity_choice",
                    "evidence_id":evidence_id})
            if isinstance(plan.get("allocation"),dict):
                used={domain:0 for domain in plan["allocation"].get("per_domain_used",{})}
                for item in retained:
                    if item.get("domain") in used:
                        used[item["domain"]]+=int(item.get("estimated_chars",len(item.get("text",""))))
                plan["allocation"]["per_domain_used"]=used
            plan["clarification_consumption"]={**clarification_consumption,
                "fresh_eligibility_result_identity":hashlib.sha256(json.dumps(
                    fresh[chosen].get("eligibility",{}),sort_keys=True,ensure_ascii=False,
                    separators=(",",":")).encode()).hexdigest(),
                "resulting_evidence_ids":[item["evidence_id"] for item in retained],
                "final_evidence_set_identity":hashlib.sha256(json.dumps(
                    sorted(item["evidence_id"] for item in retained),separators=(",",":")).encode()).hexdigest(),
                "fresh_policy_version":ELIGIBILITY_POLICY_VERSION,
                "fresh_planner_version":plan.get("policy_version"),"status":"consumed"}
            remaining_generation=copy.deepcopy(plan.get("candidate_generation",{}))
            native=remaining_generation.get("native_archive",{})
            resolved_id=clarification_consumption["ambiguity_set_id"]
            native["reference_ambiguity_sets"]=[item for item in native.get("reference_ambiguity_sets",())
                if item.get("ambiguity_set_id")!=resolved_id]
            native["ambiguity_choice_descriptors"]=[item for item in native.get("ambiguity_choice_descriptors",())
                if item.get("ambiguity_set_id")!=resolved_id]
            plan["ambiguity_decision"]=self.ambiguity_policy.evaluate(
                instance_id=self.instance_id,rider_principal_id=self.rider_principal_id,
                request_message_id=request_message_id,correlation_id=request_message_id,
                candidate_generation=remaining_generation,selected_evidence=retained,
                planner_version=plan.get("policy_version"),
                eligibility_policy_version=ELIGIBILITY_POLICY_VERSION,
                retrieval_plan_identity=plan.get("deterministic_replay_input_sha256"),
                query_sha256=hashlib.sha256(user_message.encode()).hexdigest())
            plan["deterministic_replay_input_sha256"]=hashlib.sha256(json.dumps(
                {key:value for key,value in plan.items() if key!="deterministic_replay_input_sha256"},
                sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        plan.update({
            "conversation": conversation,
            "evidence_eligibility_policy_version": ELIGIBILITY_POLICY_VERSION,
            "adapter_versions": {
                adapter.domain_id: adapter.adapter_version for adapter in self.adapters
            },
            "retrieval_audit": {
                "policy_version": plan["policy_version"],
                "evidence_eligibility_policy_version": ELIGIBILITY_POLICY_VERSION,
                "eligible_domains": list(plan["eligible_domains"]),
                "exclusions": list(plan["exclusions"]),
                "allocation": dict(plan["allocation"]),
                "continuity_projections": dict(plan.get("continuity_projections", {})),
                "candidate_generation": dict(plan.get("candidate_generation", {})),
                "representation_preference": dict(plan.get("representation_preference", {})),
                "ambiguity_decision": dict(plan.get("ambiguity_decision", {})),
                "clarification_consumption": dict(plan.get("clarification_consumption", {})),
                "warnings": list(plan["warnings"]),
                "automatic_inherited_history": False,
                "deterministic_replay_input_sha256": plan["deterministic_replay_input_sha256"],
            },
        })
        if plan["policy_version"] != PLANNER_VERSION:
            raise RuntimeError("planner policy version mismatch")
        return plan
