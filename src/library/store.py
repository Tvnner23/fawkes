"""Immutable Library originals and rebuildable structured extractions."""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import uuid
import re
import os

from src.library.artifacts import (
    lifecycle_event, source_artifact_envelope, stable_work_id,
    validate_retention_intent,
)
from src.library.storage import (
    LocalImmutableBlobStore, create_verified_backup, restore_verified_backup, confined_path,
)


ROOT = Path(__file__).resolve().parent.parent.parent
# Use the verified launcher's physical state root, not the release symlink.
# Explicit roots and stored references still pass strict symlink confinement.
STATE_ROOT = Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
LIBRARY_ROOT = STATE_ROOT / "library"
ORIGINALS_DIR = LIBRARY_ROOT / "originals"
SOURCES_DIR = LIBRARY_ROOT / "sources"
EXTRACTIONS_DIR = LIBRARY_ROOT / "extractions"
_INSTANCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def instance_library_paths(instance_id, *, library_root=None):
    """Resolve physically isolated defaults for one Phoenix's Library."""
    if not isinstance(instance_id, str) or not _INSTANCE_ID.fullmatch(instance_id):
        raise ValueError("valid instance_id is required for default Library storage")
    root = Path(library_root) if library_root else LIBRARY_ROOT
    scoped = root / "instances" / instance_id
    return {
        "root": scoped, "originals": scoped / "originals",
        "sources": scoped / "sources", "extractions": scoped / "extractions",
        "events": scoped / "events",
    }


