"""Exact, atomic production releases built from the Development workspace.

Release code is immutable after materialization. Durable Fawkes state remains
in the established canonical workspace paths and is linked into each release;
promotion changes code, never Phoenix identity or continuity.
"""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import uuid


DEVELOPMENT_ROOT = Path("/home/tvnner/fawkes")
PRODUCTION_ROOT = Path("/home/tvnner/.local/lib/fawkes-production")
RELEASES_ROOT = PRODUCTION_ROOT / "releases"
CURRENT_LINK = PRODUCTION_ROOT / "current"
PREVIOUS_LINK = PRODUCTION_ROOT / "previous"
SHARED_STATE = {
    "archive": DEVELOPMENT_ROOT / "archive",
    "database": DEVELOPMENT_ROOT / "database",
    "memory": DEVELOPMENT_ROOT / "memory",
    "library": DEVELOPMENT_ROOT / "library",
    "conversations": DEVELOPMENT_ROOT / "conversations",
    "instances": DEVELOPMENT_ROOT / "instances",
    "backups": DEVELOPMENT_ROOT / "backups",
    "logs": DEVELOPMENT_ROOT / "logs",
}
SCRIPT_NAMES = {
    "run_fawkes_discord_bot.py", "initialize_fawkes_discord_cursors.py",
    "fawkes_component_failure.py", "fawkes_failure_notifier.py",
    "show_fawkes_component_receipts.py", "wait_fawkes_app_ready.py",
    "fawkes_stack_status.sh", "fawkes_attention_events.py",
    "verify_fawkes_production_prerequisites.py",
}
DEVELOPMENT_RUNTIME_CLOSURE = frozenset({
    "src/runtime/codex_app_server.py",
    "src/runtime/development_attention.py",
    "src/runtime/codex_development_campaign.py",
    "src/runtime/codex_development_handoff.py",
    "src/runtime/codex_worker_adapter.py",
    "src/runtime/codex_write_builder_adapter.py",
    "src/runtime/wsl_codex_reviewer.py",
    "src/runtime/worker_exchange.py",
    "src/app/server.py",
    "src/app/static/app.js",
    "scripts/fawkes_attention_events.py",
})


def _digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def release_files(source=DEVELOPMENT_ROOT):
    source = Path(source).resolve()
    paths = [source / "requirements.txt"]
    paths.extend((source / "src").rglob("*.py"))
    paths.extend(path for path in (source / "src/app/static").rglob("*") if path.is_file())
    paths.extend(path for path in (source / "config").rglob("*") if path.is_file())
    paths.extend(source / "scripts" / name for name in sorted(SCRIPT_NAMES))
    result = []
    for path in sorted(set(paths), key=lambda item: item.relative_to(source).as_posix()):
        resolved = path.resolve(strict=True)
        resolved.relative_to(source)
        if not resolved.is_file():
            raise ValueError(f"production source is not a regular file: {path}")
        result.append((path.relative_to(source).as_posix(), resolved))
    if source == DEVELOPMENT_ROOT:
        included = {relative for relative, _ in result}
        missing = DEVELOPMENT_RUNTIME_CLOSURE - included
        if missing:
            raise ValueError("production Development runtime closure is incomplete: " + ", ".join(sorted(missing)))
    return result


def materialize_release(*, source=DEVELOPMENT_ROOT, production_root=PRODUCTION_ROOT,
                        validation_reference):
    source, production_root = Path(source).resolve(), Path(production_root)
    releases = production_root / "releases"
    entries = []
    for relative, path in release_files(source):
        body = path.read_bytes()
        entries.append({"path": relative, "sha256": _digest_bytes(body), "size_bytes": len(body)})
    identity_body = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    release_id = "fawkes-release-" + _digest_bytes(identity_body)
    target = releases / release_id
    if target.exists():
        verify_release(target)
        return json.loads((target / "release.json").read_text())
    staging = releases / f".{release_id}.{uuid.uuid4().hex}.staging"
    staging.mkdir(parents=True, mode=0o755)
    try:
        for entry in entries:
            source_path = source / entry["path"]
            destination = staging / entry["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination)
            os.chmod(destination, 0o755 if entry["path"].startswith("scripts/") else 0o644)
        for name, canonical in SHARED_STATE.items():
            if source == DEVELOPMENT_ROOT:
                link_target = canonical
            else:
                link_target = source / name
            if link_target.exists():
                (staging / name).symlink_to(link_target, target_is_directory=True)
        record = {"schema_version": 1, "release_id": release_id,
                  "created_at": datetime.now(timezone.utc).isoformat(),
                  "source_root": str(source), "validation_reference": validation_reference,
                  "files": entries, "state_links": {
                      name: str((DEVELOPMENT_ROOT / name) if source == DEVELOPMENT_ROOT else source / name)
                      for name in SHARED_STATE},
                  "creates_phoenix_identity": False}
        record["manifest_sha256"] = _digest_bytes(json.dumps(
            record, sort_keys=True, separators=(",", ":")).encode())
        (staging / "release.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        os.chmod(staging / "release.json", 0o444)
        staging.rename(target)
        for path in target.rglob("*"):
            if path.is_file() and not path.is_symlink():
                os.chmod(path, path.stat().st_mode & ~0o222)
        return record
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_release(path):
    path = Path(path).resolve()
    record = json.loads((path / "release.json").read_text())
    claimed = record.pop("manifest_sha256")
    actual = _digest_bytes(json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
    if claimed != actual:
        raise ValueError("production release manifest integrity mismatch")
    for entry in record["files"]:
        candidate = (path / entry["path"]).resolve(strict=True)
        candidate.relative_to(path)
        if _digest_bytes(candidate.read_bytes()) != entry["sha256"]:
            raise ValueError(f"production release file digest mismatch: {entry['path']}")
    return {**record, "manifest_sha256": claimed}


def _atomic_link(link, target):
    link.parent.mkdir(parents=True, exist_ok=True)
    temporary = link.with_name(f".{link.name}.{uuid.uuid4().hex}.tmp")
    temporary.symlink_to(target)
    temporary.replace(link)


def _release_event(root, action, record, previous=None):
    event_root = Path(root) / "release-events"
    event_root.mkdir(parents=True, exist_ok=True)
    value = {"schema_version": 1, "event_id": f"release-event-{uuid.uuid4()}",
             "timestamp_utc": datetime.now(timezone.utc).isoformat(), "action": action,
             "release_id": record["release_id"], "manifest_sha256": record["manifest_sha256"],
             "previous_release_id": previous, "creates_phoenix_identity": False}
    path = event_root / f"{value['timestamp_utc'].replace(':', '')}-{value['event_id']}.json"
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return value


def promote_release(release_id, *, production_root=PRODUCTION_ROOT):
    root = Path(production_root)
    target = root / "releases" / release_id
    record = verify_release(target)
    current = root / "current"
    previous = root / "previous"
    previous_id = None
    if current.is_symlink():
        previous_id = current.resolve().name
        _atomic_link(previous, current.resolve())
    _atomic_link(current, target.resolve())
    _release_event(root, "promote", record, previous_id)
    return record


def rollback_release(*, production_root=PRODUCTION_ROOT):
    root = Path(production_root)
    previous = root / "previous"
    if not previous.is_symlink():
        raise RuntimeError("no previous approved Fawkes release is available")
    target = previous.resolve()
    verify_release(target)
    current = root / "current"
    old_current = current.resolve() if current.is_symlink() else None
    _atomic_link(current, target)
    if old_current is not None:
        _atomic_link(previous, old_current)
    record = verify_release(target)
    _release_event(root, "rollback", record, old_current.name if old_current else None)
    return record
