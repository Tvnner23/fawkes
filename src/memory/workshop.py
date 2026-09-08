"""Inert, instance-scoped Workshop proposal and attributed Assurance evidence.

This owner records a bounded investigation; it never executes an evaluation,
teaches live Memory, transmits a report, approves a worker, or applies a change.
Worker Exchange remains the report owner. A recorded verifier verdict is an
attributed claim, not a new source of permission or canonical acceptance.
"""

from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from src.runtime.personal_recording import EffectiveRecordingPolicy, RecordingPolicyError, RecordingPolicyStore
from src.runtime.worker_exchange import WorkerExchange


SCHEMA_VERSION = 1
CLASSIFICATIONS = (
    "knowledge_gap", "retrieval_context_failure", "capability_gap",
    "workflow_inefficiency", "ui_defect", "code_system_defect",
    "security_privacy", "memory_issue", "development_observation",
    "base_phoenix_candidate",
)
VERDICTS = {"pass", "fail", "partial", "inconclusive"}
MAX_BYTES = 1_048_576
MAX_REVISIONS = 512


class WorkshopError(ValueError):
    """Invalid, unavailable, or corrupt Workshop evidence."""


class WorkshopConflict(WorkshopError):
    """Reload the proposal before explicitly retrying a stale mutation."""


class WorkshopStateError(WorkshopError):
    """Stored state is unavailable or unsafe; do not retry a write blindly."""


