#!/usr/bin/env python3
"""Explicitly refresh the standing read-only WINDOWS CODEX review snapshot."""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.windows_codex_reviewer import materialize_standing_windows_snapshot


def main():
    result = materialize_standing_windows_snapshot(ROOT)
    print(json.dumps({
        "candidate_snapshot_id": result["candidate_snapshot_id"],
        "record_sha256": result["record_sha256"],
        "file_count": result["file_count"],
        "total_byte_length": result["total_byte_length"],
        "repository_path_windows": result["repository_path_windows"],
        "current_pointer_windows": result["current_pointer_windows"],
        "matches_current_source": result["matches_current_source"],
        "created": result["created"],
        "read_only_role_contract": result["read_only_role_contract"],
        "writeback_to_authoritative_repository": result["writeback_to_authoritative_repository"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
