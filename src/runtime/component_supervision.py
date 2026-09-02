"""Sanitized component lifecycle receipts for local Fawkes supervision."""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import uuid
import fcntl
from contextlib import contextmanager


DEFAULT_STATE_ROOT = Path.home() / ".local" / "state" / "fawkes"
_FORBIDDEN = re.compile(
    r"(?i)(authorization|token|api[_ -]?key|webhook|secret|message[_ -]?content)\s*[:=]\s*\S+"
)


def sanitize_failure_message(value, *, secrets=()):
    text = "".join(character for character in str(value)[:500] if character.isprintable())
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    text = re.sub(r"(?:https?|wss?)://\S+", "<redacted-endpoint>", text,
                  flags=re.IGNORECASE)
    text = _FORBIDDEN.sub(lambda match: match.group(1) + "=<redacted>", text)
    return text or "no safe message supplied"


class ComponentReceiptStore:
    """Append-only body-free failure/recovery receipts plus pending alerts."""

    def __init__(self, root=None):
        self.root = Path(root) if root is not None else Path(
            os.getenv("FAWKES_RUNTIME_STATE_ROOT", DEFAULT_STATE_ROOT)
        )
        self.receipt_root = self.root / "component-receipts"
        self.pending_root = self.root / "pending-failure-notifications"

    def _write(self, record):
        self.receipt_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.receipt_root / f"{record['timestamp_utc'].replace(':', '')}-{record['failure_id']}.json"
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.chmod(temporary, 0o600)
            temporary.replace(path)
        except BaseException:
            # An unavailable/read-only state boundary must fail visibly without
            # leaving a misleading partial receipt behind.
            temporary.unlink(missing_ok=True)
            raise
        print("FAWKES_COMPONENT_" + record["receipt_type"].upper())
        for key in ("failure_id", "timestamp_utc", "component", "stage", "category",
                    "process_exit_code", "provider_code", "exception_type", "safe_message",
                    "restart_attempt", "recovered", "service_state"):
            print(f"{key}={record.get(key)}")
        return path

    def failure(self, *, component, stage, category, exception=None,
                process_exit_code=None, provider_code=None, restart_attempt=1,
                service_state="failed", notify=False, secrets=()):
        failure_id = "fawkes-failure-" + uuid.uuid4().hex
        record = {
            "schema_version": 1, "receipt_type": "failure", "failure_id": failure_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "component": component, "stage": stage, "category": category,
            "process_exit_code": process_exit_code, "provider_code": provider_code,
            "exception_type": type(exception).__name__ if exception else None,
            "safe_message": sanitize_failure_message(exception or category, secrets=secrets),
            "restart_attempt": int(restart_attempt), "recovered": False,
            "service_state": service_state,
        }
        path = self._write(record)
        if notify:
            self.queue_notification(record)
        return record, path

    def recovery(self, failure_record, *, service_state="active"):
        record = {**failure_record, "receipt_type": "recovery",
                  "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                  "recovered": True, "service_state": service_state,
                  "safe_message": "component recovered"}
        path = self._write(record)
        self.queue_notification(record)
        return record, path

    def queue_notification(self, record):
        self.pending_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        fingerprint = hashlib.sha256(
            "\0".join(str(record.get(key)) for key in
                       ("receipt_type", "component", "stage", "category", "provider_code",
                        "service_state")).encode("utf-8")
        ).hexdigest()
        path = self.pending_root / f"{fingerprint}.json"
        lock = self.pending_root / f".{fingerprint}.lock"
        with lock.open("a+") as descriptor:
            fcntl.flock(descriptor.fileno(), fcntl.LOCK_EX)
            if path.exists():
                return path, False
            value = {"logical_notification_id": "component-" + fingerprint,
                     "receipt": record, "attempts": []}
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                os.chmod(temporary, 0o600)
                temporary.replace(path)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
            finally:
                fcntl.flock(descriptor.fileno(), fcntl.LOCK_UN)
        return path, True

    def latest(self, limit=20):
        paths = sorted(self.receipt_root.glob("*.json"), reverse=True)[:limit]
        return [json.loads(path.read_text(encoding="utf-8")) for path in paths]

    def recover_latest(self, component):
        records = self.latest(limit=200)
        recovered = {item["failure_id"] for item in records
                     if item.get("receipt_type") == "recovery"}
        for item in records:
            if (item.get("receipt_type") == "failure" and item.get("component") == component
                    and item["failure_id"] not in recovered):
                return self.recovery(item)
        return None

    def next_restart_attempt(self, component):
        count = 0
        for item in self.latest(limit=200):
            if item.get("component") != component:
                continue
            if item.get("receipt_type") == "recovery":
                break
            if item.get("receipt_type") == "failure":
                count += 1
        return count + 1
