"""Narrow instance-scoped immutable blob and recovery boundary."""

from pathlib import Path
import hashlib
import json
import shutil
import re
import uuid
from datetime import datetime, timezone


def confined_path(root, reference):
    """Reject ambiguous, escaping and symlinked stored references.

    The local store assumes its parent directories are owned by the runtime;
    this is not a sandbox against concurrent filesystem mutation by that owner.
    """
    root = Path(root)
    if (not isinstance(reference, str) or not reference or '\\' in reference
            or '\x00' in reference or any(p in {'', '.', '..'} for p in reference.split('/'))
            or Path(reference).is_absolute()):
        raise ValueError("invalid Library storage reference")
    path = root / reference
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Library storage reference must not traverse a symlink")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Library storage reference escapes its root")
    return path


class LocalImmutableBlobStore:
    def __init__(self, root):
        self.root = Path(root)

    def put(self, raw_bytes, *, filename):
        digest = hashlib.sha256(raw_bytes).hexdigest()
        path = confined_path(self.root, filename)
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("existing Library blob failed integrity verification")
            return path, True
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(raw_bytes)
        temporary.replace(path)
        return path, False

    def verify(self, reference, expected_sha256):
        path = confined_path(self.root, reference)
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256

    def open_bytes(self, reference, expected_sha256):
        path = confined_path(self.root, reference)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ValueError("Library blob failed integrity verification")
        return data


def _files(root):
    root = Path(root)
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("Library backup integrity: symlink root")
    files = []
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Library backup integrity: unsupported file type")
        if path.is_file():
            files.append(path)
    return sorted(files)


def _instance(instance_id):
    if not isinstance(instance_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', instance_id):
        raise ValueError("invalid Library backup instance_id")


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("backup integrity: duplicate manifest field")
        result[key] = value
    return result


def create_verified_backup(source_root, backup_root, *, instance_id):
    _instance(instance_id)
    source_root, backup_root = Path(source_root), Path(backup_root)
    _files(source_root)
    target = confined_path(backup_root, f"{instance_id}-{uuid.uuid4()}")
    if target.resolve().is_relative_to(source_root.resolve()):
        raise ValueError("backup destination must be outside the Library source")
    target.mkdir(parents=True, exist_ok=False)
    if source_root.exists():
        shutil.copytree(source_root, target / "library", dirs_exist_ok=False, symlinks=True)
    else:
        (target / "library").mkdir()
    manifest = {
        "schema_version": 1, "record_type": "phoenix_library_backup",
        "instance_id": instance_id,
        "event_type": "library.backup.created",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": [{"path": str(path.relative_to(target / "library")),
                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "size_bytes": path.stat().st_size}
                  for path in _files(target / "library")],
    }
    (target / "backup_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return target, manifest


def restore_verified_backup(backup_dir, target_root, *, instance_id):
    _instance(instance_id)
    backup_dir, target_root = Path(backup_dir), Path(target_root)
    manifest_bytes = confined_path(backup_dir, 'backup_manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes, object_pairs_hook=_no_duplicate_keys)
    if not isinstance(manifest, dict) or manifest.get("instance_id") != instance_id:
        raise ValueError("backup belongs to a different Phoenix instance")
    if (type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1
            or manifest.get('record_type') != 'phoenix_library_backup'
            or not isinstance(manifest.get('files'), list)):
        raise ValueError("backup integrity: unsupported manifest")
    confined_path(target_root.parent, target_root.name)
    if target_root.exists() and (not target_root.is_dir() or any(target_root.iterdir())):
        raise ValueError("restore target must be empty")
    source = backup_dir / "library"
    if (target_root.resolve().is_relative_to(backup_dir.resolve())
            or backup_dir.resolve().is_relative_to(target_root.resolve())):
        raise ValueError("restore target must not overlap the backup")
    if not source.is_dir():
        raise ValueError("backup integrity: missing Library directory")
    actual = {str(p.relative_to(source)): p for p in _files(source)}
    expected = {}
    for item in manifest['files']:
        if (not isinstance(item, dict) or not isinstance(item.get('path'), str)
                or item['path'] in expected
                or not isinstance(item.get('sha256'), str)
                or not re.fullmatch('[0-9a-f]{64}', item['sha256'])
                or type(item.get('size_bytes')) is not int or item['size_bytes'] < 0):
            raise ValueError("backup integrity: malformed file entry")
        confined_path(source, item['path'])
        expected[item['path']] = item
    if set(actual) != set(expected):
        raise ValueError("backup integrity: exact file inventory mismatch")
    for name, path in actual.items():
        item = expected[name]
        if path.stat().st_size != item['size_bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError("backup integrity verification failed")
    target_root.parent.mkdir(parents=True, exist_ok=True)
    # Verify the staged bytes too; a changed backup cannot publish an unchecked
    # copy or a partially restored live Library. Preserve failed staging evidence.
    staged = target_root.with_name(f'.{target_root.name}.restore-{uuid.uuid4().hex}')
    shutil.copytree(source, staged, dirs_exist_ok=False, symlinks=True)
    staged_files = {str(p.relative_to(staged)): p for p in _files(staged)}
    if set(staged_files) != set(expected) or any(
        p.stat().st_size != expected[name]['size_bytes']
        or hashlib.sha256(p.read_bytes()).hexdigest() != expected[name]['sha256']
        for name, p in staged_files.items()
    ):
        raise ValueError("backup integrity: staged copy changed; live target untouched")
    receipt = {
        "schema_version": 1, "record_type": "phoenix_library_restore_receipt",
        "event_type": "library.backup.restored", "instance_id": instance_id,
        "backup_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "restored_at": datetime.now(timezone.utc).isoformat(),
    }
    # The receipt is metadata, not an excuse to overwrite source material from
    # an earlier restore. Retain earlier receipts as ordinary manifest files.
    receipt_path = staged / 'restore_receipt.json'
    if receipt_path.exists():
        receipt_path = staged / f'restore_receipt-{uuid.uuid4().hex}.json'
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    staged.rename(target_root)
    return receipt
