"""Provider-neutral, read-only staging for inherited conversation exports.

Staging preserves source evidence and builds an inspectable projection.  It
does not write Archive, Memory, Development, relationship state, or Phoenix
continuity.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import io
import json
import os
import re
import sqlite3
import uuid
import zipfile

from src.capabilities.core import (
    CapabilityDefinition, CapabilityExecutor, CapabilityRegistry, CapabilityRequest,
)
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract
from src.library.artifacts import require_id
from src.runtime.processing_ledger import ProcessingLedger


ROOT = Path(__file__).resolve().parent.parent
STATE_ROOT = Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
STAGING_ROOT = STATE_ROOT / "database" / "inherited_history"
SCHEMA_VERSION = 2
PROCESSOR_VERSION = "1.1"
MAX_EXPORT_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 10_000

IDENTITY_ATTRIBUTIONS = {
    "identified_as_fawkes", "distinguished", "mixed", "ambiguous", "unassessed",
}
NATIVE_BOUNDARY_STATUSES = {"pre_native", "boundary_unknown", "proven_native"}

INHERITED_HISTORY_STAGING_DEFINITION = CapabilityDefinition(
    name="history.import_stage", version="1.1",
    display_name="Inherited history staging",
    description="Stage an authorized conversation export as immutable inherited history without promoting it into Phoenix Memory or native continuity.",
    permissions=("history.import_stage",), effect="durable_inherited_evidence_write",
    modalities=MultimodalCapabilityContract(input_modalities=("document",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read", "create"), execution_boundary="internal", authorization_mode="explicit_confirmation"),
    privacy_handling="local_instance_scoped_original_export_no_provider_transmission",
    features=("provider_neutral_adapter", "immutable_original", "branch_preservation", "idempotent_staging", "provenance_bearing_inspection"),
    appropriate_use=("rider explicitly stages an export for historical inspection",),
    inappropriate_use=("create autobiographical Memory", "establish native continuity", "silently absorb history", "rewrite identity ambiguity"),
    limitations=("staged evidence is inert", "only ChatGPT export ZIP is currently supported", "semantic classification and attachments are not yet activated"),
    platform_support=("server", "provider_neutral"), presentation_options=("text", "table"),
    dependencies=("registered Phoenix instance", "Phase 0 ownership/recovery", "system.processing_ledger"),
    provenance_requirements=("original export digest", "provider export identity", "conversation/message identity", "inherited-history era", "native-boundary status"),
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _stable_id(kind, *values):
    digest = hashlib.sha256("\x1f".join(map(str, values)).encode("utf-8")).hexdigest()
    return f"{kind}-{digest[:32]}"


def _write_once(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("immutable inherited-history evidence conflict")
        return
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    except Exception:
        # A failed atomic write is not evidence and must not consume space or
        # be mistaken for an accepted original on retry.
        try: temporary.unlink(missing_ok=True)
        except OSError: pass
        raise


def _write_original_once(path, data, expected_digest):
    if path.exists():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
        if digest.hexdigest() != expected_digest or path.stat().st_size != len(data):
            raise ValueError("immutable inherited-history original conflict")
        return
    _write_once(path, data)


def _validate_authorization(value, *, instance_id, actor_principal):
    if not isinstance(value, dict):
        raise PermissionError("explicit inherited-history staging authorization is required")
    if value.get("mode") != "explicit_confirmation" or value.get("scope") != "stage_inherited_history_export":
        raise PermissionError("authorization does not permit inherited-history staging")
    if value.get("instance_id") != instance_id or value.get("principal_id") != actor_principal:
        raise PermissionError("staging authorization Phoenix/principal mismatch")
    authorization_id = require_id(value.get("authorization_id"), "authorization_id")
    return {"authorization_id": authorization_id, "mode": value["mode"], "scope": value["scope"],
            "instance_id": instance_id, "principal_id": actor_principal}


class ExportAdapter(ABC):
    """Provider-neutral boundary; adapters yield source-faithful records."""

    provider_id = None
    format_id = None
    version = None

    @abstractmethod
    def parse(self, raw_export):
        """Return (conversations, warnings), or raise ValueError."""


class ChatGPTExportAdapter(ExportAdapter):
    provider_id = "openai_chatgpt"
    format_id = "chatgpt_data_export_zip"
    version = PROCESSOR_VERSION

    def parse(self, raw_export):
        if not isinstance(raw_export, bytes) or not raw_export:
            raise ValueError("export is empty")
        if len(raw_export) > MAX_EXPORT_BYTES:
            raise ValueError("export exceeds staging size limit")
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw_export))
        except (zipfile.BadZipFile, OSError) as exc:
            raise ValueError("export is not a valid ZIP") from exc
        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_MEMBERS:
                raise ValueError("export contains too many members")
            matches = [item for item in infos if Path(item.filename.rstrip("/")).name == "conversations.json"]
            if len(matches) != 1:
                raise ValueError("export must contain exactly one conversations.json")
            info = matches[0]
            parts = Path(info.filename).parts
            if info.is_dir() or info.file_size > MAX_MEMBER_BYTES or any(part in {"..", ""} for part in parts):
                raise ValueError("unsafe or oversized conversations.json")
            try:
                payload = json.loads(archive.read(info).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, RuntimeError, RecursionError) as exc:
                raise ValueError("conversations.json is malformed") from exc
        if not isinstance(payload, list):
            raise ValueError("conversations.json must be a list")
        conversations, warnings = [], []
        for index, source in enumerate(payload):
            if not isinstance(source, dict) or not source.get("id") or not isinstance(source.get("mapping"), dict):
                warnings.append({"code": "malformed_conversation", "index": index})
                continue
            messages = []
            branch_nodes = []
            for node_id, node in source["mapping"].items():
                if not isinstance(node, dict):
                    warnings.append({"code": "malformed_node", "conversation_id": source["id"], "node_id": str(node_id)})
                    continue
                message = node.get("message")
                branch_nodes.append({"source_node_id": str(node_id), "source_parent_node_id": node.get("parent"),
                    "source_child_node_ids": list(node.get("children") or []),
                    "source_message_id": str(message.get("id")) if isinstance(message, dict) and message.get("id") else None})
                if message is None:
                    continue
                if not isinstance(message, dict) or not message.get("id"):
                    warnings.append({"code": "malformed_message", "conversation_id": source["id"], "node_id": str(node_id)})
                    continue
                author = message.get("author") if isinstance(message.get("author"), dict) else {}
                content = message.get("content") if isinstance(message.get("content"), dict) else {}
                parts_value = content.get("parts") if isinstance(content.get("parts"), list) else []
                text_parts = [part for part in parts_value if isinstance(part, str)]
                messages.append({
                    "source_node_id": str(node_id), "source_message_id": str(message["id"]),
                    "source_parent_node_id": node.get("parent"),
                    "source_child_node_ids": list(node.get("children") or []),
                    "role": author.get("role"), "author_name": author.get("name"),
                    "created_at": message.get("create_time"), "updated_at": message.get("update_time"),
                    "content_type": content.get("content_type"), "text": "\n".join(text_parts),
                    "source_message": message,
                })
            conversations.append({
                "source_conversation_index": index,
                "source_conversation_id": str(source["id"]), "title": source.get("title"),
                "created_at": source.get("create_time"), "updated_at": source.get("update_time"),
                "current_node": source.get("current_node"), "branch_nodes": branch_nodes, "messages": messages,
                "source_conversation": source,
            })
        if payload and not conversations:
            raise ValueError("export contains no valid conversations")
        return conversations, warnings


class InheritedHistoryStore:
    def __init__(self, instance_id, *, root=None, processing_root=None):
        self.instance_id = require_id(instance_id, "instance_id")
        self.base_root = Path(root) if root else STAGING_ROOT
        self.root = self.base_root / self.instance_id
        self.processing_root = processing_root
        self.index_path = self.root / "index.sqlite3"

    def _connect(self):
        self.root.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.index_path)
        db.row_factory = sqlite3.Row
        db.executescript("""
          CREATE TABLE IF NOT EXISTS staging_metadata(schema_version INTEGER NOT NULL, instance_id TEXT PRIMARY KEY);
          CREATE TABLE IF NOT EXISTS staged_exports(export_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL, digest TEXT NOT NULL UNIQUE, manifest_json TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS staged_conversations(conversation_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL, export_id TEXT NOT NULL, source_conversation_id TEXT NOT NULL, source_conversation_index INTEGER NOT NULL, title TEXT, record_json TEXT NOT NULL, UNIQUE(export_id,source_conversation_id,source_conversation_index));
          CREATE TABLE IF NOT EXISTS staged_nodes(node_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL, export_id TEXT NOT NULL, conversation_id TEXT NOT NULL, source_node_id TEXT NOT NULL, source_message_id TEXT, record_json TEXT NOT NULL, UNIQUE(export_id,conversation_id,source_node_id));
          CREATE TABLE IF NOT EXISTS staged_messages(message_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL, export_id TEXT NOT NULL, conversation_id TEXT NOT NULL, source_message_id TEXT NOT NULL, source_node_id TEXT NOT NULL, role TEXT, text TEXT NOT NULL, created_at TEXT, record_json TEXT NOT NULL, UNIQUE(export_id,conversation_id,source_message_id,source_node_id));
          CREATE INDEX IF NOT EXISTS staged_messages_text ON staged_messages(instance_id, conversation_id, created_at);
        """)
        row = db.execute("SELECT schema_version,instance_id FROM staging_metadata").fetchone()
        if row is None:
            db.execute("INSERT INTO staging_metadata VALUES (?,?)", (SCHEMA_VERSION, self.instance_id))
        elif row[0] != SCHEMA_VERSION or row[1] != self.instance_id:
            db.close(); raise ValueError("inherited-history staging ownership/schema mismatch")
        db.commit(); return db

    def stage(self, raw_export, *, adapter, actor_principal, authorization,
              filename="export.zip", resume_confirmed_interruption=False):
        if not isinstance(adapter, ExportAdapter):
            raise TypeError("provider-neutral export adapter is required")
        if not isinstance(raw_export, bytes) or not raw_export:
            raise ValueError("export bytes are required")
        if len(raw_export) > MAX_EXPORT_BYTES:
            raise ValueError("export exceeds staging intake size limit")
        actor_principal = require_id(actor_principal, "actor_principal")
        authorization = _validate_authorization(authorization, instance_id=self.instance_id,
                                                actor_principal=actor_principal)
        digest = hashlib.sha256(raw_export).hexdigest()
        export_id = _stable_id("history-export", adapter.provider_id, digest)
        source = {"source_id": export_id, "object_id": export_id, "content_id": digest,
                  "revision_id": digest, "source_domain": "inherited_history_export", "evidence_era": "inherited_history"}
        ledger = ProcessingLedger(self.instance_id, root=self.processing_root)
        work = ledger.register(domain="inherited_history_import", work_kind="stage_export", source=source,
            processor_id=f"history-adapter:{adapter.provider_id}", processor_version=adapter.version,
            idempotency_key=f"{adapter.provider_id}-{digest}",
            actor={"actor_type": "import", "principal_id": actor_principal},
            provenance=({"relation": "preserves_original", "target_id": export_id},
                        {"relation": "authorized_by", "target_id": authorization["authorization_id"]}),
            extensions={"historical_provenance": {"history_origin_id": export_id,
                "relationship_provenance_id": "founding-developmental",
                "identity_attribution": "unassessed", "native_boundary_status": "boundary_unknown"}})
        if work["status"] == "completed":
            manifest = self.get_export(export_id)
            if manifest is None: raise ValueError("completed import is missing authoritative staged evidence")
            return {**manifest, "idempotent_replay": True, "work_item_id": work["work_item_id"]}
        if work["status"] == "failed_terminal":
            raise ValueError("this immutable export previously failed terminal validation")
        if work["status"] == "discovered":
            work = ledger.transition(work["work_item_id"], to_status="queued", operation_id="queue-initial")
        # Claim the exact synchronous import, rather than whichever queued
        # history job happens to sort first. The ledger transaction makes a
        # competing claim observe `running` and fail closed.
        work = ledger.get(work["work_item_id"])
        if work["status"] == "running" and resume_confirmed_interruption:
            work = ledger.transition(work["work_item_id"], to_status="failed_retryable",
                operation_id=f"confirmed-interruption-{work['attempt_count']}",
                error={"code": "confirmed_process_interruption", "stage": "operator_recovery"})
        if work["status"] not in {"queued", "failed_retryable"}:
            raise RuntimeError("staging work is not eligible to resume; confirm the prior worker is stopped before recovery")
        ledger.transition(work["work_item_id"], to_status="running",
            operation_id=f"stage-attempt-{work['attempt_count'] + 1}", increment_attempt=True)
        try:
            original = self.root / "originals" / f"{export_id}.zip"
            _write_original_once(original, raw_export, digest)
            received = {"schema_version": SCHEMA_VERSION, "record_type": "inherited_history_artifact_received",
                "instance_id": self.instance_id, "export_id": export_id, "history_era": "inherited_history",
                "relationship_provenance": "founding_developmental", "identity_attribution": "unassessed",
                "native_boundary_status": "boundary_unknown", "original_filename": Path(filename).name,
                "original_evidence_reference": str(original.relative_to(self.root)),
                "original_digest": f"sha256:{digest}", "size_bytes": len(raw_export),
                "actor_principal_id": actor_principal, "authorization": authorization,
                "received_at": _now(), "immutable": True}
            receipt_path = self.root / "receipts" / f"{export_id}.json"
            if receipt_path.exists():
                existing_received = json.loads(receipt_path.read_text(encoding="utf-8"))
                comparable = dict(received); comparable["received_at"] = existing_received.get("received_at")
                if existing_received != comparable:
                    raise ValueError("immutable inherited-history receipt conflict")
            else:
                _write_once(receipt_path, (json.dumps(received, indent=2, sort_keys=True) + "\n").encode())
        except Exception as exc:
            current = ledger.get(work["work_item_id"])
            if current and current["status"] == "running":
                ledger.transition(work["work_item_id"], to_status="failed_retryable", operation_id=f"receive-failure-{current['attempt_count']}",
                    error={"code": "original_preservation_failed", "stage": "preserve_original", "type": type(exc).__name__})
            raise
        try:
            conversations, warnings = adapter.parse(raw_export)
        except ValueError as exc:
            ledger.transition(work["work_item_id"], to_status="failed_terminal", operation_id="terminal-validation-v1",
                error={"code": "malformed_export", "stage": "parse", "type": type(exc).__name__})
            raise
        except Exception as exc:
            ledger.transition(work["work_item_id"], to_status="failed_retryable", operation_id=f"parse-failure-{work['attempt_count'] + 1}",
                error={"code": "parser_runtime_failure", "stage": "parse", "type": type(exc).__name__})
            raise
        try:
            manifest = self._persist(export_id, digest, filename, adapter, conversations, warnings, original,
                                     authorization=authorization)
            ledger.transition(work["work_item_id"], to_status="completed", operation_id="complete-v1",
                assessment={"status": manifest["staging_status"], "warnings": len(warnings)},
                result_references=[export_id])
            return {**manifest, "idempotent_replay": False, "work_item_id": work["work_item_id"]}
        except Exception as exc:
            current = ledger.get(work["work_item_id"])
            if current and current["status"] == "running":
                ledger.transition(work["work_item_id"], to_status="failed_retryable", operation_id=f"stage-failure-{current['attempt_count']}",
                    error={"code": "staging_write_failed", "stage": "persist", "type": type(exc).__name__})
            raise

    def _persist(self, export_id, digest, filename, adapter, conversations, warnings, original, *, authorization):
        staged_at = _now()
        base = {
            "schema_version": SCHEMA_VERSION, "instance_id": self.instance_id,
            "history_era": "inherited_history", "relationship_provenance": "founding_developmental",
            "identity_attribution": "unassessed", "native_boundary_status": "boundary_unknown",
            "classification_derivation": {"method": "not_assessed", "uncertainty": "unassessed"},
            "history_origin": {"provider": adapter.provider_id, "format": adapter.format_id,
                               "export_id": export_id, "original_digest": f"sha256:{digest}"},
            "processor": {"id": f"history-adapter:{adapter.provider_id}", "version": adapter.version},
            "authorization_reference": authorization["authorization_id"],
        }
        manifest = {**base, "record_type": "inherited_history_export_manifest", "export_id": export_id,
            "original_filename": Path(filename).name, "original_evidence_reference": str(original.relative_to(self.root)),
            "conversation_count": len(conversations), "message_count": sum(len(c["messages"]) for c in conversations),
            "warnings": warnings, "staging_status": "partial" if warnings else "complete", "staged_at": staged_at,
            "read_only": True, "behavioral_influence": "none", "memory_promotion": "prohibited"}
        existing = self.get_export(export_id)
        if existing is not None:
            if existing != manifest:
                # staged_at is intentionally part of the first immutable
                # manifest; an interrupted retry reuses it below.
                comparable = dict(manifest); comparable["staged_at"] = existing.get("staged_at")
                if existing != comparable:
                    raise ValueError("immutable staged export conflicts with existing evidence")
            _write_once(self.root / "manifests" / f"{export_id}.json",
                        (json.dumps(existing, indent=2, sort_keys=True) + "\n").encode())
            return existing
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO staged_exports VALUES (?,?,?,?)", (export_id, self.instance_id, digest, json.dumps(manifest, sort_keys=True)))
            for conversation in conversations:
                conversation_id = _stable_id("history-conversation", adapter.provider_id, export_id,
                                             conversation["source_conversation_id"], conversation["source_conversation_index"])
                conv_record = {**base, "record_type": "inherited_history_conversation", "export_id": export_id,
                    "conversation_id": conversation_id, "source_conversation_id": conversation["source_conversation_id"],
                    "source_conversation_index": conversation["source_conversation_index"],
                    "title": conversation["title"], "created_at": conversation["created_at"], "updated_at": conversation["updated_at"],
                    "current_node": conversation["current_node"], "branch_node_count": len(conversation["branch_nodes"]),
                    "original_evidence_reference": f"{export_id}:conversation-index:{conversation['source_conversation_index']}:conversation:{conversation['source_conversation_id']}"}
                db.execute("INSERT INTO staged_conversations VALUES (?,?,?,?,?,?,?)", (conversation_id, self.instance_id, export_id, conversation["source_conversation_id"], conversation["source_conversation_index"], conversation["title"], json.dumps(conv_record, sort_keys=True)))
                for node in conversation["branch_nodes"]:
                    node_id = _stable_id("history-node", adapter.provider_id, export_id, conversation_id, node["source_node_id"])
                    node_record = {**base, "record_type": "inherited_history_node", "export_id": export_id,
                        "conversation_id": conversation_id, "node_id": node_id, **node,
                        "original_evidence_reference": f"{conv_record['original_evidence_reference']}:node:{node['source_node_id']}"}
                    db.execute("INSERT INTO staged_nodes VALUES (?,?,?,?,?,?,?)", (node_id, self.instance_id, export_id,
                        conversation_id, node["source_node_id"], node["source_message_id"], json.dumps(node_record, sort_keys=True)))
                for message in conversation["messages"]:
                    message_id = _stable_id("history-message", adapter.provider_id, export_id, conversation_id,
                                            message["source_node_id"], message["source_message_id"])
                    record = {**base, "record_type": "inherited_history_message", "export_id": export_id,
                        "conversation_id": conversation_id, "message_id": message_id,
                        "source_conversation_index": conversation["source_conversation_index"],
                        "source_conversation_id": conversation["source_conversation_id"],
                        "source_node_id": message["source_node_id"], "source_message_id": message["source_message_id"],
                        "source_parent_node_id": message["source_parent_node_id"], "source_child_node_ids": message["source_child_node_ids"],
                        "role": message["role"], "author_name": message["author_name"], "created_at": message["created_at"],
                        "updated_at": message["updated_at"], "content_type": message["content_type"], "text": message["text"],
                        "original_evidence_reference": f"{export_id}:conversation:{conversation['source_conversation_id']}:node:{message['source_node_id']}:message:{message['source_message_id']}"}
                    db.execute("INSERT INTO staged_messages VALUES (?,?,?,?,?,?,?,?,?,?)", (message_id, self.instance_id, export_id, conversation_id, message["source_message_id"], message["source_node_id"], message["role"], message["text"], str(message["created_at"] or ""), json.dumps(record, sort_keys=True)))
            db.commit()
        except Exception:
            db.rollback(); raise
        finally: db.close()
        _write_once(self.root / "manifests" / f"{export_id}.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
        return manifest

    def get_export(self, export_id):
        db = self._connect()
        try: row = db.execute("SELECT manifest_json FROM staged_exports WHERE export_id=? AND instance_id=?", (export_id, self.instance_id)).fetchone()
        finally: db.close()
        return json.loads(row[0]) if row else None

    def list_exports(self):
        db = self._connect()
        try: rows = db.execute("SELECT manifest_json FROM staged_exports WHERE instance_id=? ORDER BY export_id", (self.instance_id,)).fetchall()
        finally: db.close()
        return [json.loads(row[0]) for row in rows]

    def inspection_snapshot(self, export_id):
        """Return a read-only, ownership-scoped projection for corpus validation."""
        require_id(export_id, "export_id")
        db = self._connect()
        try:
            manifest_row = db.execute(
                "SELECT manifest_json FROM staged_exports WHERE export_id=? AND instance_id=?",
                (export_id, self.instance_id),
            ).fetchone()
            if manifest_row is None:
                raise LookupError("inherited export is unavailable")
            conversations = db.execute(
                "SELECT record_json FROM staged_conversations WHERE export_id=? AND instance_id=? "
                "ORDER BY source_conversation_index,conversation_id", (export_id, self.instance_id),
            ).fetchall()
            nodes = db.execute(
                "SELECT n.record_json,c.source_conversation_id,c.source_conversation_index "
                "FROM staged_nodes n JOIN staged_conversations c ON c.conversation_id=n.conversation_id "
                "WHERE n.export_id=? AND n.instance_id=? AND c.instance_id=? "
                "ORDER BY c.source_conversation_index,n.source_node_id,n.node_id",
                (export_id, self.instance_id, self.instance_id),
            ).fetchall()
            messages = db.execute(
                "SELECT record_json FROM staged_messages WHERE export_id=? AND instance_id=? "
                "ORDER BY conversation_id,source_node_id,message_id", (export_id, self.instance_id),
            ).fetchall()
        finally:
            db.close()
        node_records = []
        for row in nodes:
            record = json.loads(row[0])
            node_records.append({**record, "source_conversation_id": row[1],
                                 "source_conversation_index": row[2]})
        return {
            "manifest": json.loads(manifest_row[0]),
            "conversations": [json.loads(row[0]) for row in conversations],
            "nodes": node_records,
            "messages": [json.loads(row[0]) for row in messages],
        }

    def search(self, query, *, limit=20, export_id=None):
        if not isinstance(query, str) or not query.strip(): return []
        if not isinstance(limit, int) or not 1 <= limit <= 100: raise ValueError("limit must be 1 to 100")
        if export_id is not None: require_id(export_id, "export_id")
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        db = self._connect()
        try:
            if export_id is None:
                rows = db.execute("SELECT record_json FROM staged_messages WHERE instance_id=? AND text LIKE ? ESCAPE '\\' ORDER BY created_at,message_id LIMIT ?", (self.instance_id, pattern, limit)).fetchall()
            else:
                rows = db.execute("SELECT record_json FROM staged_messages WHERE instance_id=? AND export_id=? AND text LIKE ? ESCAPE '\\' ORDER BY created_at,message_id LIMIT ?", (self.instance_id, export_id, pattern, limit)).fetchall()
        finally: db.close()
        return [json.loads(row[0]) for row in rows]

    def get_message(self, message_id):
        require_id(message_id, "message_id")
        db = self._connect()
        try: row = db.execute("SELECT record_json FROM staged_messages WHERE message_id=? AND instance_id=?", (message_id, self.instance_id)).fetchone()
        finally: db.close()
        return json.loads(row[0]) if row else None

    def original_message(self, message_id):
        """Navigate a staged projection back into its authoritative export."""
        record = self.get_message(message_id)
        if record is None: raise LookupError("inherited source message is unavailable")
        manifest = self.get_export(record["export_id"])
        if manifest is None: raise LookupError("inherited export manifest is unavailable")
        original = self.root / manifest["original_evidence_reference"]
        try: raw = original.read_bytes()
        except OSError as exc: raise LookupError("inherited original export is unavailable") from exc
        expected = manifest["history_origin"]["original_digest"]
        actual = "sha256:" + hashlib.sha256(raw).hexdigest()
        if actual != expected: raise ValueError("inherited original export failed integrity verification")
        conversations, _warnings = ChatGPTExportAdapter().parse(raw)
        source_message = None
        for conversation in conversations:
            if (conversation["source_conversation_id"] != record["source_conversation_id"]
                    or conversation["source_conversation_index"] != record["source_conversation_index"]): continue
            source_message = next((item["source_message"] for item in conversation["messages"]
                                   if item["source_node_id"] == record["source_node_id"]
                                   and item["source_message_id"] == record["source_message_id"]), None)
            break
        if source_message is None: raise ValueError("staging projection does not resolve to original export evidence")
        content = source_message.get("content") if isinstance(source_message.get("content"), dict) else {}
        exact_text = "\n".join(item for item in content.get("parts", ()) if isinstance(item, str))
        return {"schema_version": 1, "record_type": "historical_source_evidence",
            "instance_id": self.instance_id, "domain": "inherited_history",
            "history_era": record["history_era"], "relationship_provenance": record["relationship_provenance"],
            "identity_attribution": record["identity_attribution"],
            "native_boundary_status": record["native_boundary_status"],
            "authority_class": "immutable_imported_source_evidence",
            "provider_source": record["history_origin"],
            "conversation_id": record["conversation_id"], "message_id": record["message_id"],
            "source_conversation_id": record["source_conversation_id"],
            "source_conversation_index": record["source_conversation_index"],
            "source_message_id": record["source_message_id"], "source_node_id": record["source_node_id"],
            "evidence_reference": {"domain": "inherited_history", "evidence_id": message_id,
                "original_evidence_reference": record["original_evidence_reference"],
                "export_id": record["export_id"], "original_digest": actual},
            "exact_original_text": exact_text, "original_record": source_message,
            "navigation_projection_authoritative": False}


def stage_authorized_export(raw_export, *, instance_id, adapter, actor_principal,
                            authorization, filename="export.zip", root=None,
                            processing_root=None, capability_receipt_dir=None,
                            explicitly_confirmed=False,
                            resume_confirmed_interruption=False,
                            granted_permissions=("history.import_stage",)):
    """Official authority boundary for a future rider-approved local import.

    Raw bytes stay in the handler closure and are never copied into capability
    receipt arguments. The domain store independently revalidates attribution.
    """
    store = InheritedHistoryStore(instance_id, root=root, processing_root=processing_root)
    registry = CapabilityRegistry()

    def stage(_request):
        result = store.stage(raw_export, adapter=adapter, filename=filename,
                             actor_principal=actor_principal, authorization=authorization,
                             resume_confirmed_interruption=resume_confirmed_interruption)
        return {"staged_export": result, "result_references": [result["export_id"], result["work_item_id"]]}

    registry.register(INHERITED_HISTORY_STAGING_DEFINITION, stage)
    result = CapabilityExecutor(registry, receipt_dir=capability_receipt_dir).execute(
        CapabilityRequest(instance_id=instance_id, capability=INHERITED_HISTORY_STAGING_DEFINITION.name,
                          arguments={"filename": Path(filename).name,
                                     "authorization_id": authorization.get("authorization_id") if isinstance(authorization, dict) else None},
                          requested_by="rider", explicitly_confirmed=explicitly_confirmed),
        granted_permissions=granted_permissions,
    )
    return result["staged_export"] | {"capability_receipt_id": result["capability_receipt_id"]}
