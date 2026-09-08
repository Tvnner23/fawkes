"""Real marker-absent Archive sources for pre-existing isolated unit tests."""

import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from src.capture import canonical


class LegacyArchiveSources:
    """Supply the historical IDs these unit tests previously only invented."""

    archive_source_owner = None
    archive_source_conversation = "legacy-synthetic"
    archive_source_messages = (("message-1", "archive-1", "user"), ("message-2", "archive-2", "user"),
                               ("independent-confirmation", "archive-confirmation", "user"))

    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix="fawkes-legacy-source-fixture-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        raw, meta = root / "raw", root / "meta"
        raw.mkdir()
        meta.mkdir()
        for name, directory in (("RAW_DIR", raw), ("META_DIR", meta)):
            patched = patch.object(canonical, name, directory)
            patched.start()
            self.addCleanup(patched.stop)
        for message_id, archive_id, role in self.archive_source_messages:
            record = {"message_id": message_id, "conversation_id": self.archive_source_conversation, "role": role,
                      "text": "Synthetic marker-absent historical evidence."}
            data = json.dumps(record).encode()
            (raw / (archive_id + ".json")).write_bytes(data)
            metadata = {"archive_id": archive_id, "instance_id": self.archive_source_owner,
                "conversation_id": self.archive_source_conversation,
                "capture_type": "message_state", "created_at": "2026-01-01T00:00:00+00:00",
                "raw_file": archive_id + ".json", "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
            (meta / (archive_id + ".json")).write_text(json.dumps(metadata))
