#!/usr/bin/env python3
"""Print the Phase 8 synthetic native Archive acceptance result and summary."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.native_archive_corpus_acceptance import run_corpus


corpus = json.loads((ROOT / "tests/fixtures/native_archive_acceptance_corpus.json").read_text())
expected = json.loads((ROOT / "tests/fixtures/native_archive_acceptance_expected.json").read_text())
result = run_corpus(corpus, expected)
print(json.dumps(result, indent=2, sort_keys=True))
print(result["summary"], file=sys.stderr)
raise SystemExit(0 if result["passed"] else 1)