class WorkshopDurabilityError(WorkshopStateError):
    """Publication is visible, but its durable commit is unconfirmed."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _copy(value):
    try:
        encoded = _canonical(value)
        if len(encoded.encode()) > MAX_BYTES:
            raise WorkshopError("Workshop input exceeds size limit")
        return json.loads(encoded)
    except (TypeError, ValueError, RecursionError) as exc:
        raise WorkshopError("bounded finite JSON is required") from exc


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
        raise WorkshopError("safe identity is required")
    return value


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise WorkshopError("exact sha256 is required")
    return value


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 32_768:
        raise WorkshopError("bounded nonempty text is required")
    return value


def _texts(value, *, nonempty=False):
    if not isinstance(value, list) or len(value) > 128 or (nonempty and not value):
        raise WorkshopError("bounded text list is required")
    for item in value:
        _text(item)
    return value


def _fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise WorkshopError("fields do not match the Workshop schema")


def _actor(value):
    _fields(value, ("worker_id", "role", "identity_status", "charter_version"), ("descriptive_only_no_authority",))
    for name in ("worker_id", "role", "charter_version"):
        _id(value[name])
    if value["identity_status"] not in ("verified", "rider_attested", "unverified"):
        raise WorkshopError("invalid attributed worker identity")
    return {**value, "descriptive_only_no_authority": True}


def _instant(value):
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.utcoffset() is None:
            raise ValueError("timezone required")
        return instant
    except (AttributeError, TypeError, ValueError) as exc:
        raise WorkshopError("timezone-qualified timestamp is required") from exc


def _now():
    return datetime.now(timezone.utc).isoformat()


def _regular(fd):
    observed = os.fstat(fd)
    if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
        raise WorkshopStateError("evidence must be a single-link regular file")


def _directory(path, *, create=False):
    """Open an exact absolute directory without following any symlink."""
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    os.close(fd)
                    return None
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
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


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WorkshopError("duplicate evidence field")
        result[key] = value
    return result


def _decode(data):
    try:
        return json.loads(data, object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(WorkshopError("nonfinite evidence")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise WorkshopError("evidence JSON is malformed") from exc


def _read(directory, filename, *, with_sha=False):
    fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, "rb") as stream:
        _regular(stream.fileno())
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise WorkshopError("evidence exceeds size limit")
    value = _decode(data)
    return (value, hashlib.sha256(data).hexdigest()) if with_sha else value


def _rename_once(directory, temporary, filename):
    # Unlike link+unlink, this has no crash interval with a two-link canonical
    # file. Unlike replace/rename, it can never overwrite a committed revision.
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        rename = libc.renameat2
    except AttributeError as exc:
        raise WorkshopError("atomic no-replace publication is unavailable") from exc
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(directory, os.fsencode(temporary), directory, os.fsencode(filename), 1):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


class _PinnedReportExchange(WorkerExchange):
    """Existing report semantics with durable, no-replace publication."""

    def __init__(self, instance_id, directory, guard):
        super().__init__(instance_id, root=Path(f"/proc/self/fd/{directory}"))
        self._report_directory = directory
        self._guard = guard

    def _path(self, kind, record_id):
        if kind != "reports":
            raise WorkshopError("Workshop can only create inert Exchange reports")
        return Path(f"/proc/self/fd/{self._report_directory}") / (_id(record_id) + ".json")

    def _write_once(self, kind, record):
        filename = self._path(kind, record['report_id']).name
        directory = self._report_directory
        ignored = {'created_at', 'record_sha256', 'content_sha256'}
        def existing_report():
            existing = _read(directory, filename)
            if not isinstance(existing, dict) or existing.get('instance_id') != self.instance_id or existing.get('record_sha256') != _digest(
                    {k: v for k, v in existing.items() if k != 'record_sha256'}):
                raise WorkshopStateError('Existing Exchange report integrity or owner mismatch')
            if {k:v for k,v in existing.items() if k not in ignored} != {k:v for k,v in record.items() if k not in ignored}:
                raise WorkshopConflict('Exchange report identity already exists with different data')
            # A prior uncertain publication is not durable merely because it is readable.
            fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                _regular(fd)
                os.fsync(fd)
            finally:
                os.close(fd)
            return existing
        self._guard()
        try:
            result = existing_report()
        except FileNotFoundError:
            data = (_canonical(record) + '\n').encode('utf-8')
            if len(data) > MAX_BYTES:
                raise WorkshopError('Exchange report exceeds the bounded evidence limit')
            temporary = '.' + filename + '.' + uuid.uuid4().hex + '.tmp'
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data); stream.flush(); os.fsync(stream.fileno())
                self._guard()
                try:
                    _rename_once(directory, temporary, filename)
                    result = record
                except FileExistsError:
                    result = existing_report()
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
        try:
            self._guard()
            os.fsync(directory)
        except OSError as exc:
            raise WorkshopDurabilityError('Exchange report may be visible; durability is unconfirmed. No Workshop reference committed.') from exc
        return result


class WorkshopStore:
    """Append-only snapshots in runtime memory/development/workshop, not a DB.

    root is the explicit runtime-state root, never an implicit source checkout.
    Historical reads do not retain new personal content and remain available
    while recording is disabled. All writes require current diagnostics consent
    and, when supplied, the immutable policy latched by the initiating action.
    """

    def __init__(self, instance_id, *, root, development_root=None, exchange_root=None):
        self.instance_id = _id(instance_id)
        self.root = Path(os.path.abspath(os.fspath(root)))
        self.path = self.root / "memory" / "development" / "workshop" / instance_id
        # These are existing server-owned source locations, not children of the
        # independent recording-policy root. Resolve trusted release symlinks
        # once; all subsequent reads/publication use no-follow directory walks.
        from src.memory import development_store
        from src.runtime import worker_exchange
        self.development_root = (development_store.DEVELOPMENT_DIR.resolve() if development_root is None
                                 else Path(os.path.abspath(os.fspath(development_root))))
        exchange_root = (worker_exchange.EXCHANGE_ROOT.resolve() if exchange_root is None
                         else Path(os.path.abspath(os.fspath(exchange_root))))
        self.exchange = WorkerExchange(instance_id, root=exchange_root)

    def _permit(self, recording_policy=None):
        try:
            current = RecordingPolicyStore(self.instance_id, root=self.root).latch()
        except RecordingPolicyError as exc:
            raise WorkshopStateError("personal recording policy is unavailable") from exc
        for policy in (current, recording_policy if recording_policy is not None else current):
            if not isinstance(policy, EffectiveRecordingPolicy) or policy.instance_id != self.instance_id:
                raise PermissionError("matching effective recording policy is required")
            if policy.mode != "retained" or not policy.personal_diagnostics:
                raise PermissionError("Workshop retention is disabled by personal recording policy")
        return current

    @contextmanager
    def _locked(self, *, create=False):
        directory = lock = None
        try:
            directory = _directory(self.path, create=create)
            if directory is None:
                yield None, None
                return
            # Recovery selects scoped JSON, not ephemeral lock files. Recreate
            # this body-free operational lock only in an existing directory.
            flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CREAT
            lock = os.open(".workshop.lock", flags, 0o600, dir_fd=directory)
            _regular(lock)
            fcntl.flock(lock, fcntl.LOCK_EX if create else fcntl.LOCK_SH)
            self._binding(directory, lock)
            yield directory, lock
            self._binding(directory, lock)
        except PermissionError:
            raise
        except OSError as exc:
            raise WorkshopStateError("Workshop state cannot be accessed safely") from exc
        finally:
            if lock is not None:
                os.close(lock)
            if directory is not None:
                os.close(directory)

    def _binding(self, directory, lock):
        _regular(lock)
        named = _directory(self.path)
        if named is None:
            raise WorkshopStateError("Workshop directory moved while waiting")
        try:
            for held, observed in ((os.fstat(directory), os.fstat(named)),
                                   (os.fstat(lock), os.stat(".workshop.lock", dir_fd=named, follow_symlinks=False))):
                if (held.st_dev, held.st_ino) != (observed.st_dev, observed.st_ino):
                    raise WorkshopStateError("Workshop ownership changed while waiting")
        finally:
            os.close(named)

    def _history(self, directory, proposal_id):
        _id(proposal_id)
        if directory is None:
            raise KeyError(proposal_id)
        prefix = proposal_id + "."
        names = sorted(name for name in os.listdir(directory) if name.startswith(prefix) and name.endswith(".json"))
        if not names:
            raise KeyError(proposal_id)
        if len(names) > MAX_REVISIONS:
            raise WorkshopError("Workshop history exceeds revision limit")
        records, previous = [], None
        for revision, name in enumerate(names, 1):
            if name != f"{proposal_id}.{revision:06d}.json":
                raise WorkshopStateError("Workshop revision history is not contiguous")
            record = _read(directory, name)
            if (not isinstance(record, dict) or record.get("instance_id") != self.instance_id
                    or record.get("proposal_id") != proposal_id or record.get("revision") != revision
                    or record.get("schema_version") != SCHEMA_VERSION
                    or record.get("previous_sha256") != previous
                    or record.get("record_sha256") != _digest({k: v for k, v in record.items() if k != "record_sha256"})):
                raise WorkshopStateError("Workshop history integrity or ownership mismatch")
            previous = record["record_sha256"]
            records.append(record)
        return records

    def _publish(self, directory, record, *, lock, recording_policy):
        self._binding(directory, lock)
        self._permit(recording_policy)
        record["record_sha256"] = _digest({k: v for k, v in record.items() if k != "record_sha256"})
        data = (_canonical(record) + "\n").encode()
        if len(data) > MAX_BYTES or record["revision"] > MAX_REVISIONS:
            raise WorkshopError("Workshop proposal reached its bounded history limit")
        filename = f"{record['proposal_id']}.{record['revision']:06d}.json"
        temporary = "." + uuid.uuid4().hex + ".tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            self._binding(directory, lock)
            self._permit(recording_policy)
            _rename_once(directory, temporary, filename)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
        try:
            os.fsync(directory)
        except OSError as exc:
            raise WorkshopDurabilityError("revision is visible but durability is unconfirmed; reload before retry") from exc
        return record

    def _resolve(self, reference):
        _fields(reference, ("kind", "instance_id", "report_id", "record_sha256"))
        if reference["kind"] != "worker_exchange_report" or reference["instance_id"] != self.instance_id:
            raise WorkshopError("evidence must reference this Phoenix's Worker Exchange report")
        report_id = _id(reference["report_id"])
        _sha(reference["record_sha256"])
        directory = _directory(self.exchange.root / "reports")
        if directory is None:
            raise WorkshopError("referenced Worker Exchange report is missing")
        try:
            report = _read(directory, report_id + ".json")
        except (OSError, KeyError) as exc:
            raise WorkshopError("referenced Worker Exchange report is unavailable") from exc
        finally:
            os.close(directory)
        if (not isinstance(report, dict) or report.get("instance_id") != self.instance_id
                or report.get("report_id") != report_id or report.get("record_type") != "worker_source_report"
                or report.get("record_sha256") != reference["record_sha256"]
                or report.get("record_sha256") != _digest({k: v for k, v in report.items() if k != "record_sha256"})):
            raise WorkshopError("Worker Exchange report integrity or ownership mismatch")
        return report

    def _references(self, values, *, nonempty=False):
        if not isinstance(values, list) or len(values) > 128 or (nonempty and not values):
            raise WorkshopError("bounded evidence references are required")
        for reference in values:
            self._resolve(reference)
        return values

    @staticmethod
    def report_reference(report):
        return {"kind": "worker_exchange_report", "instance_id": report["instance_id"],
                "report_id": report["report_id"], "record_sha256": report["record_sha256"]}

    def _section(self, reference, section_id):
        report = self._resolve(reference)
        sections = [section for section in report.get("sections", []) if section.get("section_id") == section_id]
        if len(sections) != 1:
            raise WorkshopError("exact structured Workshop evidence section is missing")
        section = sections[0]
        content = section.get("content")
        if (not isinstance(content, str) or section.get("content_sha256") != hashlib.sha256(content.encode()).hexdigest()
                or section.get("byte_length") != len(content.encode())):
            raise WorkshopError("Worker Exchange section integrity mismatch")
        try:
            payload = _copy(_decode(content))
        except (ValueError, RecursionError) as exc:
            raise WorkshopError("Workshop evidence section is not structured JSON") from exc
        return report, payload

    def _projection(self, record):
        projected = _copy(record)
        missing = []
        def visit(value):
            if isinstance(value, dict):
                if value.get("kind") == "worker_exchange_report":
                    try:
                        self._resolve(value)
                    except (WorkshopError, OSError):
                        missing.append(value.get("report_id"))
                else:
                    for item in value.values():
                        visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        visit(record)
        contract = record["acceptance_contracts"][-1] if record["acceptance_contracts"] else None
        latest = record["evaluations"][-1] if record["evaluations"] else None
        verdicts = []
        if contract and latest and latest["contract_sha256"] == contract["contract_sha256"]:
            relevant_evaluations = [item for item in record["evaluations"] if item["candidate"] == latest["candidate"]
                                    and item["contract_sha256"] == contract["contract_sha256"]]
            relevant_assurance = [item for item in record["assurance"] if item["candidate"] == latest["candidate"]
                                 and item["contract_sha256"] == contract["contract_sha256"]
                                 and item["evaluation_report"] == latest["report_reference"]]
            verdicts = [item["verdict"] for item in relevant_evaluations + relevant_assurance]
            # Redeclaring a contract (or renaming the same candidate bytes)
            # cannot erase already observed adverse results. Fixes require a
            # different exact candidate and new scoped evidence.
            verdicts.extend(item["verdict"] for item in record["evaluations"] + record["assurance"]
                            if item["candidate"]["sha256"] == latest["candidate"]["sha256"]
                            and item["verdict"] != "pass")
            if contract["assurance_tier"] >= 2 and not relevant_assurance:
                verdicts.append("inconclusive")
            if any(item["disagreements"] for item in relevant_assurance):
                verdicts.append("inconclusive")
        verdict = "inconclusive"
        if not missing and verdicts:
            verdict = "fail" if "fail" in verdicts else ("inconclusive" if "inconclusive" in verdicts else
                      "partial" if "partial" in verdicts else "pass")
        projected["evidence_status"] = {"missing_report_ids": sorted(set(missing)), "integrity_checked": not missing}
        projected["verdict"] = verdict
        projected["verdict_basis"] = "attributed_scoped_evidence_not_canonical_acceptance"
        return projected

    def get(self, proposal_id, *, revision=None):
        with self._locked() as (directory, _):
            records = self._history(directory, proposal_id)
            if revision is not None and (type(revision) is not int or revision < 1 or revision > len(records)):
                raise WorkshopError("requested revision does not exist")
            return self._projection(records[-1] if revision is None else records[revision - 1])

    def history(self, proposal_id):
        with self._locked() as (directory, _):
            return [self._projection(record) for record in self._history(directory, proposal_id)]

    def list(self):
        with self._locked() as (directory, _):
            if directory is None:
                return []
            ids = sorted({name.rsplit(".", 2)[0] for name in os.listdir(directory) if name.endswith(".json")})
            return [self._projection(self._history(directory, proposal_id)[-1]) for proposal_id in ids]

    def development_source(self, source_proposal_id):
        """Inspect one existing, exactly owned Development source without edits.

        Legacy unscoped records stay visible in their old owner; they cannot be
        silently adopted into this Phoenix's versioned Workshop history.
        """
        _id(source_proposal_id)
        directory = _directory(self.development_root)
        if directory is None:
            raise KeyError(source_proposal_id)
        try:
            source, digest = _read(directory, source_proposal_id + ".json", with_sha=True)
        except FileNotFoundError as exc:
            raise KeyError(source_proposal_id) from exc
        finally:
            os.close(directory)
        if (not isinstance(source, dict) or source.get("instance_id") != self.instance_id
                or source.get("proposal_id") != source_proposal_id):
            raise WorkshopError("Development intake requires an exactly owned source record")
        for key in ("observation", "proposed_change", "rationale", "origin"):
            _text(source.get(key))
        return {"source_proposal_id": source_proposal_id, "instance_id": self.instance_id,
                "expected_source_sha256": digest, "observation": source["observation"], "origin": source["origin"],
                "producer_identity": "not_recorded_by_legacy_owner", "source_record": source}

    def intake_development(self, source_proposal_id, *, expected_source_sha256, classification,
                           actor, recording_policy=None):
        """Rider-initiated intake of an existing Phoenix-generated proposal.

        The old owner records origin and Phoenix ownership but not the producer
        worker identity. Preserve that absence; never relabel the intake actor
        as the historical producer or invent a successful investigation.
        """
        self._permit(recording_policy)
        _sha(expected_source_sha256)
        source = self.development_source(source_proposal_id)
        if source["expected_source_sha256"] != expected_source_sha256:
            raise WorkshopConflict("Development source changed; inspect it again before intake")
        payload = {"classification": classification, "observation": source["source_record"]["observation"],
                   "interpretation": source["source_record"]["rationale"],
                   "uncertainty": "Imported source proposal only; producer identity, investigation, acceptance, and evaluation are not established.",
                   "evidence": []}
        return self._create(payload, actor=actor, recording_policy=recording_policy,
                            origin={"kind": "development_proposal_intake", **source})

    def create(self, payload, *, actor, recording_policy=None):
        return self._create(payload, actor=actor, recording_policy=recording_policy)

    def _create(self, payload, *, actor, recording_policy=None, origin=None):
        policy = self._permit(recording_policy)
        payload, actor = _copy(payload), _actor(_copy(actor))
        _fields(payload, ("classification", "observation", "interpretation", "uncertainty", "evidence"))
        if payload["classification"] not in CLASSIFICATIONS:
            raise WorkshopError("unknown failure classification")
        for key in ("observation", "interpretation", "uncertainty"):
            _text(payload[key])
        self._references(payload["evidence"])
        now = _now()
        record = {"schema_version": SCHEMA_VERSION, "proposal_id": "workshop-" + uuid.uuid4().hex,
                  "instance_id": self.instance_id, "revision": 1, "previous_sha256": None,
                  "created_at": now, "updated_at": now, "builder": actor, "actor": actor,
                  "event": "create", "status": "investigating", **payload,
                  "origin": origin or {"kind": "explicit_workshop_input", "producer_identity": "caller_attributed"},
                  "recording_policy": {"policy_revision": policy.policy_revision, "mode": policy.mode,
                                       "personal_diagnostics": True},
                  "investigations": [], "design": None, "acceptance_contracts": [], "evaluations": [],
                  "verifier_requests": [], "assurance": [], "reviews": [], "exports": [],
                  "applied_revision": None, "outcome": "not_applied", "creates_authority": False,
                  "execution_allowed": False}
        with self._locked(create=True) as (directory, lock):
            return self._projection(self._publish(directory, record, lock=lock, recording_policy=recording_policy))

    def _next(self, directory, proposal_id, expected_revision, actor, event, *, allow_reviewed=False):
        if type(expected_revision) is not int or expected_revision < 1:
            raise WorkshopError("expected_revision must be a positive integer")
        previous = self._history(directory, proposal_id)[-1]
        if previous["revision"] != expected_revision:
            raise WorkshopConflict("proposal revision changed; reload before retry")
        if previous["reviews"] and not allow_reviewed:
            raise WorkshopError("reviewed proposal is immutable; begin a new proposal")
        return {**previous, "revision": expected_revision + 1, "previous_sha256": previous["record_sha256"],
                "updated_at": _now(), "actor": _actor(_copy(actor)), "event": event}

    def _contract(self, record, payload):
        required = ("intended_behavior", "forbidden_behavior", "rider_expectation", "hard_invariants",
                    "failure_behavior", "regression_boundary", "rollback_requirement", "evidence_required",
                    "assurance_tier", "limitations", "criteria")
        _fields(payload, required)
        if record["design"] is None:
            raise WorkshopError("design must precede acceptance declaration")
        for key in required[:3] + required[4:7]:
            _text(payload[key])
        for key in ("hard_invariants", "evidence_required"):
            _texts(payload[key], nonempty=True)
        _texts(payload["limitations"])
        if type(payload["assurance_tier"]) is not int or payload["assurance_tier"] not in range(4):
            raise WorkshopError("predeclared assurance tier 0 through 3 is required")
        criteria = payload["criteria"]
        if not isinstance(criteria, list) or not criteria or len(criteria) > 128:
            raise WorkshopError("acceptance criteria are required")
        seen = set()
        for criterion in criteria:
            _fields(criterion, ("criterion_id", "expectation", "mandatory"))
            _id(criterion["criterion_id"])
            _text(criterion["expectation"])
            if type(criterion["mandatory"]) is not bool or criterion["criterion_id"] in seen:
                raise WorkshopError("unique criteria with exact mandatory booleans are required")
            seen.add(criterion["criterion_id"])
        if record["acceptance_contracts"]:
            previous = record["acceptance_contracts"][-1]
            if (payload["assurance_tier"] < previous["assurance_tier"]
                    or not set(previous["hard_invariants"]).issubset(payload["hard_invariants"])
                    or not set(previous["evidence_required"]).issubset(payload["evidence_required"])
                    or any(item not in criteria for item in previous["criteria"])):
                raise WorkshopError("contract revision cannot lower tier, drop invariants, or rewrite prior criteria")
        contract = {**payload, "contract_version": len(record["acceptance_contracts"]) + 1,
                    "declared_at": record["updated_at"], "declared_by": record["actor"],
                    "proposal_id": record["proposal_id"], "instance_id": self.instance_id}
        contract["contract_sha256"] = _digest(contract)
        record["acceptance_contracts"].append(contract)

    def _bound(self, record, payload):
        if not record["acceptance_contracts"]:
            raise WorkshopError("acceptance must be predeclared")
        contract = record["acceptance_contracts"][-1]
        if (payload["proposal_id"] != record["proposal_id"] or type(payload["contract_version"]) is not int
                or payload["contract_version"] != contract["contract_version"]
                or payload["contract_sha256"] != contract["contract_sha256"]):
            raise WorkshopError("evidence must bind the exact current proposal and acceptance contract")
        candidate = payload["candidate"]
        _fields(candidate, ("candidate_id", "revision", "sha256", "instance_id", "reality_scope"))
        _id(candidate["candidate_id"])
        _text(candidate["revision"])
        _sha(candidate["sha256"])
        if candidate["instance_id"] != self.instance_id or candidate["reality_scope"] != "isolated":
            raise WorkshopError("candidate must be exactly Phoenix-scoped and isolated")
        for old in record["evaluations"]:
            if old["candidate"]["candidate_id"] == candidate["candidate_id"] and old["candidate"] != candidate:
                raise WorkshopError("changed candidate requires a new candidate identity")
        return contract

    def _evaluation(self, record, reference):
        report, payload = self._section(reference, "workshop-evaluation-v1")
        _fields(payload, ("proposal_id", "contract_version", "contract_sha256", "candidate", "started_at",
                          "isolated", "ordinary_history_mutated", "results", "tests", "sandbox_results", "cost", "limitations"))
        contract = self._bound(record, payload)
        if (payload["isolated"] is not True or payload["ordinary_history_mutated"] is not False
                or _instant(payload["started_at"]) < _instant(contract["declared_at"])
                or _instant(payload["started_at"]) > _instant(report["created_at"])):
            raise WorkshopError("evaluation must follow declaration and report isolated, non-mutating execution")
        for key in ("tests", "sandbox_results"):
            _texts(payload[key], nonempty=True)
        _texts(payload["limitations"])
        if not isinstance(payload["cost"], dict):
            raise WorkshopError("explicit attributed cost object is required, including unknowns")
        if not isinstance(payload["results"], list) or len(payload["results"]) > 128:
            raise WorkshopError("bounded criterion results are required")
        criteria = {item["criterion_id"]: item for item in contract["criteria"]}
        outcomes = {}
        for result in payload["results"]:
            _fields(result, ("criterion_id", "verdict", "observed", "evidence"))
            identity = result["criterion_id"]
            if (not isinstance(identity, str) or identity not in criteria or identity in outcomes
                    or not isinstance(result["verdict"], str) or result["verdict"] not in VERDICTS):
                raise WorkshopError("result must uniquely identify a predeclared criterion and scoped verdict")
            _text(result["observed"])
            self._references(result["evidence"], nonempty=result["verdict"] == "pass")
            outcomes[identity] = result["verdict"]
        verdicts = list(outcomes.values()) + ["inconclusive" for identity in criteria if identity not in outcomes]
        verdict = "fail" if "fail" in verdicts else ("inconclusive" if "inconclusive" in verdicts else
                  "partial" if "partial" in verdicts else "pass")
        if verdict == "pass" and _actor(report["sender"])["identity_status"] == "unverified":
            verdict = "inconclusive"
        if any(item["report_reference"] == reference for item in record["evaluations"]):
            raise WorkshopError("evaluation report already recorded")
        record["evaluations"].append({**payload, "verdict": verdict, "report_reference": reference,
            "producer": report["sender"], "task_scope_id": report["task_scope_id"],
            "authority_reference": report["authority_reference"], "claims": report["claims"],
            "evidence_basis": "source_report_assertions_not_reexecuted_by_workshop"})

    def _assurance(self, record, reference):
        report, payload = self._section(reference, "workshop-assurance-v1")
        _fields(payload, ("proposal_id", "contract_version", "contract_sha256", "candidate", "evaluation_report",
                          "verifier_request", "verdict", "observed", "coverage", "limitations", "disagreements",
                          "authority_check", "rider_impact", "recommendation", "independence", "cost"))
        contract = self._bound(record, payload)
        evaluations = [item for item in record["evaluations"] if item["report_reference"] == payload["evaluation_report"]
                       and item["candidate"] == payload["candidate"] and item["contract_sha256"] == payload["contract_sha256"]]
        requests = [item for item in record["verifier_requests"] if item["report_reference"] == payload["verifier_request"]
                    and item["candidate"] == payload["candidate"] and item["contract_sha256"] == payload["contract_sha256"]
                    and item["evaluation_report"] == payload["evaluation_report"]]
        if len(evaluations) != 1 or len(requests) != 1:
            raise WorkshopError("Assurance requires exact recorded evaluation and verifier request")
        self._resolve(payload["evaluation_report"])
        self._resolve(payload["verifier_request"])
        verifier = _actor(report["sender"])
        independence = payload["independence"]
        _fields(independence, ("builder_worker_id", "verifier_worker_id", "context_separation", "common_mode_dependencies"))
        _text(independence["context_separation"])
        _texts(independence["common_mode_dependencies"])
        if (independence["builder_worker_id"] != record["builder"]["worker_id"]
                or independence["verifier_worker_id"] != verifier["worker_id"]
                or verifier["worker_id"] in {record["builder"]["worker_id"], evaluations[0]["producer"]["worker_id"]}
                or requests[0]["verifier"] != verifier or report["task_scope_id"] != requests[0]["task_scope_id"]):
            raise WorkshopError("verifier must be separate and match the exact requested scope and identity")
        if not isinstance(payload["verdict"], str) or payload["verdict"] not in VERDICTS:
            raise WorkshopError("invalid Assurance verdict")
        for key in ("observed", "authority_check", "rider_impact", "recommendation"):
            _text(payload[key])
        for key in ("coverage", "limitations", "disagreements"):
            _texts(payload[key])
        if not isinstance(payload["cost"], dict):
            raise WorkshopError("attributed verifier cost is required")
        if payload["verdict"] == "pass" and (verifier["identity_status"] == "unverified"
                or evaluations[0]["verdict"] != "pass" or payload["disagreements"]
                or set(payload["coverage"]) != {item["criterion_id"] for item in contract["criteria"]}):
            raise WorkshopError("missing coverage, uncertain identity, disagreement, or failing evidence cannot pass")
        if any(item["report_reference"] == reference for item in record["assurance"]):
            raise WorkshopError("Assurance report already recorded")
        record["assurance"].append({**payload, "report_reference": reference, "verifier": verifier,
            "task_scope_id": report["task_scope_id"], "authority_reference": report["authority_reference"],
            "claims": report["claims"], "independence_basis": "attributed_identity_and_scope_not_model_diversity"})

    def append(self, proposal_id, *, expected_revision, action, payload, actor, recording_policy=None):
        self._permit(recording_policy)
        if not isinstance(action, str):
            raise WorkshopError("Workshop action must be a string")
        payload = _copy(payload)
        with self._locked(create=True) as (directory, lock):
            record = self._next(directory, proposal_id, expected_revision, actor, action)
            if record["status"] == "submitted":
                raise WorkshopError("submitted proposal only permits rider review")
            if action == "investigate":
                _fields(payload, ("investigation", "knowledge", "hypothesis", "evidence", "cost"))
                for key in ("investigation", "knowledge", "hypothesis"):
                    _text(payload[key])
                self._references(payload["evidence"])
                if not isinstance(payload["cost"], dict):
                    raise WorkshopError("attributed investigation cost is required")
                record["investigations"].append({**payload, "actor": record["actor"], "recorded_at": record["updated_at"]})
            elif action == "design":
                _fields(payload, ("proposed_change", "affected_systems", "permissions", "risks", "rollback"))
                if not record["investigations"] or record["acceptance_contracts"]:
                    raise WorkshopError("design requires investigation and must precede acceptance")
                for key in ("proposed_change", "rollback"):
                    _text(payload[key])
                for key in ("affected_systems", "permissions", "risks"):
                    _texts(payload[key], nonempty=key == "affected_systems")
                record["design"] = {**payload, "actor": record["actor"]}
            elif action == "declare_acceptance":
                self._contract(record, payload)
            elif action in {"record_evaluation", "record_assurance"}:
                _fields(payload, ("report_reference",))
                (self._evaluation if action == "record_evaluation" else self._assurance)(record, payload["report_reference"])
            elif action == "submit":
                _fields(payload, ())
                if not record["evaluations"] or not record["acceptance_contracts"]:
                    raise WorkshopError("an isolated evaluation must precede Human Review submission")
                if record["evaluations"][-1]["contract_sha256"] != record["acceptance_contracts"][-1]["contract_sha256"]:
                    raise WorkshopError("current contract still needs isolated evaluation")
                record["status"] = "submitted"
            else:
                raise WorkshopError("unknown Workshop action")
            return self._projection(self._publish(directory, record, lock=lock, recording_policy=recording_policy))

    def review(self, proposal_id, *, expected_revision, decision, note, rider_principal_id,
               authenticated_rider, recording_policy=None):
        self._permit(recording_policy)
        if authenticated_rider is not True:
            raise PermissionError("authenticated rider boundary is required")
        _id(rider_principal_id)
        if decision not in ("approve", "reject"):
            raise WorkshopError("review decision must be approve or reject")
        if not isinstance(note, str) or len(note) > 32_768:
            raise WorkshopError("bounded review note is required")
        actor = {"worker_id": rider_principal_id, "role": "rider", "identity_status": "verified", "charter_version": "human-review-v1"}
        with self._locked(create=True) as (directory, lock):
            record = self._next(directory, proposal_id, expected_revision, actor, "review")
            if record["status"] != "submitted":
                raise WorkshopError("proposal must be submitted before rider review")
            record["reviews"].append({"decision": decision, "note": note, "rider_principal_id": rider_principal_id,
                "reviewed_at": record["updated_at"], "proposal_revision": expected_revision,
                "proposal_sha256": record["previous_sha256"], "verdict_at_review": self._projection(record)["verdict"],
                "effect": "recorded_only_no_automatic_application", "creates_authority": False})
            record["status"] = "approved_for_future_action" if decision == "approve" else "rejected"
            return self._projection(self._publish(directory, record, lock=lock, recording_policy=recording_policy))

    def export_report(self, proposal_id, *, expected_revision, task_scope_id, sender, authority,
                      purpose="proposal", verifier=None, recording_policy=None):
        """Record an Exchange report, never deliver it or activate its recipient.

        Caller supplies existing upstream Exchange authority. No authority is
        derived from a Workshop proposal or from the rider's inert review.
        """
        self._permit(recording_policy)
        sender = _actor(_copy(sender))
        _id(task_scope_id)
        if purpose not in ("proposal", "verifier_request"):
            raise WorkshopError("unsupported Workshop report purpose")
        verifier = _actor(_copy(verifier)) if purpose == "verifier_request" else None
        with self._locked(create=True) as (directory, lock):
            record = self._next(directory, proposal_id, expected_revision, sender, "export_" + purpose,
                                allow_reviewed=purpose == "proposal")
            if purpose == "verifier_request":
                if not record["evaluations"]:
                    raise WorkshopError("verifier request requires an exact evaluated candidate")
                evaluation = record["evaluations"][-1]
                if (evaluation["contract_sha256"] != record["acceptance_contracts"][-1]["contract_sha256"]
                        or verifier["worker_id"] in {record["builder"]["worker_id"], evaluation["producer"]["worker_id"]}):
                    raise WorkshopError("request requires current evidence and a separate verifier")
                details = {"candidate": evaluation["candidate"], "contract_sha256": evaluation["contract_sha256"],
                    "contract_version": evaluation["contract_version"], "evaluation_report": evaluation["report_reference"],
                    "verifier": verifier, "task_scope_id": task_scope_id}
            else:
                details = {}
            prior = self._history(directory, proposal_id)[-1]
            content = {"purpose": purpose, "proposal_id": proposal_id, "proposal_revision": expected_revision,
                "proposal_sha256": prior["record_sha256"], "instance_id": self.instance_id, **details,
                "proposal": self._projection(prior), "execution_allowed": False, "creates_authority": False}
            self._permit(recording_policy)
            # Bind the Exchange writer to an opened directory. The existing
            # report owner uses only its reports child for create_report.
            reports = None
            try:
                reports = _directory(self.exchange.root / "reports", create=True)
                # Existing Exchange handles format/authority/content identity;
                # /proc dirfd pins its path instead of following a swapped root.
                def guard():
                    self._binding(directory, lock)
                    self._permit(recording_policy)
                    named = _directory(self.exchange.root / 'reports')
                    try:
                        if named is None or (os.fstat(named).st_dev, os.fstat(named).st_ino) != (os.fstat(reports).st_dev, os.fstat(reports).st_ino):
                            raise WorkshopStateError('Exchange reports directory binding changed')
                    finally:
                        if named is not None:
                            os.close(named)
                exchange = _PinnedReportExchange(self.instance_id, reports, guard)
                report = exchange.create_report(task_scope_id=task_scope_id, sender=sender, authority=authority,
                    sections=[{"section_id": "workshop-" + purpose.replace("_", "-") + "-v1",
                               "title": "Inert Workshop " + purpose, "content": _canonical(content)}],
                    contract_references=[{"proposal_id": proposal_id, "revision": expected_revision,
                                          "record_sha256": prior["record_sha256"]}])
            finally:
                if reports is not None:
                    os.close(reports)
            reference = self.report_reference(report)
            self._resolve(reference)
            entry = {"purpose": purpose, "report_reference": reference, "proposal_revision": expected_revision,
                     "proposal_sha256": prior["record_sha256"], "sender": sender, **details}
            record["exports"].append(entry)
            if purpose == "verifier_request":
                record["verifier_requests"].append(entry)
            updated = self._projection(self._publish(directory, record, lock=lock, recording_policy=recording_policy))
            return {"proposal": updated, "report_reference": reference}
