"""Prospective personal-retention settings, not provider or execution authority.

Callers must latch one effective policy before any turn side effect and enforce
it at every personal-content writer. This store neither deletes old history nor
disables required metadata-only operational/authorization receipts.
"""

from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import stat
import uuid


SCHEMA_VERSION = 1
CATEGORIES = (
    "archive_recording", "memory_learning", "personal_diagnostics",
    "research_records", "library_retention", "social_archive",
    "sensor_retention",
)
EDITABLE_CATEGORIES = CATEGORIES[:-1]
MODES = ("retained", "private")
ROOT = Path(__file__).resolve().parents[2]
_MAX_BYTES = 16_384
_FILENAME = "personal_recording.json"
_LOCKNAME = ".personal_recording.lock"


class RecordingPolicyError(ValueError):
    """Policy is unavailable or invalid; callers must not assume recording on."""


class RecordingPolicyConflict(RecordingPolicyError):
    """The expected revision is stale; reload before an explicit retry."""


class RecordingPolicyDurabilityError(RecordingPolicyError):
    """Replacement occurred but directory durability was not confirmed."""


def _instance(value):
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    if (not isinstance(value, str) or not value or len(value) > 128
            or value in {".", ".."} or any(ch not in allowed for ch in value)):
        raise RecordingPolicyError("valid instance_id is required")


def _revision(value):
    if type(value) is not int or value < 0:
        raise RecordingPolicyError("revision must be a nonnegative integer")


def _mode(value):
    if not isinstance(value, str) or value not in MODES:
        raise RecordingPolicyError("mode must be retained or private")


@dataclass(frozen=True)
class EffectiveRecordingPolicy:
    instance_id: str
    policy_revision: int
    configured_mode: str
    mode: str
    archive_recording: bool
    memory_learning: bool
    personal_diagnostics: bool
    research_records: bool
    library_retention: bool
    social_archive: bool
    sensor_retention: bool = False

    def __post_init__(self):
        _instance(self.instance_id)
        _revision(self.policy_revision)
        _mode(self.configured_mode)
        _mode(self.mode)
        if any(type(getattr(self, name)) is not bool for name in CATEGORIES):
            raise RecordingPolicyError("effective categories must be exact booleans")
        if self.sensor_retention:
            raise RecordingPolicyError("sensor retention is unavailable")
        if self.mode == "private" and any(getattr(self, name) for name in CATEGORIES):
            raise RecordingPolicyError("private interactions cannot retain personal content")
        if self.mode == "retained" and (self.configured_mode == "private" or not self.archive_recording):
            raise RecordingPolicyError("effective policy cannot override configured privacy")

    def public(self):
        return {
            "instance_id": self.instance_id, "policy_revision": self.policy_revision,
            "configured_mode": self.configured_mode, "mode": self.mode,
            "categories": {name: getattr(self, name) for name in CATEGORIES},
        }


@dataclass(frozen=True)
class RecordingPolicy:
    instance_id: str
    revision: int = 0
    mode: str = "retained"
    archive_recording: bool = True
    memory_learning: bool = True
    personal_diagnostics: bool = True
    research_records: bool = True
    library_retention: bool = True
    social_archive: bool = True
    sensor_retention: bool = False

    def __post_init__(self):
        _instance(self.instance_id)
        _revision(self.revision)
        _mode(self.mode)
        if any(type(getattr(self, name)) is not bool for name in CATEGORIES):
            raise RecordingPolicyError("category values must be exact booleans")
        if self.sensor_retention:
            raise RecordingPolicyError("sensor retention is unavailable")

    def public(self):
        return {
            "schema_version": SCHEMA_VERSION, "instance_id": self.instance_id,
            "revision": self.revision, "mode": self.mode,
            "categories": {name: getattr(self, name) for name in CATEGORIES},
        }

    def effective(self, *, mode=None):
        if mode is not None:
            _mode(mode)
        private = self.mode == "private" or not self.archive_recording or mode == "private"
        return EffectiveRecordingPolicy(
            instance_id=self.instance_id, policy_revision=self.revision,
            configured_mode=self.mode, mode="private" if private else "retained",
            **{name: False if private else getattr(self, name) for name in CATEGORIES},
        )


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecordingPolicyError("duplicate JSON policy key")
        result[key] = value
    return result


def _decode(data, instance_id):
    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise RecordingPolicyError("recording policy JSON is malformed") from exc
    keys = {"schema_version", "instance_id", "revision", "mode", "categories"}
    if not isinstance(payload, dict) or set(payload) != keys:
        raise RecordingPolicyError("recording policy fields do not match schema")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != SCHEMA_VERSION:
        raise RecordingPolicyError("unsupported recording policy schema")
    if payload["instance_id"] != instance_id:
        raise RecordingPolicyError("recording policy belongs to another instance")
    categories = payload["categories"]
    if not isinstance(categories, dict) or set(categories) != set(CATEGORIES):
        raise RecordingPolicyError("recording policy categories do not match schema")
    return RecordingPolicy(instance_id=instance_id, revision=payload["revision"],
                           mode=payload["mode"], **categories)


