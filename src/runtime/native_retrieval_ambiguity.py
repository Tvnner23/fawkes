"""Deterministic, body-free rider clarification policy for native retrieval."""

import hashlib
import json
from datetime import datetime


POLICY_VERSION = "native-retrieval-ambiguity-v1"
MATERIAL_BASES = {
    "multiple_recent_conversations_no_reference_resolution",
    "multiple_verified_native_reference_targets",
    "multiple_direct_native_reference_matches",
}
SAFE_JOINT_BASES = {"multiple_temporal_native_anchors_safe_joint_inclusion"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _label(item, ordinal):
    created = item.get("created_at")
    try:
        instant = datetime.fromisoformat(created)
        label = instant.strftime("conversation from %b %-d, %Y at %H:%M %Z").strip()
    except (TypeError, ValueError):
        label = f"matching conversation {ordinal}"
    return label


class NativeRetrievalAmbiguityPolicy:
    version = POLICY_VERSION

    def verify_integrity(self, decision):
        if not isinstance(decision,dict): raise PermissionError("clarification_decision_malformed")
        unsigned={key:value for key,value in decision.items() if key not in {"decision_id","replay_sha256"}}
        expected_id="ambiguity-decision-"+_digest(unsigned)[:24]
        expected_replay=_digest({**unsigned,"decision_id":expected_id})
        if decision.get("decision_id") != expected_id or decision.get("replay_sha256") != expected_replay:
            raise PermissionError("clarification_decision_tampered")
        return True

    def evaluate(self, *, instance_id, rider_principal_id, request_message_id,
                 correlation_id, candidate_generation, selected_evidence,
                 planner_version=None, eligibility_policy_version=None,
                 retrieval_plan_identity=None, query_sha256=None):
        native = (candidate_generation or {}).get("native_archive", {})
        sets = sorted(native.get("reference_ambiguity_sets", ()),
                      key=lambda item: str(item.get("ambiguity_set_id")))
        descriptors={item.get("ambiguity_set_id"):item.get("choices",())
                     for item in native.get("ambiguity_choice_descriptors",())
                     if isinstance(item,dict)}
        selected = {item.get("evidence_id"): item for item in selected_evidence
                    if item.get("domain") == "native_archive"}
        decisions = []
        for ambiguity in sets:
            ambiguity_id = ambiguity.get("ambiguity_set_id")
            eligible_descriptors={item.get("evidence_id"):item for item in descriptors.get(ambiguity_id,())
                                  if isinstance(item,dict) and item.get("evidence_id")}
            ids = tuple(sorted(eligible_descriptors))
            if not ambiguity_id or len(ids) < 2:
                continue
            choices = []
            for ordinal, evidence_id in enumerate(ids, 1):
                item = {**eligible_descriptors[evidence_id], **selected.get(evidence_id, {})}
                identity = {"ambiguity_set_id":ambiguity_id,"evidence_id":evidence_id,
                            "instance_id":instance_id,"request_message_id":request_message_id}
                choices.append({"choice_id":"clarification-choice-"+_digest(identity)[:24],
                                "evidence_id":evidence_id,"label":_label(item, ordinal),
                                "selected_by_plan":evidence_id in selected})
            basis = ambiguity.get("basis", "unspecified_native_ambiguity")
            all_included = all(choice["selected_by_plan"] for choice in choices)
            required = basis in MATERIAL_BASES or not (basis in SAFE_JOINT_BASES and all_included)
            decisions.append({"ambiguity_set_id":ambiguity_id,"basis":basis,
                              "clarification_required":required,
                              "decision_reason":("materially_distinct_native_interpretations"
                                  if required else "bounded_joint_inclusion_preserves_meaning"),
                              "choices":choices})
        envelope = {"schema_version":1,"record_type":"native_retrieval_ambiguity_decision",
                    "policy_version":self.version,"instance_id":instance_id,
                    "rider_principal_id":rider_principal_id,
                    "request_message_id":request_message_id,"correlation_id":correlation_id,
                    "planner_version":planner_version,
                    "eligibility_policy_version":eligibility_policy_version,
                    "resulting_retrieval_plan_identity":retrieval_plan_identity,
                    "query_sha256":query_sha256,
                    "ambiguity_sets":decisions,
                    "clarification_required":any(x["clarification_required"] for x in decisions),
                    "sensitive_content_logged":False,"authorization_granted":False,
                    "automatic_inherited_history":False}
        envelope["decision_id"]="ambiguity-decision-"+_digest(envelope)[:24]
        envelope["replay_sha256"]=_digest(envelope)
        return envelope

    def question(self, decision):
        self.verify_integrity(decision)
        required = next((item for item in decision.get("ambiguity_sets", ())
                         if item.get("clarification_required")), None)
        if required is None: return None
        labels = [choice["label"] for choice in required["choices"]]
        if len(labels) == 2:
            options = f"{labels[0]} or {labels[1]}"
        else:
            options = ", ".join(labels[:-1]) + f", or {labels[-1]}"
        return f"I found {len(labels)} possibilities that could change the answer: {options}. Which one do you mean?"

    def validate_selection(self, decision, response, *, instance_id,
                           rider_principal_id, originating_request_message_id,
                           correlation_id):
        self.verify_integrity(decision)
        expected=(instance_id,rider_principal_id,originating_request_message_id,correlation_id)
        actual=(decision.get("instance_id"),decision.get("rider_principal_id"),
                decision.get("request_message_id"),decision.get("correlation_id"))
        if actual != expected: raise PermissionError("clarification_scope_or_turn_mismatch")
        ambiguity_id=response.get("ambiguity_set_id") if isinstance(response,dict) else None
        choice_id=response.get("choice_id") if isinstance(response,dict) else None
        matched=next((item for item in decision.get("ambiguity_sets",())
                      if item.get("ambiguity_set_id")==ambiguity_id),None)
        if matched is None: raise PermissionError("clarification_ambiguity_mismatch")
        choice=next((item for item in matched.get("choices",())
                    if item.get("choice_id")==choice_id),None)
        if choice is None: raise PermissionError("clarification_choice_mismatch")
        return {"policy_version":self.version,"decision_id":decision["decision_id"],
                "ambiguity_set_id":ambiguity_id,"choice_id":choice_id,
                "selected_evidence_id":choice["evidence_id"],
                "authorization_granted":False,"scope_validated":True}
