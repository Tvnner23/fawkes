#!/usr/bin/env python3
"""Real WSL-to-Windows acceptance for portable snapshot identity v2."""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.disposable_verifier import materialize_candidate
from src.runtime.windows_codex_reviewer import _windows_path


WINDOWS_TEMP = Path("/mnt/c/Users/tjbha/AppData/Local/Temp")
POWERSHELL = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")


def windows_identity(script, repository):
    completed = subprocess.run([
        str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", _windows_path(script), "-RepositoryPath", _windows_path(repository),
    ], capture_output=True, text=True, encoding="utf-8", errors="strict", check=False,
       timeout=120)
    if completed.returncode != 0:
        raise RuntimeError("Windows snapshot identity recomputation failed: " + completed.stderr)
    return json.loads(completed.stdout)


def main():
    with tempfile.TemporaryDirectory(prefix="fawkes-portable-source-") as source_name:
        source = Path(source_name)
        for relative, content in (("B.txt", b"B\n"), ("a.txt", b"a\n"),
                                  ("nested/A.txt", b"A\n"),
                                  ("nested/b.txt", b"b\n")):
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        with tempfile.TemporaryDirectory(prefix="fawkes-portable-windows-",
                                         dir=WINDOWS_TEMP) as fixture_name:
            fixture = Path(fixture_name)
            repository = fixture / "repository"
            provenance = materialize_candidate(source, repository)
            verifier = fixture / "recompute_snapshot_identity.ps1"
            shutil.copyfile(ROOT / "scripts/recompute_snapshot_identity.ps1", verifier)
            windows_before = windows_identity(verifier, repository)
            if windows_before["candidate_snapshot_id"] != provenance["candidate_snapshot_id"]:
                raise RuntimeError("WSL and Windows snapshot identities differ")
            target = repository / "nested/b.txt"
            target.write_bytes(b"c\n")
            windows_after = windows_identity(verifier, repository)
            if windows_after["candidate_snapshot_id"] == provenance["candidate_snapshot_id"]:
                raise RuntimeError("one-byte mutation did not change snapshot identity")
            print(json.dumps({
                "paths": ["B.txt", "a.txt", "nested/A.txt", "nested/b.txt"],
                "wsl_snapshot_id": provenance["candidate_snapshot_id"],
                "windows_snapshot_id": windows_before["candidate_snapshot_id"],
                "identities_match": True,
                "one_byte_mutation_snapshot_id": windows_after["candidate_snapshot_id"],
                "one_byte_mutation_rejected": True,
                "file_count": windows_before["file_count"],
                "total_byte_length": windows_before["total_byte_length"],
            }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
