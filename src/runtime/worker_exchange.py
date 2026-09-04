"""Transport-neutral, zero-authority Phoenix Worker Exchange foundation."""

from datetime import datetime, timezone
from pathlib import Path
import base64
import hashlib
import json
import uuid
import zlib

from src.capabilities.core import CapabilityDefinition
from src.library.artifacts import require_id


ROOT = Path(__file__).resolve().parent.parent.parent
EXCHANGE_ROOT = ROOT / "database" / "worker_exchange"
POLICY_VERSION = "phoenix-worker-exchange-v0.1"
REVOCATION_POLICY_VERSION = "worker-exchange-transport-revocation-v1"
REPORT_SCHEMA_VERSION = 1
PACKAGE_SCHEMA_VERSION = 1
VERIFICATION_STATUSES = {"accepted", "accepted_with_caveats", "unverified", "disputed", "insufficient"}
IDENTITY_STATUSES = {"verified", "rider_attested", "unverified"}
MATURITY_STATES = {"live", "improved", "in_development", "experimental", "approved_direction",
                   "proposed", "discovered", "deprecated", "removed", "blocked"}
CHANGE_CLASSES = {"personal_candidate", "software_system", "external_discovery"}
BODY_KEYS = {"body", "content", "text", "payload", "raw"}
REVOCATION_REASONS = {"rider_revoked", "scope_withdrawn", "security_response"}

TRANSPORT_REVOCATION_ACCEPTANCE_CONTRACT = {
    "contract_version": REVOCATION_POLICY_VERSION,
    "scope": "one existing Worker Exchange transport authorization reference",
    "hard_invariants": (
        "valid_nonexpired_authorization_works_before_revocation",
        "authorized_revocation_is_durable_attributable_and_integrity_bound",
        "future_use_fails_closed_after_revocation",
        "replay_and_resealed_payload_cannot_bypass_revocation",
        "historical_receipts_and_results_remain_unchanged",
        "wrong_phoenix_scope_and_authorization_cannot_revoke_unrelated_authority",
        "identical_revocation_is_idempotent",
        "expiry_and_revocation_remain_distinct",
        "revocation_creates_no_authority",
        "no_worker_orchestration_authority_is_created",
    ),
    "rider_authority_required": True,
    "retroactive_history_mutation": False,
}