class RecordingPolicyStore:
    """POSIX store under a runtime-state root, with cross-process revision CAS.

    load() never creates directories/files. An absent file is revision zero;
    unreadable, malformed, linked, or nonregular state is an error, not defaults.
    root overrides FAWKES_RUNTIME_STATE_ROOT; it is NOT the preferences directory.
    """

    def __init__(self, instance_id, *, root=None):
        _instance(instance_id)
        self.instance_id = instance_id
        selected_root = root if root is not None else (os.getenv("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
        self.root = Path(os.path.abspath(os.fspath(selected_root)))
        self.path = self.root / "database" / "preferences" / instance_id / _FILENAME

    def _directory(self, *, create=False):
        # Walk with directory descriptors: no following an ancestor symlink or
        # checking a pathname and then reopening it through a changed ancestor.
        fd = os.open(self.path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in self.path.parent.parts[1:]:
                try:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except FileNotFoundError:
                    if not create:
                        os.close(fd)
                        return None
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        pass
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except BaseException:
            os.close(fd)
            raise

    @staticmethod
    def _regular(fd):
        observed = os.fstat(fd)
        if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
            raise RecordingPolicyError("recording policy files must be single-link regular files")

    def _load_at(self, directory):
        try:
            fd = os.open(_FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return RecordingPolicy(self.instance_id)
        with os.fdopen(fd, "rb") as stream:
            self._regular(stream.fileno())
            data = stream.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            raise RecordingPolicyError("recording policy exceeds size limit")
        return _decode(data, self.instance_id)

    def load(self):
        try:
            directory = self._directory()
            if directory is None:
                return RecordingPolicy(self.instance_id)
            try:
                return self._load_at(directory)
            finally:
                os.close(directory)
        except OSError as exc:
            raise RecordingPolicyError("recording policy cannot be read safely") from exc

    def latch(self, *, mode=None):
        return self.load().effective(mode=mode)

    def _verify_writer_binding(self, directory, lock):
        """A waiter must still own the lock at the currently named directory."""
        current = self._directory()
        if current is None:
            raise RecordingPolicyError("recording policy directory changed while waiting")
        try:
            held, named = os.fstat(directory), os.fstat(current)
            if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
                raise RecordingPolicyError("recording policy directory changed while waiting")
            self._regular(lock)
            held = os.fstat(lock)
            named = os.stat(_LOCKNAME, dir_fd=current, follow_symlinks=False)
            if (not stat.S_ISREG(named.st_mode)
                    or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)):
                raise RecordingPolicyError("recording policy lock ownership changed")
        finally:
            os.close(current)

    def update(self, changes, *, expected_revision):
        _revision(expected_revision)
        if not isinstance(changes, dict) or set(changes) - {"mode", "categories"}:
            raise RecordingPolicyError("unknown recording preference fields")
        if "mode" in changes:
            _mode(changes["mode"])
        categories = changes.get("categories", {})
        if (not isinstance(categories, dict) or set(categories) - set(EDITABLE_CATEGORIES)
                or any(type(value) is not bool for value in categories.values())):
            raise RecordingPolicyError("unknown, unavailable, or invalid recording category")
        # Copy caller-owned input before waiting for the shared lock.
        changes = {**changes, "categories": dict(categories)}
        directory = lock = None
        try:
            directory = self._directory(create=True)
            lock = os.open(_LOCKNAME, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                           0o600, dir_fd=directory)
            self._regular(lock)
            fcntl.flock(lock, fcntl.LOCK_EX)
            self._verify_writer_binding(directory, lock)
            current = self._load_at(directory)
            if current.revision != expected_revision:
                raise RecordingPolicyConflict("recording policy revision changed; reload before retry")
            updated = RecordingPolicy(
                instance_id=self.instance_id, revision=current.revision + 1,
                mode=changes.get("mode", current.mode),
                **{**current.public()["categories"], **changes["categories"]},
            )
            self._verify_writer_binding(directory, lock)
            self._publish(directory, updated)
            return updated
        except OSError as exc:
            raise RecordingPolicyError("recording policy update could not be completed safely") from exc
        finally:
            if lock is not None:
                os.close(lock)  # Closing releases the process-shared flock.
            if directory is not None:
                os.close(directory)

    @staticmethod
    def _publish(directory, policy):
        temporary = f".{_FILENAME}.{uuid.uuid4().hex}.tmp"
        encoded = (json.dumps(policy.public(), indent=2, sort_keys=True) + "\n").encode("utf-8")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        published = False
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, _FILENAME, src_dir_fd=directory, dst_dir_fd=directory)
            published = True
            try:
                os.fsync(directory)
            except OSError as exc:
                # Do not fabricate rollback after publication. Reload and report
                # uncertainty; never retry a possibly committed update blindly.
                raise RecordingPolicyDurabilityError(
                    "policy replacement is visible but durable commit is unconfirmed; reload"
                ) from exc
        finally:
            if not published:
                os.unlink(temporary, dir_fd=directory)
