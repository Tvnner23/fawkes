"""Provider-neutral, instance-scoped coordination ledger.

The ledger records processing work and append-only lifecycle evidence. It does
not replace or mutate Archive, Library, Memory, Development, Test history, or
their authoritative domain records.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3

from src.library.artifacts import EVIDENCE_ERAS, require_id, stable_work_id
from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract


ROOT = Path(__file__).resolve().parent.parent.parent
STATE_ROOT = Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
PROCESSING_ROOT = STATE_ROOT / "database" / "processing"
SCHEMA_VERSION = 1

STATUSES = {
    "discovered", "queued", "running", "paused", "awaiting_review",
    "completed", "failed_retryable", "failed_terminal", "quarantined",
    "cancelled", "superseded",
}
TRANSITIONS = {
    "discovered": {"queued", "cancelled", "quarantined"},
    "queued": {"running", "paused", "cancelled", "quarantined"},
    "running": {"completed", "paused", "awaiting_review", "failed_retryable",
                "failed_terminal", "quarantined", "cancelled"},
    "paused": {"queued", "running", "cancelled", "quarantined"},
    "awaiting_review": {"queued", "completed", "failed_terminal", "cancelled", "quarantined"},
    "failed_retryable": {"queued", "running", "failed_terminal", "cancelled", "quarantined"},
    "completed": {"superseded"},
    "failed_terminal": set(), "quarantined": {"queued", "cancelled"},
    "cancelled": set(), "superseded": set(),
}
REALITY_SCOPES = {"production", "development", "synthetic_experiment"}
TIME_DOMAIN_KINDS = {"wall_clock", "simulation"}
EXTENSION_NAMESPACES = {
    "development_run", "experiment_run", "continuity_lineage",
    "validated_progression", "independent_reference", "historical_provenance",
}

PROCESSING_LEDGER_DEFINITION = CapabilityDefinition(
    name="system.processing_ledger", version="1.0",
    display_name="Canonical Processing Ledger",
    description="Coordinate instance-scoped resumable processing without replacing authoritative domain evidence.",
    effect="internal_coordination_projection",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read", "create", "modify"), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="instance_scoped_metadata_only_no_source_payload_required",
    features=("stable_work_identity", "append_only_processing_events", "resumable_lifecycle",
              "corpus_coverage_projection", "future_metadata_extension_envelopes"),
    appropriate_use=("coordinate and inspect bounded Phoenix processing", "identify processing failures and coverage gaps"),
    inappropriate_use=("replace Archive or Library evidence", "grant authority", "create Memory", "activate Ghost Rider or continuity claims"),
    limitations=("existing Memory work remains in its domain ledger until an explicit migration", "coverage includes only registered work", "reserved extensions are inert metadata"),
    platform_support=("server", "provider_neutral", "platform_independent"),
    presentation_options=("text",),
    dependencies=("registered Phoenix instance", "Phase 0 ownership and recovery"),
    provenance_requirements=("Phoenix instance id", "source revision identity", "processor version", "append-only lifecycle event"),
)


class SystemClock:
    domain_id = "wall-clock:utc"
    kind = "wall_clock"

    def now(self):
        return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _validate_source(source):
    if not isinstance(source, dict):
        raise ValueError("processing source revision is required")
    result = dict(source)
    for name in ("source_id", "object_id", "content_id", "revision_id"):
        require_id(result.get(name), name)
    if result.get("evidence_era") not in EVIDENCE_ERAS:
        raise ValueError("processing source evidence_era is required")
    result["source_domain"] = str(result.get("source_domain") or "unknown")
    return result


def _validate_actor(actor):
    if not isinstance(actor, dict) or actor.get("actor_type") not in {
        "rider", "phoenix", "runtime", "developer", "import", "workflow", "agent",
    }:
        raise ValueError("processing actor attribution is required")
    require_id(actor.get("principal_id"), "actor principal_id")
    return dict(actor)


def _validate_time_domain(value):
    value = dict(value or {"kind": "wall_clock", "domain_id": "wall-clock:utc"})
    if value.get("kind") not in TIME_DOMAIN_KINDS:
        raise ValueError("invalid processing time domain")
    require_id(value.get("domain_id"), "time domain_id")
    return value


def _validate_extensions(value):
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - EXTENSION_NAMESPACES:
        raise ValueError("unknown processing extension namespace")
    result = {}
    for namespace, payload in value.items():
        if not isinstance(payload, dict):
            raise ValueError(f"{namespace} extension must be an object")
        # Extension payloads remain inert. IDs are checked when present, but
        # their presence cannot activate authority, simulation, or continuity.
        clean = dict(payload)
        for key, item in clean.items():
            if key.endswith("_id") and item is not None:
                require_id(item, f"{namespace}.{key}")
        result[namespace] = clean
    return result


def processing_root(instance_id, *, root=None):
    require_id(instance_id, "instance_id")
    return (Path(root) if root else PROCESSING_ROOT) / instance_id


class ProcessingLedger:
    def __init__(self, instance_id, *, root=None, clock=None):
        self.instance_id = require_id(instance_id, "instance_id")
        self.root = processing_root(instance_id, root=root)
        self.path = self.root / "ledger.sqlite3"
        self.clock = clock or SystemClock()
        self.time_domain = _validate_time_domain({
            "kind": getattr(self.clock, "kind", None),
            "domain_id": getattr(self.clock, "domain_id", None),
        })

    def _connect(self):
        self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS processing_ledger_metadata (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                schema_version INTEGER NOT NULL,
                instance_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS processing_work_items (
                work_item_id TEXT PRIMARY KEY,
                instance_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                work_kind TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                processor_id TEXT NOT NULL,
                processor_version TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                envelope_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(instance_id, domain, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS processing_instance_status
                ON processing_work_items(instance_id, status, updated_at);
            CREATE INDEX IF NOT EXISTS processing_instance_domain
                ON processing_work_items(instance_id, domain, updated_at);
            CREATE TABLE IF NOT EXISTS processing_events (
                event_id TEXT PRIMARY KEY,
                work_item_id TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                event_json TEXT NOT NULL,
                FOREIGN KEY(work_item_id) REFERENCES processing_work_items(work_item_id)
            );
            CREATE INDEX IF NOT EXISTS processing_event_work
                ON processing_events(instance_id, work_item_id, occurred_at);
        """)
        metadata = connection.execute(
            "SELECT schema_version, instance_id FROM processing_ledger_metadata WHERE singleton=1"
        ).fetchone()
        if metadata is None:
            connection.execute(
                "INSERT INTO processing_ledger_metadata VALUES (1,?,?,?)",
                (SCHEMA_VERSION, self.instance_id, self.clock.now()),
            )
        elif metadata["schema_version"] != SCHEMA_VERSION or metadata["instance_id"] != self.instance_id:
            connection.close()
            raise ValueError("processing ledger schema or Phoenix ownership mismatch")
        connection.commit()
        return connection

    def register(self, *, domain, work_kind, source, processor_id,
                 processor_version, idempotency_key, actor,
                 reality_scope="production", time_domain=None, provenance=(),
                 resource=None, extensions=None, dependency_work_item_ids=(),
                 correlation_id=None, causation_id=None):
        for value, name in ((domain, "domain"), (work_kind, "work_kind"),
                            (processor_id, "processor_id"),
                            (processor_version, "processor_version"),
                            (idempotency_key, "idempotency_key")):
            require_id(value, name)
        if reality_scope not in REALITY_SCOPES:
            raise ValueError("invalid processing reality_scope")
        source = _validate_source(source)
        actor = _validate_actor(actor)
        time_domain = _validate_time_domain(time_domain or self.time_domain)
        if reality_scope == "production" and time_domain["kind"] != "wall_clock":
            raise ValueError("production work cannot use simulation time")
        edges = []
        for edge in provenance:
            if not isinstance(edge, dict) or not edge.get("relation") or not edge.get("target_id"):
                raise ValueError("typed processing provenance is required")
            require_id(edge["target_id"], "provenance target_id")
            edges.append(dict(edge))
        dependencies = []
        for dependency in dependency_work_item_ids:
            dependencies.append(require_id(dependency, "dependency work_item_id"))
        if correlation_id is not None: require_id(correlation_id, "correlation_id")
        if causation_id is not None: require_id(causation_id, "causation_id")
        now = self.clock.now()
        work_item_id = stable_work_id("processing", self.instance_id, domain, idempotency_key)
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "record_type": "phoenix_processing_work_item",
            "work_item_id": work_item_id,
            "instance_id": self.instance_id,
            "domain": domain,
            "work_kind": work_kind,
            "source": source,
            "processor": {"processor_id": processor_id, "processor_version": processor_version},
            "status": "discovered",
            "attempt_count": 0,
            "idempotency_key": idempotency_key,
            "actor": actor,
            "reality_scope": reality_scope,
            "time_domain": time_domain,
            "provenance": edges,
            "dependency_work_item_ids": dependencies,
            "correlation_id": correlation_id,
            "causation_id": causation_id,
            "resource": dict(resource or {}),
            "assessment": None,
            "decision": None,
            "result_references": [],
            "review_reference": None,
            "error": None,
            "extensions": _validate_extensions(extensions),
            "created_at": now,
            "updated_at": now,
        }
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM processing_work_items WHERE instance_id=? AND domain=? AND idempotency_key=?",
                (self.instance_id, domain, idempotency_key),
            ).fetchone()
            if existing is not None:
                current = self._decode(existing)
                immutable = ("work_kind", "source", "processor", "actor", "reality_scope", "time_domain",
                             "extensions", "dependency_work_item_ids", "correlation_id", "causation_id")
                if any(current[field] != envelope[field] for field in immutable):
                    raise ValueError("processing idempotency key already identifies different work")
                connection.commit()
                return current
            connection.execute(
                "INSERT INTO processing_work_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (work_item_id, self.instance_id, domain, work_kind, idempotency_key,
                 processor_id, processor_version, "discovered", 0, _json(envelope), now, now),
            )
            self._insert_event(connection, envelope, "work.registered", None, "discovered", {}, "registration")
            connection.commit()
            return envelope
        finally:
            connection.close()

    def transition(self, work_item_id, *, to_status, operation_id, details=None,
                   assessment=None, decision=None, result_references=None,
                   review_reference=None, error=None, increment_attempt=False):
        require_id(work_item_id, "work_item_id")
        require_id(operation_id, "operation_id")
        if to_status not in STATUSES:
            raise ValueError("invalid processing status")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM processing_work_items WHERE work_item_id=? AND instance_id=?",
                (work_item_id, self.instance_id),
            ).fetchone()
            if row is None:
                raise KeyError("processing work item does not belong to this Phoenix")
            current = self._decode(row)
            event_id = stable_work_id("processing-event", self.instance_id, work_item_id, operation_id)
            prior_event = connection.execute("SELECT event_json FROM processing_events WHERE event_id=?", (event_id,)).fetchone()
            if prior_event is not None:
                prior = json.loads(prior_event["event_json"])
                if prior.get("to_status") != to_status:
                    raise ValueError("processing operation_id already identifies a different transition")
                connection.commit()
                return current
            if to_status not in TRANSITIONS[current["status"]]:
                raise ValueError(f"disallowed processing transition: {current['status']} -> {to_status}")
            now = self.clock.now()
            updated = dict(current)
            updated.update(status=to_status, updated_at=now,
                           attempt_count=current["attempt_count"] + (1 if increment_attempt else 0))
            if assessment is not None: updated["assessment"] = dict(assessment)
            if decision is not None: updated["decision"] = dict(decision)
            if result_references is not None:
                updated["result_references"] = [require_id(item, "result_reference") for item in result_references]
            if review_reference is not None:
                require_id(review_reference, "review_reference")
                updated["review_reference"] = review_reference
            updated["error"] = dict(error) if error is not None else None
            connection.execute(
                "UPDATE processing_work_items SET status=?, attempt_count=?, envelope_json=?, updated_at=? WHERE work_item_id=?",
                (to_status, updated["attempt_count"], _json(updated), now, work_item_id),
            )
            self._insert_event(connection, updated, "work.transitioned", current["status"], to_status,
                               details or {}, operation_id)
            connection.commit()
            return updated
        finally:
            connection.close()

    def get(self, work_item_id):
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM processing_work_items WHERE work_item_id=? AND instance_id=?",
                (work_item_id, self.instance_id),
            ).fetchone()
            return self._decode(row)
        finally:
            connection.close()

    def claim_next(self, *, domain=None):
        """Atomically claim one queued/retryable item for this Phoenix."""
        if domain is not None: require_id(domain, "domain")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            query = ("SELECT * FROM processing_work_items WHERE instance_id=? "
                     "AND status IN ('queued','failed_retryable')")
            values = [self.instance_id]
            if domain is not None:
                query += " AND domain=?"; values.append(domain)
            query += " ORDER BY updated_at,work_item_id LIMIT 1"
            row = connection.execute(query, values).fetchone()
            if row is None:
                connection.commit(); return None
            current = self._decode(row); now = self.clock.now()
            updated = dict(current)
            updated.update(status="running", attempt_count=current["attempt_count"] + 1,
                           updated_at=now, error=None)
            operation_id = f"claim-{updated['attempt_count']}"
            connection.execute(
                "UPDATE processing_work_items SET status='running',attempt_count=?,envelope_json=?,updated_at=? WHERE work_item_id=?",
                (updated["attempt_count"], _json(updated), now, updated["work_item_id"]),
            )
            self._insert_event(connection, updated, "work.claimed", current["status"], "running", {}, operation_id)
            connection.commit(); return updated
        finally:
            connection.close()

    def list(self, *, status=None, domain=None, limit=100):
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("processing list limit must be 1 to 1000")
        clauses = ["instance_id=?"]; values = [self.instance_id]
        if status is not None:
            if status not in STATUSES: raise ValueError("invalid processing status")
            clauses.append("status=?"); values.append(status)
        if domain is not None:
            require_id(domain, "domain"); clauses.append("domain=?"); values.append(domain)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT * FROM processing_work_items WHERE {' AND '.join(clauses)} ORDER BY created_at, work_item_id LIMIT ?",
                (*values, limit),
            ).fetchall()
            return [self._decode(row) for row in rows]
        finally:
            connection.close()

    def events(self, work_item_id):
        if self.get(work_item_id) is None:
            raise KeyError("processing work item does not belong to this Phoenix")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT event_json FROM processing_events WHERE instance_id=? AND work_item_id=? ORDER BY occurred_at,event_id",
                (self.instance_id, work_item_id),
            ).fetchall()
            return [json.loads(row["event_json"]) for row in rows]
        finally:
            connection.close()

    def coverage(self):
        items = self.list(limit=1000)
        statuses = {}; domains = {}
        for item in items:
            statuses[item["status"]] = statuses.get(item["status"], 0) + 1
            domains[item["domain"]] = domains.get(item["domain"], 0) + 1
        incomplete = sum(count for status, count in statuses.items() if status not in {"completed", "cancelled", "superseded"})
        failures = sum(statuses.get(status, 0) for status in ("failed_retryable", "failed_terminal", "quarantined"))
        return {
            "schema_version": 1, "record_type": "processing_coverage_projection",
            "instance_id": self.instance_id, "generated_at": self.clock.now(),
            "total": len(items), "by_status": statuses, "by_domain": domains,
            "incomplete": incomplete, "failures_or_quarantine": failures,
            "blind_spots": [] if items else ["no_registered_processing_work"],
            "bounded": len(items) < 1000,
        }

    def _insert_event(self, connection, envelope, event_type, from_status, to_status, details, operation_id):
        event_id = stable_work_id("processing-event", self.instance_id, envelope["work_item_id"], operation_id)
        event = {
            "schema_version": 1, "record_type": "phoenix_processing_event",
            "event_id": event_id, "work_item_id": envelope["work_item_id"],
            "instance_id": self.instance_id, "event_type": event_type,
            "from_status": from_status, "to_status": to_status,
            "operation_id": operation_id, "details": dict(details),
            "correlation_id": envelope.get("correlation_id"),
            "causation_id": envelope.get("causation_id"),
            "occurred_at": self.clock.now(),
        }
        connection.execute(
            "INSERT INTO processing_events VALUES (?,?,?,?,?,?,?,?)",
            (event_id, envelope["work_item_id"], self.instance_id, event_type,
             from_status, to_status, event["occurred_at"], _json(event)),
        )

    @staticmethod
    def _decode(row):
        return json.loads(row["envelope_json"]) if row is not None else None
