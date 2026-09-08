from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import uuid
from contextlib import contextmanager
import threading
from src.capture.storage import metadata_paths, read_metadata, validate_metadata

ROOT = Path(__file__).resolve().parent.parent
STATE_ROOT = Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
RAW_DIR = STATE_ROOT / "archive" / "raw"
META_DIR = STATE_ROOT / "archive" / "meta"

RAW_DIR.mkdir(parents=True, exist_ok=True)
META_DIR.mkdir(parents=True, exist_ok=True)
_INGEST_LOCK = threading.RLock()


def _sync_directory(path):
    if os.name=='posix':
        fd=os.open(path,os.O_RDONLY | os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)


def _durable_directory(path):
    path=Path(path).absolute()
    if path.resolve()!=path:raise ValueError('Archive storage cannot traverse a symlink')
    path.mkdir(parents=True,exist_ok=True)
    # Existing names may come from a previous interrupted publication. Fence
    # both their entries and all ancestor entries before acknowledging replay.
    for directory in (path,*path.parents):_sync_directory(directory)
    return path


@contextmanager
def _serialized_ingest(meta_dir=None):
    """Serialize event identity checks and immutable publication locally."""
    with _INGEST_LOCK:
        directory=META_DIR if meta_dir is None else Path(meta_dir)
        directory=_durable_directory(directory)
        lock = directory/'.ingest.lock'
        if lock.is_symlink():raise ValueError('Archive lock must not be a symlink')
        fd=os.open(lock,os.O_RDWR | os.O_CREAT | getattr(os,'O_NOFOLLOW',0),0o600)
        acquired=False
        try:
            if os.fstat(fd).st_size==0:os.write(fd,b'0');os.fsync(fd)
            if os.name=='posix':
                import fcntl
                fcntl.flock(fd,fcntl.LOCK_EX)
            elif os.name=='nt':
                import msvcrt
                os.lseek(fd,0,os.SEEK_SET);msvcrt.locking(fd,msvcrt.LK_LOCK,1)
            else:raise RuntimeError('No supported Archive identity lock')
            acquired=True
            yield
        finally:
            try:
                if acquired:
                    if os.name=='posix':fcntl.flock(fd,fcntl.LOCK_UN)
                    else:os.lseek(fd,0,os.SEEK_SET);msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
            finally:os.close(fd)


def read_archived_bytes(metadata):
    """Read the exact retained blob; corrupted/escaping references fail closed."""
    name=metadata.get('raw_file')
    if not isinstance(name,str) or not name or Path(name).name!=name or '/' in name or '\\' in name:
        raise ValueError('Archive raw-file reference is not a local filename')
    path=RAW_DIR/name
    if path.is_symlink() or path.resolve().parent!=RAW_DIR.resolve() or not path.is_file():
        raise ValueError('Archive raw-file reference is unavailable or outside storage')
    value=path.read_bytes()
    if hashlib.sha256(value).hexdigest()!=metadata.get('sha256') or len(value)!=metadata.get('size_bytes'):
        raise ValueError('Retained Archive bytes do not match their metadata')
    return value


def find_duplicate(sha256: str, *, binding=None):
    for meta_path in metadata_paths(META_DIR):
        metadata = read_metadata(meta_path)

        if isinstance(metadata,dict) and metadata.get("sha256") == sha256 and (binding is None or all(metadata.get(key)==value for key,value in binding.items())):
            return metadata

    return None


def find_capture_event(capture_event_id: str):
    """Return an already archived capture event, when present."""
    matches=[]
    for meta_path in metadata_paths(META_DIR):
        metadata = read_metadata(meta_path)

        if isinstance(metadata,dict) and metadata.get("capture_event_id") == capture_event_id:
            matches.append(metadata)

    if len(matches)>1:raise ValueError('Capture event has ambiguous retained identities; explicit recovery required')
    if matches:return matches[0]

    return None


def _atomic_write_bytes(path: Path, payload: bytes):
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open('xb') as output:
        output.write(payload);output.flush();os.fsync(output.fileno())
    # Archive objects are new identities, never replace existing evidence.
    try:os.link(temporary,path)
    finally:temporary.unlink()
    _sync_directory(path.parent)


def _atomic_write_json(path: Path, payload: dict):
    validate_metadata(payload,path)
    encoded = (
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")
    _atomic_write_bytes(path, encoded)


def ingest_bytes(*args,**kwargs):
    with _serialized_ingest():
        return _ingest_bytes(*args,**kwargs)


def _ingest_bytes(
    raw_bytes: bytes,
    title: str,
    source: str,
    capture_type: str,
    original_filename=None,
    encoding=None,
    instance_id=None,
    conversation_id=None,
    capture_event_id=None,
    emit_receipt=True,
):
    _durable_directory(RAW_DIR)
    _durable_directory(META_DIR)
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    binding={'sha256':sha256,'size_bytes':len(raw_bytes),'title':title,
        'ingest_method':source,'capture_type':capture_type,'encoding':encoding,
        'instance_id':instance_id,'conversation_id':conversation_id,'original_filename':original_filename}
    if capture_event_id is not None:
        if not isinstance(capture_event_id, str) or not capture_event_id.strip():
            raise ValueError("capture_event_id must be a non-empty string or null")

        existing_event = find_capture_event(capture_event_id)

        if existing_event is not None:
            if any(existing_event.get(key)!=value for key,value in binding.items()):
                raise ValueError('capture_event_id already binds different payload or metadata')
            if read_archived_bytes(existing_event)!=raw_bytes:
                raise ValueError('Capture replay does not match retained evidence')
            return {
                **existing_event,
                "_capture_event_replayed": True,
            }

    duplicate = find_duplicate(sha256)
    if capture_event_id is None:
        duplicate = find_duplicate(sha256,binding=binding) or duplicate
    if duplicate is not None:
        read_archived_bytes(duplicate)

    if duplicate and capture_event_id is None and all(duplicate.get(key)==value for key,value in binding.items()):
        if emit_receipt:
            print("Duplicate detected: archive not written again.")
            print(f'Existing Archive ID: {duplicate["archive_id"]}')
            print(f"SHA-256: {sha256}")
        return duplicate

    archive_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    extension = Path(original_filename).suffix if original_filename else ".bin"

    if duplicate is not None:
        raw_filename = duplicate["raw_file"]
    else:
        raw_filename = f"{archive_id}{extension}"

    raw_path = RAW_DIR / raw_filename
    meta_path = META_DIR / f"{archive_id}.json"

    if duplicate is None:
        _atomic_write_bytes(raw_path, raw_bytes)

    metadata = {
        "schema_version": 2 if capture_event_id is not None else 1,
        "archive_id": archive_id,
        "capture_event_id": capture_event_id,
        "title": title,
        "created_at": created_at,
        "sha256": sha256,
        "raw_file": raw_filename,
        "original_filename": original_filename,
        "size_bytes": len(raw_bytes),
        "ingest_method": source,
        "capture_type": capture_type,
        "encoding": encoding,
        "instance_id": instance_id,
        "conversation_id": conversation_id,
        "blob_reused": duplicate is not None,
    }

    _atomic_write_json(meta_path, metadata)

    if emit_receipt:
        print(f"Archived: {archive_id}")
        print(f"SHA-256: {sha256}")

    return {
        **metadata,
        "_capture_event_replayed": False,
    }
