"""Immutable pre-call authorization for exact response-model evidence sets."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import uuid

from src.library.artifacts import require_id
from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_ROOT = ROOT / "database/evidence_transmissions"
SCHEMA_VERSION = 1

EVIDENCE_TRANSMISSION_DEFINITION = CapabilityDefinition(
    name="retrieval.evidence_transmission", version="1.0",
    display_name="Pre-call Evidence Transmission Authorization",
    description="Bind an exact eligible evidence set to one response-provider route before any evidence body is transmitted.",
    effect="immutable_provider_authorization_receipt",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read", "create"), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="content_digests_and_references_only_no_evidence_bodies",
    features=("content_addressed_manifest", "provider_route_binding", "pre_call_permit", "tamper_detection", "empty_set_support"),
    appropriate_use=("authorize selected retrieval evidence for one response-model call",),
    inappropriate_use=("external disclosure authorization", "cross-principal access", "post-call reconstruction"),
    limitations=("served planner Chat is default; explicit legacy mode remains the deterministic rollback",),
    dependencies=("provider-allowed evidence eligibility decisions", "stable evidence references"),
    provenance_requirements=("turn identity", "provider route", "policy versions", "evidence digest", "manifest digest"),
)


def _canonical(value): return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
def _digest(value): return hashlib.sha256(_canonical(value).encode()).hexdigest()


def evidence_body(item, *, allow_missing=False):
    """One exact body across authorization, composition and transmission."""
    if not isinstance(item, dict):
        raise ValueError("evidence body envelope is malformed")
    values = [item[key] for key in ("text", "content") if key in item]
    if not values:
        if allow_missing:
            return ""
        raise ValueError("evidence body is missing")
    if any(not isinstance(value, str) for value in values):
        raise ValueError("evidence body alias is malformed")
    if any(value != values[0] for value in values):
        raise ValueError("evidence body aliases disagree")
    return values[0]


@dataclass(frozen=True)
class ProviderRoute:
    provider_policy_id: str
    provider_class: str
    model: str
    route_version: str = "1"
    def __post_init__(self):
        for value, name in ((self.provider_policy_id,"provider_policy_id"),(self.provider_class,"provider_class"),(self.model,"model"),(self.route_version,"route_version")): require_id(value,name)
    def public(self): return {"provider_policy_id":self.provider_policy_id,"provider_class":self.provider_class,"model":self.model,"route_version":self.route_version}


class EvidenceTransmissionAuthorizer:
    def __init__(self, *, root=None): self.root = Path(root or MANIFEST_ROOT)

    def authorize(self, *, instance_id, rider_principal_id, conversation_id,
                  request_message_id, correlation_id, route, selected_evidence,
                  planner_version, policy_version, adapter_versions):
        for value,name in ((instance_id,"instance_id"),(rider_principal_id,"rider_principal_id"),(conversation_id,"conversation_id"),(request_message_id,"request_message_id"),(correlation_id,"correlation_id"),(planner_version,"planner_version"),(policy_version,"policy_version")): require_id(value,name)
        if not isinstance(route, ProviderRoute): raise TypeError("ProviderRoute is required")
        items=[]; bodies={}
        for evidence in selected_evidence:
            item,body=self._validate_evidence(evidence, instance_id, rider_principal_id, route, policy_version)
            if item["evidence_id"] in bodies: raise ValueError("duplicate evidence identity")
            items.append(item); bodies[item["evidence_id"]]=body
        items.sort(key=lambda x:(x["source_domain"],x["evidence_id"]))
        core={"schema_version":SCHEMA_VERSION,"record_type":"evidence_transmission_manifest",
              "instance_id":instance_id,"rider_principal_id":rider_principal_id,
              "conversation_id":conversation_id,"request_message_id":request_message_id,
              "correlation_id":correlation_id,"provider_route":route.public(),
              "planner_version":planner_version,"evidence_eligibility_policy_version":policy_version,
              "adapter_versions":dict(sorted(adapter_versions.items())),"evidence":items,
              "evidence_set_sha256":_digest(items),"authorization_scope":"this_exact_response_model_transmission_only",
              "grants_external_disclosure":False,"grants_tool_disclosure":False,
              "grants_cross_rider":False,"grants_cross_phoenix":False,"grants_public_disclosure":False}
        manifest_id="evidence-manifest-"+_digest(core)
        manifest={**core,"manifest_id":manifest_id,"created_at":datetime.now(timezone.utc).isoformat()}
        path=self.root/instance_id/f"{manifest_id}.json"
        saved=self._write_once(path,manifest)
        permit=EvidenceTransmissionPermit(saved,bodies,path)
        permit.verify(route=route, selected_evidence=selected_evidence)
        return permit

    def _validate_evidence(self,evidence,instance_id,rider_principal_id,route,policy_version):
        if not isinstance(evidence,dict): raise ValueError("malformed selected evidence")
        if evidence.get("instance_id")!=instance_id: raise PermissionError("foreign_phoenix")
        if evidence.get("owner_principal_id")!=rider_principal_id: raise PermissionError("cross_principal_denied")
        decision=evidence.get("eligibility")
        if not isinstance(decision,dict) or decision.get("instance_id")!=instance_id: raise PermissionError("provider decision missing or mismatched")
        if decision.get("policy_version")!=policy_version: raise PermissionError("provider_decision_policy_mismatch")
        provider=decision.get("provider_transmission",{})
        if provider.get("allowed") is not True: raise PermissionError("provider_transmission_denied")
        decision_route=provider.get("provider_route")
        if decision_route is not None and decision_route!=route.public(): raise PermissionError("provider_route_mismatch")
        if decision.get("selected_for_context") is not True: raise PermissionError("evidence_not_context_eligible")
        reference=evidence.get("original_evidence_reference"); body=evidence_body(evidence)
        if not isinstance(reference,dict) or not reference or not isinstance(body,str): raise ValueError("evidence reference or body is malformed")
        body_sha=hashlib.sha256(body.encode()).hexdigest()
        expected=evidence.get("materialized_sha256")
        if expected is not None and expected!=body_sha: raise ValueError("evidence_digest_mismatch")
        eid=require_id(evidence.get("evidence_id"),"evidence_id")
        return ({"evidence_id":eid,"source_domain":evidence.get("domain"),"authority_class":evidence.get("authority_class"),
                 "native_evidence_identity": evidence.get("native_evidence_identity"),
                 "privacy_classification":decision.get("privacy_classification"),"legacy_compatibility":decision.get("legacy_compatibility"),
                 "adapter_version":evidence.get("adapter_version"),"source_reference":reference,
                 "source_reference_sha256":_digest(reference),"selected_evidence_sha256":body_sha,
                 "provider_decision_allowed":True,"provider_decision_reason":provider.get("reason"),
                 "provider_decision_policy_version":decision.get("policy_version")},body)

    @staticmethod
    def _write_once(path,payload):
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            existing=json.loads(path.read_text())
            if {k:v for k,v in existing.items() if k!="created_at"}!={k:v for k,v in payload.items() if k!="created_at"}: raise ValueError("manifest identity collision")
            return existing
        tmp=path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp"); tmp.write_text(json.dumps(payload,indent=2)+"\n"); tmp.replace(path); return payload


class EvidenceTransmissionPermit:
    def __init__(self,manifest,bodies,path): self.manifest=manifest; self._bodies=dict(bodies); self.path=Path(path)
    def verify(self,*,route,selected_evidence):
        disk=json.loads(self.path.read_text())
        if disk!=self.manifest: raise ValueError("evidence_manifest_tampered")
        core={k:v for k,v in disk.items() if k not in {"manifest_id","created_at"}}
        if disk.get("manifest_id")!="evidence-manifest-"+_digest(core): raise ValueError("evidence_manifest_identity_mismatch")
        if disk.get("provider_route")!=route.public(): raise PermissionError("provider_route_mismatch")
        supplied=[]; seen=set()
        validator=EvidenceTransmissionAuthorizer(root=self.path.parent)
        for evidence in selected_evidence:
            item,_=validator._validate_evidence(evidence,disk["instance_id"],disk["rider_principal_id"],route,disk["evidence_eligibility_policy_version"])
            if item["evidence_id"] in seen: raise ValueError("duplicate evidence identity")
            seen.add(item["evidence_id"]);supplied.append(item)
        supplied.sort(key=lambda item:(item["source_domain"],item["evidence_id"]))
        if supplied!=disk["evidence"]: raise ValueError("evidence_set_or_digest_mismatch")
        return True
    def provider_bodies(self,*,route,selected_evidence): self.verify(route=route,selected_evidence=selected_evidence); return dict(self._bodies)


class ChatRetrievalPathSwitch:
    """Non-mutating immediate rollback: planner failure yields empty evidence."""
    def __init__(self,*,enabled=False): self.enabled=bool(enabled)
    def select(self,*,legacy_builder,planner_builder):
        if not self.enabled: return {"path":"legacy","context":legacy_builder(),"warnings":[]}
        try: return {"path":"planner","context":planner_builder(),"warnings":[]}
        except Exception as exc: return {"path":"planner_degraded_empty","context":{"memories":[],"archive_passages":[],"library_passages":[]},"warnings":[f"planner retrieval unavailable ({type(exc).__name__})"]}