WORKER_EXCHANGE_DEFINITION = CapabilityDefinition(
    name="worker.exchange", version="0.1",
    display_name="Phoenix Worker Exchange Foundation",
    description="Preserve scoped worker reports and verified-handoff evidence without transporting or authorizing workers.",
    permissions=("worker_exchange.record",), effect="create_communication_evidence",
    privacy_handling="Phoenix/task/recipient scoped; report content is untrusted data",
    features=("immutable_source_reports", "least_necessary_packages", "explicit_omissions",
              "delivery_verification_separation", "disagreement_preservation", "return_report_lineage"),
    appropriate_use=("prepare a source-preserving package for an already-approved worker",),
    inappropriate_use=("discover or assign workers", "grant authority", "claim delivery through an unqualified adapter", "promote worker claims"),
    limitations=("one promoted Codex adapter; no Blender adapter", "no Worker Pulse or Board",
                 "manual rider fallback remains required"),
    dependencies=("Universal Worker Charter", "upstream task and transmission authorization", "Phase 0 recovery"),
    provenance_requirements=("Phoenix instance", "task scope", "sender and recipient", "source report digest"),
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _body_free(value):
    if isinstance(value, dict):
        if any(str(key).lower() in BODY_KEYS for key in value):
            raise ValueError("reference metadata must remain body-free")
        return {str(key): _body_free(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_body_free(item) for item in value]
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    raise ValueError("reference metadata must be JSON-compatible")


def body_free_references(value):
    """Public validation seam for consumers composing Exchange references."""
    return _body_free(value)


def _worker(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} worker reference is required")
    worker_id = require_id(value.get("worker_id"), f"{label}_worker_id")
    role = require_id(value.get("role"), f"{label}_role")
    identity_status = value.get("identity_status")
    if identity_status not in IDENTITY_STATUSES:
        raise ValueError("invalid worker identity status")
    charter_version = require_id(value.get("charter_version"), "charter_version")
    return {"worker_id": worker_id, "role": role, "identity_status": identity_status,
            "charter_version": charter_version, "descriptive_only_no_authority": True}


def _authority(value, *, instance_id, task_scope_id, sender_id, recipient_id=None):
    if not isinstance(value, dict) or value.get("decision") != "authorized":
        raise PermissionError("upstream Exchange authority is required")
    expected = {"instance_id": instance_id, "task_scope_id": task_scope_id,
                "sender_worker_id": sender_id}
    if recipient_id is not None:
        expected["recipient_worker_id"] = recipient_id
    if any(value.get(key) != item for key, item in expected.items()):
        raise PermissionError("Exchange authority scope mismatch")
    reference = require_id(value.get("authorization_reference"), "authorization_reference")
    expires_at = value.get("expires_at")
    if expires_at is not None:
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise PermissionError("Exchange authority expiry is invalid") from exc
        if expiry <= datetime.now(timezone.utc):
            raise PermissionError("Exchange authority is expired")
    return {**expected, "decision": "authorized", "authorization_reference": reference,
            "expires_at": expires_at, "creates_authority": False}


class WorkerExchange:
    """Local semantics/evidence core. It never sends a package anywhere."""

    def __init__(self, instance_id, *, root=None):
        self.instance_id = require_id(instance_id, "instance_id")
        base = Path(root) if root is not None else EXCHANGE_ROOT
        self.root = base / self.instance_id

    def _path(self, kind, record_id):
        return self.root / kind / f"{require_id(record_id, f'{kind}_id')}.json"

    def _write_once(self, kind, record):
        identity_keys = {"reports": "report_id", "packages": "package_id",
                         "delivery_receipts": "delivery_receipt_id",
                         "verification_receipts": "verification_receipt_id",
                         "authorization_revocations": "revocation_id"}
        path = self._path(kind, record[identity_keys[kind]])
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            ignored = {"created_at", "record_sha256"}
            if kind == "reports": ignored.add("content_sha256")
            comparable_existing = {key: value for key, value in existing.items() if key not in ignored}
            comparable_record = {key: value for key, value in record.items() if key not in ignored}
            if comparable_existing != comparable_record:
                raise ValueError("Exchange identity already exists with different data")
            return existing
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)
        return record

    def _load(self, kind, record_id):
        path = self._path(kind, record_id)
        if not path.exists():
            raise KeyError(f"Exchange {kind} record not found")
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("instance_id") != self.instance_id:
            raise PermissionError("Exchange record belongs to another Phoenix")
        claimed = value.get("record_sha256")
        if claimed != _digest({key: item for key, item in value.items() if key != "record_sha256"}):
            raise ValueError("Exchange record integrity mismatch")
        return value

    @staticmethod
    def _transport_authorization_id(instance_id, authorization_reference):
        return "transport-authorization-" + _digest({
            "instance_id": require_id(instance_id, "instance_id"),
            "authorization_reference": require_id(authorization_reference, "authorization_reference"),
        })

    def _revocation_for(self, authorization_id):
        path = self._path("authorization_revocations", authorization_id)
        if not path.exists():
            return None
        return self._load("authorization_revocations", authorization_id)

    def transport_authorization_status(self, *, package_id, authority):
        """Return current local usability without rewriting historical evidence."""
        try:
            package = self._load("packages", package_id)
            if not isinstance(authority, dict) or authority.get("decision") != "authorized":
                raise PermissionError("transport authorization is invalid")
            expected = {"instance_id": self.instance_id, "task_scope_id": package["task_scope_id"],
                "sender_worker_id": package["sender"]["worker_id"],
                "recipient_worker_id": package["recipient"]["worker_id"]}
            if any(authority.get(key) != value for key, value in expected.items()):
                raise PermissionError("transport authorization scope mismatch")
            reference = require_id(authority.get("authorization_reference"), "authorization_reference")
            if package["recipient_authorization_reference"] != reference:
                raise PermissionError("transport authorization reference mismatch")
            authorization_id = self._transport_authorization_id(self.instance_id, reference)
        except (KeyError, TypeError, ValueError, PermissionError):
            return {"status": "invalid", "authorization_id": None, "revocation_id": None,
                    "creates_authority": False}
        revocation = self._revocation_for(authorization_id)
        if revocation is not None:
            return {"status": "revoked", "authorization_id": authorization_id,
                    "revocation_id": revocation["revocation_id"], "revoked_at": revocation["revoked_at"],
                    "creates_authority": False}
        try:
            expiry = datetime.fromisoformat(authority.get("expires_at").replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            return {"status": "invalid", "authorization_id": authorization_id,
                    "revocation_id": None, "creates_authority": False}
        if expiry <= datetime.now(timezone.utc):
            return {"status": "expired", "authorization_id": authorization_id,
                    "revocation_id": None, "creates_authority": False}
        return {"status": "valid", "authorization_id": authorization_id,
                "revocation_id": None, "creates_authority": False}

    def validate_transport_authorization(self, *, package_id, authority):
        package = self._load("packages", package_id)
        status = self.transport_authorization_status(package_id=package_id, authority=authority)
        if status["status"] == "revoked":
            raise PermissionError("transport authorization is revoked")
        if status["status"] == "expired":
            raise PermissionError("transport authorization is expired")
        if status["status"] != "valid":
            raise PermissionError("transport authorization is invalid")
        try:
            auth = _authority(authority, instance_id=self.instance_id,
                task_scope_id=package["task_scope_id"], sender_id=package["sender"]["worker_id"],
                recipient_id=package["recipient"]["worker_id"])
        except PermissionError as exc:
            if "expired" in str(exc):
                raise PermissionError("transport authorization is expired") from exc
            raise
        if package["recipient_authorization_reference"] != auth["authorization_reference"]:
            raise PermissionError("transport authorization reference mismatch")
        authorization_id = status["authorization_id"]
        return {**auth, "authorization_id": authorization_id, "status": "valid",
                "revocation_checked": True, "creates_authority": False}

    def revoke_transport_authorization(self, *, package_id, target_authorization,
                                       revocation_authority, reason="rider_revoked"):
        """Append one rider-authorized revocation for an existing transport grant."""
        package = self._load("packages", package_id)
        status = self.transport_authorization_status(package_id=package_id, authority=target_authorization)
        if status["status"] == "invalid":
            raise PermissionError("transport authorization is invalid")
        if status["status"] == "expired":
            raise PermissionError("transport authorization is expired")
        target = {"authorization_reference": package["recipient_authorization_reference"],
                  "authorization_id": status["authorization_id"]}
        if reason not in REVOCATION_REASONS:
            raise ValueError("invalid transport revocation reason")
        expected = {
            "decision": "authorized",
            "operation": "worker_exchange.transport_authorization.revoke",
            "authority_class": "rider",
            "instance_id": self.instance_id,
            "task_scope_id": package["task_scope_id"],
            "target_authorization_id": target["authorization_id"],
            "target_authorization_reference": target["authorization_reference"],
        }
        if not isinstance(revocation_authority, dict) or any(
                revocation_authority.get(key) != value for key, value in expected.items()):
            raise PermissionError("rider-scoped transport revocation authority is required")
        principal_id = require_id(revocation_authority.get("revoking_principal_id"), "revoking_principal_id")
        approval_reference = require_id(
            revocation_authority.get("authorization_reference"), "revocation_authorization_reference")
        expires_at = revocation_authority.get("expires_at")
        try:
            approval_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise PermissionError("revocation authority expiry is invalid") from exc
        if approval_expiry <= datetime.now(timezone.utc):
            raise PermissionError("revocation authority is expired")
        scope = {
            "instance_id": self.instance_id,
            "task_scope_id": package["task_scope_id"],
            "sender_worker_id": package["sender"]["worker_id"],
            "recipient_worker_id": package["recipient"]["worker_id"],
            "originating_package_id": package_id,
            "adapter_id": target_authorization.get("adapter_id"),
            "recipient_environment_id": target_authorization.get("recipient_environment_id"),
        }
        existing = self._revocation_for(target["authorization_id"])
        if existing is not None:
            expected_existing = {"target_authorization_reference": target["authorization_reference"],
                "target_scope": scope, "revoking_principal_id": principal_id,
                "revocation_authorization_reference": approval_reference, "reason": reason}
            if any(existing.get(key) != value for key, value in expected_existing.items()):
                raise ValueError("transport authorization already has different revocation evidence")
            return existing
        revocation_id = target["authorization_id"]
        payload = {"schema_version": 1, "record_type": "worker_exchange_transport_authorization_revocation",
            "policy_version": REVOCATION_POLICY_VERSION, "instance_id": self.instance_id,
            "revocation_id": revocation_id, "target_authorization_id": target["authorization_id"],
            "target_authorization_reference": target["authorization_reference"], "target_scope": scope,
            "revoking_principal_id": principal_id, "revocation_authorization_reference": approval_reference,
            "authority_class": "rider", "reason": reason, "revoked_at": _now(),
            "future_use_blocked": True, "historical_evidence_rewritten": False,
            "creates_authority": False, "worker_self_revocation_authorized": False}
        record = {**payload}
        record["record_sha256"] = _digest(record)
        return self._write_once("authorization_revocations", record)

    def create_report(self, *, task_scope_id, sender, authority, sections, claims=(),
                      artifact_references=(), evidence_references=(), contract_references=(),
                      recovery_references=(), report_version="1", media_type="application/vnd.fawkes.worker-report+json",
                      in_reply_to=None):
        task_scope_id = require_id(task_scope_id, "task_scope_id")
        sender = _worker(sender, "sender")
        authority = _authority(authority, instance_id=self.instance_id, task_scope_id=task_scope_id,
                               sender_id=sender["worker_id"])
        if not isinstance(sections, (list, tuple)) or not sections:
            raise ValueError("at least one report section is required")
        normalized, seen = [], set()
        for section in sections:
            if not isinstance(section, dict): raise ValueError("report section must be an object")
            section_id = require_id(section.get("section_id"), "section_id")
            if section_id in seen: raise ValueError("report section identities must be unique")
            seen.add(section_id)
            title, content = section.get("title"), section.get("content")
            if not isinstance(title, str) or not title.strip() or not isinstance(content, str):
                raise ValueError("report section title and content are required")
            normalized.append({"section_id": section_id, "title": title.strip(), "content": content,
                               "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                               "byte_length": len(content.encode())})
        normalized_claims, claim_ids = [], set()
        for claim in claims:
            if not isinstance(claim, dict): raise ValueError("claim must be an object")
            maturity = claim.get("maturity")
            if maturity not in MATURITY_STATES: raise ValueError("invalid asserted maturity")
            claim_id = require_id(claim.get("claim_id"), "claim_id")
            if claim_id in claim_ids: raise ValueError("claim identities must be unique")
            claim_ids.add(claim_id)
            statement = claim.get("statement")
            if not isinstance(statement, str) or not statement.strip(): raise ValueError("claim statement is required")
            change_class = claim.get("change_class", "software_system")
            if change_class not in CHANGE_CLASSES: raise ValueError("invalid change class")
            normalized_claims.append({"claim_id": claim_id,
                "area": require_id(claim.get("area"), "claim_area"), "statement": statement.strip(),
                "change_class": change_class, "maturity": maturity,
                "verification_state": "worker_asserted_unverified", "creates_project_truth": False,
                "evidence_references": _body_free(claim.get("evidence_references", []))})
        reply = _body_free(in_reply_to) if in_reply_to is not None else None
        payload = {"schema_version": REPORT_SCHEMA_VERSION, "record_type": "worker_source_report",
            "policy_version": POLICY_VERSION, "instance_id": self.instance_id, "task_scope_id": task_scope_id,
            "sender": sender, "authority_reference": authority["authorization_reference"],
            "report_version": require_id(report_version, "report_version"), "media_type": str(media_type),
            "sections": normalized, "claims": normalized_claims,
            "artifact_references": _body_free(artifact_references), "evidence_references": _body_free(evidence_references),
            "contract_references": _body_free(contract_references), "recovery_references": _body_free(recovery_references),
            "in_reply_to": reply, "trust": "untrusted_worker_report_data",
            "instruction_authority": False, "creates_authority": False}
        report_id = "worker-report-" + _digest(payload)
        record = {**payload, "report_id": report_id, "content_sha256": _digest(payload), "created_at": _now()}
        record["record_sha256"] = _digest(record)
        return self._write_once("reports", record)

    def compose_package(self, *, report_id, recipient, authority, included_section_ids,
                        composition_purpose="specialist_handoff", composition_profile_version="1",
                        summary=None, summary_processor=None):
        report = self._load("reports", report_id)
        recipient = _worker(recipient, "recipient")
        auth = _authority(authority, instance_id=self.instance_id, task_scope_id=report["task_scope_id"],
                          sender_id=report["sender"]["worker_id"], recipient_id=recipient["worker_id"])
        requested = list(dict.fromkeys(included_section_ids or ()))
        available = {item["section_id"]: item for item in report["sections"]}
        if not requested or any(item not in available for item in requested):
            raise ValueError("package sections must resolve exactly to the source report")
        included = [available[item] for item in requested]
        omitted = [item["section_id"] for item in report["sections"] if item["section_id"] not in requested]
        derived_summary = None
        if summary is not None:
            if not isinstance(summary, str) or not summary_processor:
                raise ValueError("derived summary requires text and attributed processor")
            derived_summary = {"text": summary, "sha256": hashlib.sha256(summary.encode()).hexdigest(),
                               "derived": True, "authoritative": False,
                               "source_section_ids": requested, "semantic_equivalence_claimed": False,
                               "source_discrepancy_status": "not_evaluated",
                               "processor": _body_free(summary_processor)}
        payload = {"schema_version": PACKAGE_SCHEMA_VERSION, "record_type": "worker_exchange_package",
            "policy_version": POLICY_VERSION, "instance_id": self.instance_id,
            "task_scope_id": report["task_scope_id"], "sender": report["sender"], "recipient": recipient,
            "recipient_authorization_reference": auth["authorization_reference"],
            "authority_expires_at": auth.get("expires_at"), "source_report_id": report_id,
            "source_report_sha256": report.get("content_sha256", report["report_id"].removeprefix("worker-report-")),
            "source_report_version": report["report_version"],
            "composition_purpose": require_id(composition_purpose, "composition_purpose"),
            "composition_profile_version": require_id(composition_profile_version, "composition_profile_version"),
            "included_sections": included, "included_section_ids": requested, "omitted_section_ids": omitted,
            "source_section_count": len(report["sections"]), "included_byte_length": sum(x["byte_length"] for x in included),
            "source_byte_length": sum(x["byte_length"] for x in report["sections"]),
            "truncated": False, "truncation_detectable": True, "derived_summary": derived_summary,
            "source_fidelity_policy_version": "worker-exchange-source-fidelity-v1",
            "material_reliance_requires_exact_source": True, "summary_may_replace_source": False,
            "claims": report["claims"], "artifact_references": report["artifact_references"],
            "evidence_references": report["evidence_references"], "contract_references": report["contract_references"],
            "recovery_references": report["recovery_references"], "source_lineage": [report_id],
            "in_reply_to": report.get("in_reply_to"), "trust": "untrusted_worker_content_data_only",
            "instruction_authority": False, "creates_authority": False, "forwarding_allowed": False,
            "manual_transfer_retirement_eligible": False, "real_adapter_qualified": False,
            "qualification_contract_version": "worker-exchange-qualification-future-v1"}
        package_id = "worker-package-" + _digest(payload)
        record = {**payload, "package_id": package_id, "created_at": _now()}
        record["record_sha256"] = _digest(record)
        return self._write_once("packages", record)

    def export_package(self, package_id):
        return (_canonical(self._load("packages", package_id)) + "\n").encode()

    def export_package_transport(self, package_id, *, max_transport_bytes,
                                 max_resolved_bytes):
        """Losslessly transport one immutable package without changing its identity."""
        logical = self.export_package(package_id)
        if len(logical) > max_resolved_bytes:
            raise ValueError("resolved Exchange package exceeds byte limit")
        if len(logical) <= max_transport_bytes:
            return logical
        compressed = zlib.compress(logical, level=9)
        payload = {"schema_version": 1,
            "record_type": "worker_exchange_package_transport",
            "encoding": "zlib-base64-v1", "package_id": package_id,
            "resolved_byte_length": len(logical),
            "resolved_sha256": hashlib.sha256(logical).hexdigest(),
            "compressed_byte_length": len(compressed),
            "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
            "body": base64.b64encode(compressed).decode("ascii"),
            "creates_authority": False}
        envelope = {**payload, "record_sha256": _digest(payload)}
        transported = (_canonical(envelope) + "\n").encode()
        if len(transported) > max_transport_bytes:
            raise ValueError("transported Exchange package exceeds byte limit")
        return transported

    @staticmethod
    def resolve_package_transport(data, *, max_transport_bytes,
                                  max_resolved_bytes):
        """Resolve an exact bounded transport envelope to the original package bytes."""
        transported = bytes(data)
        if len(transported) > max_transport_bytes:
            raise ValueError("transported Exchange package exceeds byte limit")
        try:
            value = json.loads(transported.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError("Exchange package transport encoding is invalid") from exc
        if value.get("record_type") == "worker_exchange_package":
            if len(transported) > max_resolved_bytes:
                raise ValueError("resolved Exchange package exceeds byte limit")
            return transported
        expected_keys = {"schema_version", "record_type", "encoding", "package_id",
            "resolved_byte_length", "resolved_sha256", "compressed_byte_length",
            "compressed_sha256", "body", "creates_authority", "record_sha256"}
        if (set(value) != expected_keys or value.get("schema_version") != 1
                or value.get("record_type") != "worker_exchange_package_transport"
                or value.get("encoding") != "zlib-base64-v1"
                or value.get("creates_authority") is not False
                or value.get("record_sha256") != _digest(
                    {key: item for key, item in value.items() if key != "record_sha256"})):
            raise ValueError("Exchange package transport integrity mismatch")
        if (not isinstance(value.get("resolved_byte_length"), int)
                or value["resolved_byte_length"] < 0
                or value["resolved_byte_length"] > max_resolved_bytes):
            raise ValueError("resolved Exchange package exceeds byte limit")
        try:
            compressed = base64.b64decode(value["body"], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("Exchange package transport body is invalid") from exc
        if (len(compressed) != value.get("compressed_byte_length")
                or hashlib.sha256(compressed).hexdigest() != value.get("compressed_sha256")):
            raise ValueError("Exchange package transport body mismatch")
        decoder = zlib.decompressobj()
        logical = decoder.decompress(compressed, max_resolved_bytes + 1)
        if (len(logical) > max_resolved_bytes or decoder.unconsumed_tail
                or not decoder.eof or decoder.unused_data):
            raise ValueError("resolved Exchange package is invalid or oversized")
        logical += decoder.flush()
        if (len(logical) != value["resolved_byte_length"]
                or hashlib.sha256(logical).hexdigest() != value["resolved_sha256"]):
            raise ValueError("resolved Exchange package identity mismatch")
        try:
            package = json.loads(logical.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("resolved Exchange package encoding is invalid") from exc
        if package.get("package_id") != value.get("package_id"):
            raise ValueError("resolved Exchange package identity mismatch")
        return logical

    @staticmethod
    def verify_export(data, *, expected_instance_id, expected_task_scope_id, expected_recipient_id,
                      expected_package_id, expected_source_report, expected_authorization_reference):
        try: value = json.loads(bytes(data).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError("Exchange package encoding is invalid") from exc
        claimed = value.get("record_sha256")
        if claimed != _digest({key: item for key, item in value.items() if key != "record_sha256"}):
            raise ValueError("Exchange package integrity mismatch")
        package_payload = {key: item for key, item in value.items()
                           if key not in {"package_id", "created_at", "record_sha256"}}
        if (value.get("package_id") != expected_package_id
                or value.get("package_id") != "worker-package-" + _digest(package_payload)):
            raise ValueError("Exchange package content identity mismatch")
        if not isinstance(expected_source_report, dict):
            raise ValueError("exact source report is required for export verification")
        expected_report_id = expected_source_report.get("report_id")
        expected_report_digest = _digest({key: item for key, item in expected_source_report.items()
                                          if key != "record_sha256"})
        if expected_source_report.get("record_sha256") != expected_report_digest:
            raise ValueError("exact source report integrity mismatch")
        if value.get("source_report_id") != expected_report_id:
            raise ValueError("Exchange source report identity mismatch")
        if value.get("source_report_sha256") != expected_report_id.removeprefix("worker-report-"):
            raise ValueError("Exchange source report digest mismatch")
        if value.get("recipient_authorization_reference") != expected_authorization_reference:
            raise PermissionError("Exchange package authorization reference mismatch")
        if (value.get("instance_id") != expected_instance_id or value.get("task_scope_id") != expected_task_scope_id
                or (value.get("recipient") or {}).get("worker_id") != expected_recipient_id):
            raise PermissionError("Exchange package recipient or scope mismatch")
        if value.get("truncated") or len(value.get("included_section_ids", ())) + len(value.get("omitted_section_ids", ())) != value.get("source_section_count"):
            raise ValueError("Exchange package is partial or silently truncated")
        included = value.get("included_section_ids", ())
        omitted = value.get("omitted_section_ids", ())
        if len(set(included)) != len(included) or len(set(omitted)) != len(omitted) or set(included) & set(omitted):
            raise ValueError("Exchange package section accounting is invalid")
        actual = [item.get("section_id") for item in value.get("included_sections", ())]
        if actual != included:
            raise ValueError("Exchange package included section identity mismatch")
        source_sections = expected_source_report.get("sections")
        if not isinstance(source_sections, list) or not source_sections:
            raise ValueError("exact source report sections are missing")
        source_by_id = {item.get("section_id"): item for item in source_sections}
        expected_omitted = [item["section_id"] for item in source_sections if item["section_id"] not in included]
        if (not included or len(source_by_id) != len(source_sections)
                or any(item not in source_by_id for item in included)
                or list(omitted) != expected_omitted
                or value.get("source_section_count") != len(source_sections)):
            raise ValueError("Exchange source section resolution mismatch")
        if value.get("included_sections") != [source_by_id[item] for item in included]:
            raise ValueError("Exchange exact source section substitution detected")
        included_byte_length = 0
        for section in value.get("included_sections", ()):
            content = section.get("content")
            if not isinstance(content, str):
                raise ValueError("Exchange source section content is invalid")
            encoded = content.encode()
            if section.get("content_sha256") != hashlib.sha256(encoded).hexdigest():
                raise ValueError("Exchange source section digest mismatch")
            if section.get("byte_length") != len(encoded):
                raise ValueError("Exchange source section byte length mismatch")
            included_byte_length += len(encoded)
        if value.get("included_byte_length") != included_byte_length:
            raise ValueError("Exchange included byte accounting mismatch")
        exact_source_length = sum(item["byte_length"] for item in source_sections)
        if value.get("source_byte_length") != exact_source_length:
            raise ValueError("Exchange source byte accounting mismatch")
        summary = value.get("derived_summary")
        if summary is not None:
            if (not isinstance(summary, dict) or summary.get("derived") is not True
                    or summary.get("authoritative") is not False or not isinstance(summary.get("text"), str)
                    or summary.get("sha256") != hashlib.sha256(summary["text"].encode()).hexdigest()
                    or summary.get("source_section_ids") != included
                    or summary.get("semantic_equivalence_claimed") is not False
                    or summary.get("source_discrepancy_status") != "not_evaluated"):
                raise ValueError("Exchange derived summary integrity mismatch")
        if (value.get("material_reliance_requires_exact_source") is not True
                or value.get("summary_may_replace_source") is not False
                or value.get("instruction_authority") is not False
                or value.get("creates_authority") is not False
                or value.get("manual_transfer_retirement_eligible") is not False
                or value.get("real_adapter_qualified") is not False):
            raise ValueError("Exchange source-fidelity policy mismatch")
        expires_at = value.get("authority_expires_at")
        if expires_at is not None:
            try:
                expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except (AttributeError, ValueError) as exc:
                raise PermissionError("Exchange package authority expiry is invalid") from exc
            if expiry <= datetime.now(timezone.utc):
                raise PermissionError("Exchange package authority is expired")
        return value

    def record_delivery(self, *, package_id, authority, adapter_id, adapter_version, status,
                        delivery_reference=None, failure_reason=None):
        package = self._load("packages", package_id)
        auth = _authority(authority, instance_id=self.instance_id, task_scope_id=package["task_scope_id"],
                          sender_id=package["sender"]["worker_id"], recipient_id=package["recipient"]["worker_id"])
        if status not in {"delivered", "failed"}: raise ValueError("invalid delivery status")
        if status == "delivered" and not delivery_reference:
            raise ValueError("successful delivery requires a delivery reference")
        if status == "failed" and not failure_reason:
            raise ValueError("failed delivery requires a failure reason")
        payload = {"schema_version": 1, "record_type": "worker_exchange_delivery_receipt",
            "policy_version": POLICY_VERSION, "instance_id": self.instance_id, "task_scope_id": package["task_scope_id"],
            "package_id": package_id, "package_sha256": package["record_sha256"], "sender": package["sender"],
            "recipient": package["recipient"], "authorization_reference": auth["authorization_reference"],
            "adapter_id": require_id(adapter_id, "adapter_id"), "adapter_version": require_id(adapter_version, "adapter_version"),
            "delivery_reference": delivery_reference, "status": status, "failure_reason": failure_reason,
            "verified": False, "approved": False, "promoted": False, "creates_authority": False}
        receipt_id = "delivery-receipt-" + _digest(payload)
        record = {**payload, "delivery_receipt_id": receipt_id, "created_at": _now()}
        record["record_sha256"] = _digest(record)
        return self._write_once("delivery_receipts", record)

    def record_verification(self, *, package_id, recipient, authority, status, checked_claim_ids,
                            evidence_references, method, material_reliance=False,
                            relied_source_section_ids=(), caveats=(), counterclaim=None):
        package = self._load("packages", package_id)
        recipient = _worker(recipient, "recipient")
        if recipient["worker_id"] != package["recipient"]["worker_id"]: raise PermissionError("verification recipient mismatch")
        auth = _authority(authority, instance_id=self.instance_id, task_scope_id=package["task_scope_id"],
                          sender_id=package["sender"]["worker_id"], recipient_id=recipient["worker_id"])
        if status not in VERIFICATION_STATUSES: raise ValueError("invalid verification status")
        known = {item["claim_id"] for item in package["claims"]}
        checked = list(dict.fromkeys(checked_claim_ids or ()))
        if any(item not in known for item in checked): raise ValueError("verification references an unknown claim")
        if material_reliance and not checked:
            raise ValueError("material reliance requires checked claims")
        relied_ids = list(dict.fromkeys(relied_source_section_ids or ()))
        included = {item["section_id"]: item for item in package["included_sections"]}
        if any(item not in included for item in relied_ids):
            raise ValueError("relied source must be an exact included source section")
        if material_reliance and not relied_ids:
            raise ValueError("material reliance requires exact relied source sections")
        exact_sources = [{"source_report_id": package["source_report_id"], "section_id": item,
                          "content_sha256": included[item]["content_sha256"],
                          "byte_length": included[item]["byte_length"], "source_type": "exact_report_section"}
                         for item in relied_ids]
        if not isinstance(method, str) or not method.strip():
            raise ValueError("verification method is required")
        caveats = [str(item) for item in caveats]
        if status == "accepted_with_caveats" and not caveats: raise ValueError("caveated acceptance requires caveats")
        if status == "disputed" and not isinstance(counterclaim, dict): raise ValueError("dispute requires a counterclaim")
        payload = {"schema_version": 1, "record_type": "worker_exchange_verification_receipt",
            "policy_version": POLICY_VERSION, "instance_id": self.instance_id, "task_scope_id": package["task_scope_id"],
            "package_id": package_id, "source_report_id": package["source_report_id"], "recipient": recipient,
            "authorization_reference": auth["authorization_reference"], "status": status,
            "checked_claim_ids": checked, "evidence_references": _body_free(evidence_references),
            "method": method.strip(), "material_reliance": bool(material_reliance),
            "relied_exact_sources": exact_sources, "derived_summary_used_as_source": False,
            "source_fidelity_policy_version": package["source_fidelity_policy_version"], "caveats": caveats,
            "counterclaim": _body_free(counterclaim) if counterclaim is not None else None,
            "delivered_is_verified": False, "verified_is_approved": False, "approved_is_promoted": False,
            "creates_authority": False}
        receipt_id = "verification-receipt-" + _digest(payload)
        record = {**payload, "verification_receipt_id": receipt_id, "created_at": _now()}
        record["record_sha256"] = _digest(record)
        return self._write_once("verification_receipts", record)

    def create_return_report(self, *, source_package_id, task_scope_id, sender, authority, sections,
                             claims=(), evidence_references=()):
        package = self._load("packages", source_package_id)
        if package["task_scope_id"] != task_scope_id: raise PermissionError("return report task mismatch")
        if _worker(sender, "sender")["worker_id"] != package["recipient"]["worker_id"]:
            raise PermissionError("only the bound recipient may author the return report")
        return self.create_report(task_scope_id=task_scope_id, sender=sender, authority=authority,
            sections=sections, claims=claims, evidence_references=evidence_references,
            in_reply_to={"package_id": source_package_id, "source_report_id": package["source_report_id"],
                         "source_report_sha256": package["source_report_sha256"],
                         "source_package_sha256": package["record_sha256"]})
