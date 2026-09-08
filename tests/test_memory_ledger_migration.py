import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import src.memory.ledger as ledger


class MemoryLedgerMigrationTests(unittest.TestCase):
    def test_concurrent_legacy_schema_upgrade_is_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute(
                """
                CREATE TABLE memory_work_items (
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
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.commit()
            connection.close()

            original_connect = ledger.sqlite3.connect
            pre_migration_columns = threading.Barrier(2)

            class InstrumentedConnection(sqlite3.Connection):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.migration_locked = False

                def execute(self, sql, *args, **kwargs):
                    cursor = super().execute(sql, *args, **kwargs)
                    statement = str(sql).strip()
                    if statement == "BEGIN IMMEDIATE":
                        self.migration_locked = True
                    if (
                        statement.startswith("PRAGMA table_info(memory_work_items)")
                        and not self.migration_locked
                    ):
                        pre_migration_columns.wait(timeout=2)
                    return cursor

            def instrumented_connect(*args, **kwargs):
                kwargs["factory"] = InstrumentedConnection
                return original_connect(*args, **kwargs)

            errors = []
            error_lock = threading.Lock()

            def list_items():
                try:
                    ledger.list_work_items(instance_id="fawkes", path=path)
                except BaseException as exc:
                    with error_lock:
                        errors.append(exc)

            with patch.object(ledger.sqlite3, "connect", instrumented_connect):
                threads = [threading.Thread(target=list_items) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)

            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
            connection = sqlite3.connect(path)
            try:
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(memory_work_items)"
                    )
                }
            finally:
                connection.close()
            self.assertTrue({
                "candidate_content",
                "candidate_created_at",
                "decision",
                "decision_reason",
            }.issubset(columns))


if __name__ == "__main__":
    unittest.main()