def _atomic_write(path, payload):
    path = confined_path(path.parent, path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open('xb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            # Deterministic records are immutable: racing retries read the
            # winning record, rather than replacing its authority or timestamp.
            pass
    finally:
        if temporary.exists():
            temporary.unlink()


def _storage_directory(directory):
    directory = Path(directory)
    return confined_path(directory.parent, directory.name)


def _metadata_paths(directory):
    directory = _storage_directory(directory)
    if not directory.exists():
        return ()
    paths = []
    for path in directory.glob('*.json'):
        path = confined_path(directory, path.name)
        if not path.is_file():
            raise ValueError('Library metadata must be a regular file')
        paths.append(path)
    return tuple(paths)


def _write_json_once(path, payload):
    path = confined_path(path.parent, path.name)
    encoded = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        return existing
    _atomic_write(path, encoded)
    return json.loads(confined_path(path.parent, path.name).read_text(encoding='utf-8'))


def _ensure_registered_events(source, events):
    """Complete an interrupted schema2 registration from its saved authority.

    Legacy records remain legacy; retries must not invent ownership or migrate
    them. Existing event bytes are preserved and checked against their identity.
    """
    if source.get('schema_version') != 2:
        return
    artifact = source['artifact']
    identifiers = artifact.get('identifiers', {})
    work_id = source['retention_work_id']
    source_id = source['source_id']
    requested = lifecycle_event(
        instance_id=source['instance_id'], artifact_id=source_id,
        event_type='library.retention.requested', from_state='validated_temporary',
        to_state='retention_requested', actor=artifact['actor'],
        idempotency_key=stable_work_id('retention-request', work_id),
        correlation_id=identifiers.get('correlation_id'), causation_id=identifiers.get('causation_id'),
        details={'temporary_source_reference': next((edge.get('target_id')
            for edge in artifact.get('provenance', ()) if edge.get('relation')=='derived_from'), None)})
    registered = lifecycle_event(
        instance_id=source['instance_id'], artifact_id=source_id,
        event_type='library.artifact.durable_registered', from_state='retention_requested',
        to_state='durable_registered', actor=artifact['actor'], idempotency_key=work_id,
        correlation_id=identifiers.get('correlation_id'), causation_id=requested['event_id'],
        details={'source_id':source_id,'sha256':source['sha256']})
    for event in (requested, registered):
        path = events / f"{hashlib.sha256(event['event_id'].encode()).hexdigest()}.json"
        retained = _write_json_once(path, event)
        if (not isinstance(retained, dict)
                or {k:v for k,v in retained.items() if k!='occurred_at'}
                != {k:v for k,v in event.items() if k!='occurred_at'}):
            raise ValueError('Library lifecycle record conflicts with saved registration')


def _load_sources(directory):
    records = []
    for path in _metadata_paths(directory):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(record, dict) and record.get("schema_version") in {1, 2}:
                records.append(record)
        except (OSError, json.JSONDecodeError):
            continue
    return tuple(records)


def register_source(
    raw_bytes,
    *,
    title,
    media_type,
    original_filename=None,
    instance_id=None,
    retention_intent=None,
    privacy="potentially_private",
    evidence_era="native_phoenix_history",
    source_domain="rider_supplied",
    provenance=(),
    rights=None,
    encryption=None,
    correlation_id=None,
    causation_id=None,
    originals_dir=None,
    sources_dir=None,
    events_dir=None,
):
    """Register external source material without converting it into memory."""
    if not isinstance(raw_bytes, bytes) or not raw_bytes:
        raise ValueError("raw_bytes must be non-empty bytes")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title is required")
    if not isinstance(media_type, str) or not media_type.strip():
        raise ValueError("media_type is required")

    provenance = tuple(provenance)
    custom_storage = any(value is not None for value in (
        originals_dir, sources_dir, events_dir,
    ))
    if custom_storage and not all(value is not None for value in (
        originals_dir, sources_dir, events_dir,
    )):
        raise ValueError(
            "custom Library storage requires originals_dir, sources_dir, and events_dir"
        )

    # Ownership and durable retention are never inferred from a path, caller,
    # filename, or old record.  Legacy records remain readable but all new
    # writes use the explicit contract.
    paths = instance_library_paths(instance_id)
    intent = validate_retention_intent(retention_intent)
    if privacy not in {"standard", "potentially_private", "highly_private", "restricted"}:
        raise ValueError("invalid Library privacy classification")

    originals = _storage_directory(originals_dir if originals_dir else paths["originals"])
    sources = _storage_directory(sources_dir if sources_dir else paths["sources"])
    events = _storage_directory(events_dir if events_dir else paths["events"])
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    for existing in _load_sources(sources):
        if (
            existing.get("sha256") == sha256
            and existing.get("instance_id") == instance_id
        ):
            blob = existing.get("original_blob")
            if not blob or not LocalImmutableBlobStore(originals).verify(blob, sha256):
                raise ValueError("existing Library source failed blob integrity verification")
            existing_owner = existing.get("artifact", {}).get("owner_principal_id")
            if existing_owner is not None and existing_owner != intent["principal_id"]:
                raise PermissionError("existing Library artifact belongs to a different owner principal")
            _ensure_registered_events(existing, events)
            return {**existing, "_replayed": True}

    source_id = "source:" + hashlib.sha256(f"{instance_id}:{sha256}".encode()).hexdigest()
    suffix = Path(original_filename).suffix.lower() if original_filename else ".bin"
    blob_name = f"{sha256}{suffix or '.bin'}"
    blob_path = originals / blob_name
    blob_store = LocalImmutableBlobStore(originals)
    blob_store.put(raw_bytes, filename=blob_name)

    created_at = datetime.now(timezone.utc).isoformat()
    artifact = source_artifact_envelope(
        artifact_id=source_id, instance_id=instance_id,
        owner_principal_id=intent["principal_id"], artifact_kind="library_source",
        source_domain=source_domain, evidence_era=evidence_era, sha256=sha256,
        media_type=media_type.strip().lower(), storage_reference=blob_name,
        lifecycle_state="durable_registered",
        privacy={"classification": privacy, "assigned_by": intent["actor_type"],
                 "rider_visible": True, "revisable": True},
        trust="untrusted_library_content", retention=intent,
        actor={"actor_type": intent["actor_type"], "principal_id": intent["principal_id"]},
        provenance=provenance, rights=rights,
        resource={"size_bytes": len(raw_bytes), "quota_class": "library_original"},
        encryption=encryption, created_at=created_at,
        identifiers={"library_source_id": source_id, "correlation_id": correlation_id,
                     "causation_id": causation_id, "sandbox_branch_id": None,
                     "environment_id": None, "device_id": None, "sensor_id": None,
                     "actuator_id": None, "embodiment_id": None, "session_id": None},
    )
    retention_work_id = stable_work_id("retain", instance_id, sha256, intent)

    record = {
        "schema_version": 2,
        "record_type": "library_source",
        "source_id": source_id,
        "instance_id": instance_id,
        "title": title.strip(),
        "media_type": media_type.strip().lower(),
        "original_filename": original_filename,
        "created_at": created_at,
        "sha256": sha256,
        "size_bytes": len(raw_bytes),
        "original_blob": blob_name,
        "immutability": "content-addressed-original",
        "retention_work_id": retention_work_id,
        "artifact": artifact,
    }
    saved = _write_json_once(sources / f"{source_id}.json", record)
    if (saved.get('instance_id') != instance_id or saved.get('sha256') != sha256
            or saved.get('artifact', {}).get('owner_principal_id') != intent['principal_id']):
        raise ValueError('Library source conflicts with the saved registration owner')
    _ensure_registered_events(saved, events)
    return {**saved, "_replayed": False}


def _normalise_location(location):
    if not isinstance(location, dict):
        raise ValueError("segment location must be an object")
    page_number = location.get("page_number")
    if page_number is not None and (
        type(page_number) is not int or page_number <= 0
    ):
        raise ValueError("page_number must be a positive integer or null")
    normalized = {"page_number": page_number}
    for field in ("page_label", "chapter", "section", "subsection", "source_locator"):
        value = location.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"segment location {field} must be a string or null")
        # Empty optional labels are unavailable, never citation evidence. A
        # reliable physical page still suffices when a PDF has a blank label.
        normalized[field] = (value.strip() or None) if value is not None else None
    if not any(value is not None for value in normalized.values()):
        raise ValueError("segment must retain at least one source location")
    return normalized


def save_extraction(
    source_id,
    segments,
    *,
    extractor,
    extractor_version,
    sources_dir=None,
    extractions_dir=None,
    events_dir=None,
    instance_id=None,
    metadata=None,
):
    """Save a versioned, rebuildable structural interpretation of a source."""
    paths = instance_library_paths(instance_id)
    custom_storage = any(value is not None for value in (sources_dir, extractions_dir, events_dir))
    if custom_storage and not all(value is not None for value in (sources_dir, extractions_dir, events_dir)):
        raise ValueError("custom extraction storage requires sources_dir, extractions_dir, and events_dir")
    sources = _storage_directory(sources_dir if sources_dir else paths["sources"])
    extractions = _storage_directory(extractions_dir if extractions_dir else paths["extractions"])
    events = _storage_directory(events_dir if events_dir else paths["events"])
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("valid Library source_id is required")
    source_path = confined_path(sources, f"{source_id}.json")
    if not source_path.exists():
        raise ValueError("unknown Library source_id")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if source.get("instance_id") != instance_id:
        raise ValueError("Library source belongs to a different Phoenix instance")
    if not extractor or not extractor_version:
        raise ValueError("extractor and extractor_version are required")

    normalized_segments = []
    for ordinal, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError("each segment must be an object")
        text = segment.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("segment text is required")
        normalized_segments.append(
            {
                "segment_id": segment.get("segment_id") or f"segment-{ordinal + 1}",
                "ordinal": ordinal,
                "text": text.strip(),
                "location": _normalise_location(segment.get("location")),
            }
        )

    identity = json.dumps(
        {
            "source_id": source_id,
            "source_sha256": source["sha256"],
            "extractor": extractor,
            "extractor_version": extractor_version,
            "segments": normalized_segments,
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    extraction_id = hashlib.sha256(identity).hexdigest()
    extraction_work_id = stable_work_id(
        "extract", instance_id, source_id, source["sha256"], extractor, extractor_version
    )
    record = {
        "schema_version": 2,
        "record_type": "library_extraction",
        "extraction_id": extraction_id,
        "instance_id": source.get("instance_id"),
        "source_id": source_id,
        "source_sha256": source["sha256"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "extractor": extractor,
        "extractor_version": extractor_version,
        "status": "derived_rebuildable",
        "extraction_work_id": extraction_work_id,
        "provenance": [{"relation": "extracted_from", "target_kind": "library_source",
                        "target_id": source_id}],
        "metadata": dict(metadata or {}),
        "segments": normalized_segments,
    }
    saved = _write_json_once(extractions / f"{extraction_id}.json", record)
    pending = lifecycle_event(
        instance_id=instance_id, artifact_id=source_id,
        event_type="library.extraction.pending", from_state="durable_registered",
        to_state="extraction_pending", actor={"actor_type": "runtime"},
        idempotency_key=extraction_work_id,
        details={"extraction_id": extraction_id, "extractor": extractor,
                 "extractor_version": extractor_version},
    )
    searchable = lifecycle_event(
        instance_id=instance_id, artifact_id=source_id,
        event_type="library.extraction.searchable", from_state="extraction_pending",
        to_state="searchable", actor={"actor_type": "runtime"},
        idempotency_key=stable_work_id("searchable", extraction_work_id),
        causation_id=pending["event_id"],
        details={"extraction_id": extraction_id, "segment_count": len(normalized_segments)},
    )
    for event in (pending, searchable):
        _write_json_once(events / f"{hashlib.sha256(event['event_id'].encode()).hexdigest()}.json", event)
    return saved


def record_extraction_failure(
    source_id, *, extractor, extractor_version, error_code, instance_id,
    events_dir=None, correlation_id=None,
):
    """Append a retryable derivation failure without changing the original.

    Failure details are deliberately limited to a stable class/code. Provider
    payloads, document text, and stack traces never enter lifecycle evidence.
    """
    paths = instance_library_paths(instance_id)
    events = _storage_directory(events_dir if events_dir else paths["events"])
    work_id = stable_work_id(
        "extract", instance_id, source_id, extractor, extractor_version
    )
    event = lifecycle_event(
        instance_id=instance_id, artifact_id=source_id,
        event_type="library.extraction.failed", from_state="extraction_pending",
        to_state="failed", actor={"actor_type": "runtime"},
        idempotency_key=stable_work_id("extraction-failure", work_id, error_code),
        correlation_id=correlation_id,
        details={"extractor": extractor, "extractor_version": extractor_version,
                 "error_code": str(error_code), "retryable": True,
                 "original_preserved": True},
    )
    return _write_json_once(
        events / f"{hashlib.sha256(event['event_id'].encode()).hexdigest()}.json",
        event,
    )


def list_extractions(*, instance_id, source_id=None, library_root=None):
    paths = instance_library_paths(instance_id, library_root=library_root)
    records = []
    for path in _metadata_paths(paths['extractions']):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if item.get("instance_id") != instance_id:
            continue
        if source_id is not None and item.get("source_id") != source_id:
            continue
        records.append(item)
    return tuple(sorted(records, key=lambda item: item.get("created_at", ""), reverse=True))


def list_sources(*, instance_id, library_root=None):
    paths = instance_library_paths(instance_id, library_root=library_root)
    return tuple(
        source for source in _load_sources(paths["sources"])
        if source.get("instance_id") == instance_id
    )


def search_extractions(query, *, instance_id, limit=10, library_root=None):
    """Rebuildable local lexical retrieval with exact Library provenance."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Library query is required")
    paths = instance_library_paths(instance_id, library_root=library_root)
    sources = {item["source_id"]: item for item in list_sources(
        instance_id=instance_id, library_root=library_root
    )}
    terms = tuple(dict.fromkeys(re.findall(r"[A-Za-z0-9]+", query.casefold())))
    results = []
    for path in _metadata_paths(paths['extractions']):
        try:
            extraction = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source = sources.get(extraction.get("source_id"))
        if source is None:
            continue
        for segment in extraction.get("segments", ()):
            haystack = segment.get("text", "").casefold()
            matched = [term for term in terms if term in haystack]
            if not matched:
                continue
            results.append({
                "source_id": source["source_id"], "source_title": source["title"],
                "source_sha256": source["sha256"],
                "extraction_id": extraction["extraction_id"],
                "extractor": extraction["extractor"],
                "extractor_version": extraction["extractor_version"],
                "segment_id": segment["segment_id"], "text": segment["text"],
                "location": segment["location"], "matched_terms": matched,
                "retrieval_score": len(matched) / max(1, len(terms)),
                "trust": "untrusted_library_content",
            })
    return sorted(
        results,
        key=lambda item: (item["retrieval_score"], len(item["matched_terms"])),
        reverse=True,
    )[:max(0, int(limit))]


def backup_instance_library(instance_id, backup_root, *, library_root=None):
    paths = instance_library_paths(instance_id, library_root=library_root)
    return create_verified_backup(paths["root"], backup_root, instance_id=instance_id)


def restore_instance_library(instance_id, backup_dir, *, library_root=None):
    paths = instance_library_paths(instance_id, library_root=library_root)
    return restore_verified_backup(backup_dir, paths["root"], instance_id=instance_id)
