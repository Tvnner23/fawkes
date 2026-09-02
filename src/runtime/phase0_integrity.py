"""Read-only ownership audit and isolated complete-Phoenix recovery snapshots.

Canonical sources are copied byte-for-byte.  Legacy ownership is reported,
never inferred or rewritten.  Rebuildable projections are declared rather
than treated as canonical evidence.
"""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import uuid


ROOT = Path(__file__).resolve().parent.parent.parent
SCOPED_ROOTS = (
    "library/instances", "database/preferences", "database/capability_receipts",
    "database/provider_transmission_receipts", "database/research",
    "database/research_sessions", "database/acceptance_test_runs",
    "database/presentation", "database/processing", "database/inherited_history",
    "database/retrieval_replay",
    "database/evidence_transmissions",
    "database/worker_exchange",
    "database/development_campaigns",
)
FLAT_JSON_ROOTS = (
    "database/context_receipts", "memory/records", "memory/events",
    "memory/development", "memory/development/feedback",
    "memory/development/observations/records", "memory/development/observations/events",
    "memory/development/review",
)
REBUILDABLE = (
    "database/canonical_archive.sqlite3", "database/archive_passages.sqlite",
    "database/archive_manifest.json",
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_instance(record):
    return record.get("instance_id") if isinstance(record, dict) else None


def audit_phoenix_state(instance_id, *, root=None):
    """Return a bounded projection without mutating any audited record."""
    root = Path(root) if root else ROOT
    findings = []

    def add(component, path, status, detail=None):
        findings.append({"component": component, "path": str(path.relative_to(root)),
                         "status": status, "detail": detail})

    for relative in SCOPED_ROOTS:
        base = root / relative
        if not base.exists():
            continue
        for owner_dir in (item for item in base.iterdir() if item.is_dir()):
            for path in owner_dir.rglob("*.json"):
                record = _json(path)
                if record is None:
                    add(relative, path, "invalid", "unreadable JSON")
                    continue
                owner = _record_instance(record)
                if owner is None:
                    # Some older path-scoped schemas (preferences and
                    # acceptance completion events) did not repeat ownership
                    # inside each leaf. Report that historical limitation;
                    # never infer it into the record.
                    add(relative, path, "legacy_path_scoped", owner_dir.name)
                elif owner != owner_dir.name:
                    add(relative, path, "ownership_mismatch", f"path={owner_dir.name}; record={owner}")
                else:
                    add(relative, path, "owned" if owner == instance_id else "foreign_owned")

    seen = set()
    for relative in FLAT_JSON_ROOTS:
        base = root / relative
        if not base.exists():
            continue
        for path in base.rglob("*.json"):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            record = _json(path)
            if record is None:
                add(relative, path, "invalid", "unreadable JSON")
                continue
            owner = _record_instance(record)
            if owner is None:
                add(relative, path, "legacy_unscoped")
            else:
                add(relative, path, "owned" if owner == instance_id else "foreign_owned")

    conversations = _json(root / "conversations/registry.json") or {}
    for record in conversations.get("conversations", ()):
        owner = record.get("instance_id")
        status = "legacy_unscoped" if owner is None else ("owned" if owner == instance_id else "foreign_owned")
        findings.append({"component": "conversations", "record_id": record.get("conversation_id"),
                         "path": "conversations/registry.json", "status": status, "detail": None})

    archive_meta = root / "archive/meta"
    if archive_meta.exists():
        for path in archive_meta.glob("*.json"):
            record = _json(path)
            owner = _record_instance(record)
            status = "invalid" if record is None else ("legacy_unscoped" if owner is None else ("owned" if owner == instance_id else "foreign_owned"))
            add("canonical_archive", path, status)

    for relative, table in (("database/memory_processing.sqlite3", "memory_work_items"),
                            ("database/canonical_archive.sqlite3", "canonical_message_projection")):
        path = root / relative
        if not path.exists():
            continue
        try:
            connection = sqlite3.connect(path)
            rows = connection.execute(f"SELECT instance_id, COUNT(*) FROM {table} GROUP BY instance_id").fetchall()
            connection.close()
            for owner, count in rows:
                status = "legacy_unscoped" if owner is None else ("owned" if owner == instance_id else "foreign_owned")
                findings.append({"component": table, "path": relative, "status": status,
                                 "detail": {"instance_id": owner, "records": count}})
        except sqlite3.Error as exc:
            findings.append({"component": table, "path": relative, "status": "invalid", "detail": type(exc).__name__})

    processing_root = root / "database/processing"
    if processing_root.exists():
        for owner_dir in (item for item in processing_root.iterdir() if item.is_dir()):
            path = owner_dir / "ledger.sqlite3"
            if not path.exists():
                continue
            try:
                connection = sqlite3.connect(path)
                metadata = connection.execute(
                    "SELECT schema_version, instance_id FROM processing_ledger_metadata WHERE singleton=1"
                ).fetchone()
                owners = connection.execute(
                    "SELECT instance_id, COUNT(*) FROM processing_work_items GROUP BY instance_id"
                ).fetchall()
                connection.close()
                if metadata is None or metadata[1] != owner_dir.name or any(owner != owner_dir.name for owner, _ in owners):
                    status = "ownership_mismatch"
                else:
                    status = "owned" if owner_dir.name == instance_id else "foreign_owned"
                findings.append({"component": "processing_work_items", "path": str(path.relative_to(root)),
                                 "status": status, "detail": {"path_owner": owner_dir.name,
                                 "metadata_owner": metadata[1] if metadata else None,
                                 "record_owners": [{"instance_id": owner, "records": count} for owner, count in owners]}})
            except sqlite3.Error as exc:
                findings.append({"component": "processing_work_items", "path": str(path.relative_to(root)),
                                 "status": "invalid", "detail": type(exc).__name__})

    history_root = root / "database/inherited_history"
    if history_root.exists():
        for owner_dir in (item for item in history_root.iterdir() if item.is_dir()):
            path = owner_dir / "index.sqlite3"
            if not path.exists():
                continue
            try:
                connection = sqlite3.connect(path)
                metadata = connection.execute("SELECT schema_version,instance_id FROM staging_metadata").fetchone()
                owners = set()
                for table in ("staged_exports", "staged_conversations", "staged_nodes", "staged_messages"):
                    owners.update(row[0] for row in connection.execute(f"SELECT DISTINCT instance_id FROM {table}"))
                connection.close()
                mismatch = metadata is None or metadata[1] != owner_dir.name or any(owner != owner_dir.name for owner in owners)
                status = "ownership_mismatch" if mismatch else ("owned" if owner_dir.name == instance_id else "foreign_owned")
                findings.append({"component": "inherited_history_staging", "path": str(path.relative_to(root)),
                                 "status": status, "detail": {"path_owner": owner_dir.name,
                                 "metadata_owner": metadata[1] if metadata else None,
                                 "record_owners": sorted(owners)}})
            except sqlite3.Error as exc:
                findings.append({"component": "inherited_history_staging", "path": str(path.relative_to(root)),
                                 "status": "invalid", "detail": type(exc).__name__})

    counts = {}
    for item in findings:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    blocking = sum(counts.get(item, 0) for item in ("ownership_mismatch", "invalid"))
    return {
        "schema_version": 1, "record_type": "phoenix_state_ownership_audit",
        "instance_id": instance_id, "generated_at": _now(), "read_only": True,
        "summary": counts, "gate_satisfied": blocking == 0,
        "legacy_records_modified": False, "findings": findings,
        "rebuildable_projections": list(REBUILDABLE),
    }


def _copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _owned_json_files(instance_id, root):
    selected = []
    for relative in SCOPED_ROOTS:
        base = root / relative / instance_id
        if base.exists():
            selected.extend(path for path in base.rglob("*") if path.is_file())
    for relative in FLAT_JSON_ROOTS:
        base = root / relative
        if not base.exists():
            continue
        for path in base.rglob("*.json"):
            if _record_instance(_json(path)) == instance_id:
                selected.append(path)
    meta_root = root / "archive/meta"
    if meta_root.exists():
        for meta in meta_root.glob("*.json"):
            record = _json(meta)
            if _record_instance(record) != instance_id:
                continue
            selected.append(meta)
            archive_id = record.get("archive_id")
            if archive_id:
                selected.extend(path for path in (root / "archive/raw").glob(f"{archive_id}.*") if path.is_file())
    return sorted(set(selected))


def _filtered_registries(instance_id, source_root, files_root):
    instances = _json(source_root / "instances/registry.json") or {"schema_version": 1, "instances": []}
    selected_instances = [item for item in instances.get("instances", ()) if item.get("instance_id") == instance_id]
    if len(selected_instances) != 1:
        raise ValueError("backup requires exactly one registered Phoenix instance")
    conversations = _json(source_root / "conversations/registry.json") or {"schema_version": 1, "conversations": []}
    selected_conversations = [item for item in conversations.get("conversations", ()) if item.get("instance_id") == instance_id]
    for relative, payload in (
        ("instances/registry.json", {"schema_version": instances.get("schema_version", 1), "instances": selected_instances}),
        ("conversations/registry.json", {"schema_version": conversations.get("schema_version", 1), "conversations": selected_conversations}),
    ):
        path = files_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _filtered_work_ledger(instance_id, source_root, files_root):
    source = source_root / "database/memory_processing.sqlite3"
    if not source.exists():
        return
    target = files_root / "database/memory_processing.sqlite3"
    target.parent.mkdir(parents=True, exist_ok=True)
    origin, copy = sqlite3.connect(source), sqlite3.connect(target)
    origin.backup(copy)
    copy.execute("DELETE FROM memory_work_items WHERE instance_id != ?", (instance_id,))
    copy.commit(); copy.close(); origin.close()


def create_complete_state_backup(instance_id, backup_root, *, source_root=None):
    source_root = Path(source_root) if source_root else ROOT
    audit = audit_phoenix_state(instance_id, root=source_root)
    if not audit["gate_satisfied"]:
        raise ValueError("ownership/integrity audit has blocking findings")
    backup = Path(backup_root) / f"phoenix-{instance_id}-{uuid.uuid4()}"
    files_root = backup / "files"
    files_root.mkdir(parents=True, exist_ok=False)
    for source in _owned_json_files(instance_id, source_root):
        _copy_file(source, files_root / source.relative_to(source_root))
    _filtered_registries(instance_id, source_root, files_root)
    _filtered_work_ledger(instance_id, source_root, files_root)
    entries = [{"path": str(path.relative_to(files_root)), "sha256": _hash(path),
                "size_bytes": path.stat().st_size}
               for path in sorted(files_root.rglob("*")) if path.is_file()]
    manifest = {
        "schema_version": 1, "record_type": "complete_phoenix_state_backup",
        "backup_id": str(uuid.uuid4()), "instance_id": instance_id,
        "created_at": _now(), "files": entries,
        "legacy_unscoped_excluded": audit["summary"].get("legacy_unscoped", 0),
        "legacy_path_scoped_included": audit["summary"].get("legacy_path_scoped", 0),
        "rebuildable_projections_excluded": list(REBUILDABLE),
        "secret_material_included": False,
        "restore_mode": "empty_isolated_root_only",
    }
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return backup, manifest


def verify_complete_state_backup(backup_dir, *, expected_instance_id=None):
    backup = Path(backup_dir)
    manifest = _json(backup / "manifest.json")
    if not manifest or manifest.get("record_type") != "complete_phoenix_state_backup":
        raise ValueError("invalid complete-state backup manifest")
    if expected_instance_id and manifest.get("instance_id") != expected_instance_id:
        raise ValueError("backup belongs to a different Phoenix instance")
    expected = {item["path"]: item for item in manifest.get("files", ())}
    actual = {str(path.relative_to(backup / "files")): path for path in (backup / "files").rglob("*") if path.is_file()}
    if set(actual) != set(expected):
        raise ValueError("backup file inventory mismatch")
    for relative, path in actual.items():
        if _hash(path) != expected[relative]["sha256"] or path.stat().st_size != expected[relative]["size_bytes"]:
            raise ValueError("backup integrity verification failed")
    return manifest


def restore_complete_state_backup(backup_dir, target_root, *, instance_id):
    manifest = verify_complete_state_backup(backup_dir, expected_instance_id=instance_id)
    target = Path(target_root)
    if target.exists() and any(target.iterdir()):
        raise ValueError("complete-state restore target must be empty")
    source = Path(backup_dir) / "files"
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if path.is_file():
            _copy_file(path, target / path.relative_to(source))
    receipt = {"schema_version": 1, "record_type": "complete_phoenix_restore_receipt",
               "instance_id": instance_id, "backup_id": manifest["backup_id"],
               "restored_at": _now(), "target_was_empty": True,
               "archive_sources_copied_byte_for_byte": True}
    path = target / "database/recovery/restore_receipt.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt
