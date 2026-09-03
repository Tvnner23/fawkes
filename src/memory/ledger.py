"""Durable, resumable processing state for canonical memory candidates."""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
import uuid


ROOT = Path(__file__).resolve().parent.parent.parent
LEDGER_PATH = Path(os.environ.get(
    "FAWKES_MEMORY_LEDGER_PATH",
    str(Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
        / "database" / "memory_processing.sqlite3"),
))

STATUSES = {
    "discovered",
    "queued",
    "evaluating",
    "evaluated",
    "accepted",
    "rejected",
    "review",
    "consolidating",
    "consolidated",
    "failed_retryable",
    "failed_evaluation_retryable",
    "failed_consolidation_retryable",
    "failed_terminal",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _connect(path=LEDGER_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_work_items (
            work_item_id TEXT PRIMARY KEY,
            instance_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            canonical_revision TEXT NOT NULL,
            processor_version TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            source_archive_ids TEXT NOT NULL,
            assessment TEXT,
            resulting_memory_ids TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (
                instance_id,
                conversation_id,
                message_id,
                canonical_revision,
                processor_version
            )
        )
        """
    )
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(memory_work_items)"
        ).fetchall()
    }
    for name, definition in (
        ("candidate_content", "TEXT"),
        ("candidate_created_at", "TEXT"),
        ("decision", "TEXT"),
        ("decision_reason", "TEXT"),
    ):
        if name not in columns:
            connection.execute(
                f"ALTER TABLE memory_work_items ADD COLUMN {name} {definition}"
            )
    connection.commit()
    return connection


def discover_candidate(
    *,
    instance_id,
    conversation_id,
    message_id,
    canonical_revision,
    source_archive_ids=(),
    candidate_content=None,
    candidate_created_at=None,
    processor_version="memory-v1",
    path=LEDGER_PATH,
):
    for value, label in ((instance_id, "instance_id"), (conversation_id, "conversation_id"),
                         (message_id, "message_id"), (canonical_revision, "canonical_revision")):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} is required")
    now = _now()
    connection = _connect(path)

    try:
        connection.execute(
            """
            INSERT OR IGNORE INTO memory_work_items (
                work_item_id,
                instance_id,
                conversation_id,
                message_id,
                canonical_revision,
                processor_version,
                status,
                source_archive_ids,
                candidate_content,
                candidate_created_at,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'discovered', ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                instance_id,
                conversation_id,
                message_id,
                canonical_revision,
                processor_version,
                json.dumps(list(source_archive_ids)),
                candidate_content,
                candidate_created_at,
                now,
                now,
            ),
        )
        connection.commit()

        row = connection.execute(
            """
            SELECT * FROM memory_work_items
            WHERE instance_id = ?
              AND conversation_id = ?
              AND message_id = ?
              AND canonical_revision = ?
              AND processor_version = ?
            """,
            (
                instance_id,
                conversation_id,
                message_id,
                canonical_revision,
                processor_version,
            ),
        ).fetchone()
    finally:
        connection.close()

    return _decode(row)


def update_work_item(
    work_item_id,
    *,
    status,
    assessment=None,
    resulting_memory_ids=None,
    error=None,
    decision=None,
    decision_reason=None,
    increment_attempt=False,
    path=LEDGER_PATH,
):
    if status not in STATUSES:
        raise ValueError(f"Invalid work-item status: {status}")

    connection = _connect(path)
    try:
        connection.execute(
            """
            UPDATE memory_work_items
            SET status = ?,
                assessment = COALESCE(?, assessment),
                resulting_memory_ids = COALESCE(?, resulting_memory_ids),
                error = ?,
                decision = COALESCE(?, decision),
                decision_reason = COALESCE(?, decision_reason),
                attempt_count = attempt_count + ?,
                updated_at = ?
            WHERE work_item_id = ?
            """,
            (
                status,
                json.dumps(assessment) if assessment is not None else None,
                (
                    json.dumps(list(resulting_memory_ids))
                    if resulting_memory_ids is not None
                    else None
                ),
                error,
                decision,
                decision_reason,
                1 if increment_attempt else 0,
                _now(),
                work_item_id,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM memory_work_items WHERE work_item_id = ?",
            (work_item_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise KeyError(f"Unknown work item: {work_item_id}")
    return _decode(row)


def list_work_items(*, instance_id, status=None, path=LEDGER_PATH):
    connection = _connect(path)
    try:
        if status is None:
            rows = connection.execute(
                "SELECT * FROM memory_work_items WHERE instance_id = ?",
                (instance_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM memory_work_items
                WHERE instance_id = ? AND status = ?
                """,
                (instance_id, status),
            ).fetchall()
    finally:
        connection.close()
    return [_decode(row) for row in rows]


def get_work_item(work_item_id, *, path=LEDGER_PATH):
    connection = _connect(path)
    try:
        row = connection.execute(
            "SELECT * FROM memory_work_items WHERE work_item_id = ?",
            (work_item_id,),
        ).fetchone()
    finally:
        connection.close()
    return _decode(row)


def claim_next_work_item(
    *,
    instance_id,
    statuses=("queued", "failed_retryable"),
    target_status="evaluating",
    exclude_work_item_ids=(),
    path=LEDGER_PATH,
):
    """Atomically claim one item for a single resumable worker."""
    if target_status not in STATUSES:
        raise ValueError(f"Invalid work-item status: {target_status}")
    if not statuses:
        return None

    placeholders = ", ".join("?" for _ in statuses)
    excluded = tuple(exclude_work_item_ids)
    exclusion_sql = ""
    if excluded:
        exclusion_placeholders = ", ".join("?" for _ in excluded)
        exclusion_sql = (
            f" AND work_item_id NOT IN ({exclusion_placeholders})"
        )
    connection = _connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            f"""
            SELECT * FROM memory_work_items
            WHERE instance_id = ? AND status IN ({placeholders})
              {exclusion_sql}
            ORDER BY created_at, work_item_id
            LIMIT 1
            """,
            (instance_id, *statuses, *excluded),
        ).fetchone()
        if row is None:
            connection.commit()
            return None

        connection.execute(
            """
            UPDATE memory_work_items
            SET status = ?, attempt_count = attempt_count + 1,
                error = NULL, updated_at = ?
            WHERE work_item_id = ?
            """,
            (target_status, _now(), row["work_item_id"]),
        )
        connection.commit()
        claimed = connection.execute(
            "SELECT * FROM memory_work_items WHERE work_item_id = ?",
            (row["work_item_id"],),
        ).fetchone()
    finally:
        connection.close()
    return _decode(claimed)


def work_item_status_counts(*, instance_id, path=LEDGER_PATH):
    connection = _connect(path)
    try:
        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM memory_work_items
            WHERE instance_id = ?
            GROUP BY status
            """,
            (instance_id,),
        ).fetchall()
    finally:
        connection.close()
    return {row["status"]: row["count"] for row in rows}


def recover_stale_work_items(
    *, instance_id, older_than, path=LEDGER_PATH
):
    """Requeue work abandoned by an interrupted worker before a cutoff."""
    cutoff = older_than.isoformat()
    connection = _connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            """
            SELECT work_item_id, status FROM memory_work_items
            WHERE instance_id = ?
              AND status IN ('evaluating', 'consolidating')
              AND updated_at < ?
            """,
            (instance_id, cutoff),
        ).fetchall()
        for row in rows:
            recovered_status = (
                "queued" if row["status"] == "evaluating" else "accepted"
            )
            connection.execute(
                """
                UPDATE memory_work_items
                SET status = ?, error = ?, updated_at = ?
                WHERE work_item_id = ?
                """,
                (
                    recovered_status,
                    f"Recovered stale {row['status']} work item.",
                    _now(),
                    row["work_item_id"],
                ),
            )
        connection.commit()
    finally:
        connection.close()
    return len(rows)


def _decode(row):
    if row is None:
        return None
    record = dict(row)
    for field in ("source_archive_ids", "assessment", "resulting_memory_ids"):
        if record.get(field) is not None:
            record[field] = json.loads(record[field])
    return record
