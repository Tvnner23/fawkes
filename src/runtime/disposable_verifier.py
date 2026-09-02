"""Exact, disposable candidate snapshots for independent Phoenix Assurance."""

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import unicodedata


LEGACY_SNAPSHOT_POLICY_VERSION = "phoenix-disposable-verifier-v1"
SNAPSHOT_POLICY_VERSION = "phoenix-portable-snapshot-identity-v2"
EXCLUDED_NAMES = {
    ".git", ".venv", "database", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".coverage", "htmlcov",
}
EXCLUDED_ROOTS = {".agents", ".codex", "archive", "backups", "conversations", "database",
                  "instances", "library", "logs", "memory", "node_modules"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_SECRET_NAMES = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json"}
EXCLUDED_WINDOWS_METADATA_SUFFIXES = {":Zone.Identifier", "\uf03aZone.Identifier"}


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _included(relative):
    portable_name = unicodedata.normalize("NFC", str(relative.name))
    return (relative.parts[0] not in EXCLUDED_ROOTS
            and not any(part in EXCLUDED_NAMES for part in relative.parts)
            and relative.name not in EXCLUDED_SECRET_NAMES
            and relative.suffix not in EXCLUDED_SUFFIXES
            and not any(portable_name.endswith(suffix)
                        for suffix in EXCLUDED_WINDOWS_METADATA_SUFFIXES))


def _portable_relative_path(relative):
    """Return the one cross-platform path representation used for identity."""
    value = unicodedata.normalize("NFC", str(relative).replace("\\", "/"))
    if (not value or value.startswith("/")
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ValueError("snapshot contains a non-portable relative path")
    return value


def snapshot_identity(files, *, policy_version=SNAPSHOT_POLICY_VERSION):
    """Hash portable normalized entries with explicit binary framing."""
    normalized = []
    exact_paths = set()
    casefolded = set()
    for entry in files:
        path = _portable_relative_path(entry["path"])
        if path in exact_paths or path.casefold() in casefolded:
            raise ValueError("snapshot contains a portable path identity collision")
        exact_paths.add(path)
        casefolded.add(path.casefold())
        normalized.append({"path": path, "sha256": entry["sha256"],
                           "byte_length": int(entry["byte_length"])})
    normalized.sort(key=lambda item: item["path"].encode("utf-8"))
    digest = hashlib.sha256()
    digest.update(policy_version.encode("utf-8") + b"\n")
    for entry in normalized:
        path = entry["path"].encode("utf-8")
        digest.update(len(path).to_bytes(8, "big"))
        digest.update(path)
        digest.update(bytes.fromhex(entry["sha256"]))
        digest.update(entry["byte_length"].to_bytes(8, "big"))
    return "candidate-snapshot-" + digest.hexdigest(), normalized


def candidate_manifest(source_root):
    """Describe every included byte in the dirty working candidate deterministically."""
    source_root = Path(source_root).resolve()
    files = []
    for path in source_root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(source_root)
        if not _included(relative):
            continue
        if "\\" in relative.as_posix():
            raise ValueError("snapshot contains a non-portable native filename")
        data = path.read_bytes()
        files.append({"path": _portable_relative_path(relative),
                      "sha256": _sha256(data), "byte_length": len(data)})
    identity, files = snapshot_identity(files)
    return {"policy_version": SNAPSHOT_POLICY_VERSION, "files": files,
            "candidate_snapshot_id": identity}


def materialize_candidate(source_root, destination):
    """Copy the exact included candidate into a new, non-authoritative writable fixture."""
    source_root = Path(source_root).resolve()
    destination = Path(destination).resolve()
    before = candidate_manifest(source_root)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("disposable verifier destination must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    for entry in before["files"]:
        source = source_root / entry["path"]
        target = destination / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # Establish a real, history-free disposable Git workspace. Codex's
    # supported workspace check requires more than an empty marker, while
    # authoritative Git history/configuration and credentials must not cross.
    initialized = subprocess.run(["git", "init", "--quiet", str(destination)],
                                 capture_output=True, text=True, check=False)
    if initialized.returncode != 0:
        raise RuntimeError("disposable verifier Git workspace initialization failed")
    after = candidate_manifest(destination)
    if before["candidate_snapshot_id"] != after["candidate_snapshot_id"] or before["files"] != after["files"]:
        raise RuntimeError("disposable verifier snapshot does not match the candidate")
    provenance = {
        "schema_version": 1,
        "record_type": "phoenix_disposable_verifier_snapshot",
        "policy_version": SNAPSHOT_POLICY_VERSION,
        "candidate_snapshot_id": before["candidate_snapshot_id"],
        "source_root_sha256": _sha256(str(source_root).encode()),
        "disposable_root_sha256": _sha256(str(destination).encode()),
        "file_count": len(before["files"]),
        "total_byte_length": sum(item["byte_length"] for item in before["files"]),
        "files": before["files"],
        "includes_uncommitted_worktree": True,
        "git_head_is_not_candidate_identity": True,
        "authoritative_project_state": False,
        "credentials_copied": False,
        "authoritative_git_history_copied": False,
        "disposable_git_workspace_initialized": True,
        "real_repository_writable": False,
    }
    provenance["record_sha256"] = _sha256(json.dumps(
        provenance, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode())
    return provenance


class DisposableVerifierWorkspace:
    """Lifetime-bound exact snapshot; cleanup can only target its mkdtemp root."""

    def __init__(self, source_root, *, parent=None):
        self.source_root = Path(source_root).resolve()
        self.parent = Path(parent).resolve() if parent else None
        self._temporary = None
        self.root = None
        self.provenance = None
        self.source_before = None

    def __enter__(self):
        self.source_before = candidate_manifest(self.source_root)
        self._temporary = tempfile.TemporaryDirectory(prefix="fawkes-verifier-", dir=self.parent)
        self.root = Path(self._temporary.name) / "candidate"
        self.provenance = materialize_candidate(self.source_root, self.root)
        return self

    def verify_source_unchanged(self):
        current = candidate_manifest(self.source_root)
        if current != self.source_before:
            raise RuntimeError("real Fawkes candidate changed during disposable verification")
        return True

    def __exit__(self, exc_type, exc, traceback):
        self.verify_source_unchanged()
        self._temporary.cleanup()
        return False
