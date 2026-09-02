#!/usr/bin/env python3
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from src.runtime.worker_exchange_qualification import run_generated_campaign


if __name__ == "__main__":
    result=run_generated_campaign()
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result["passed"] else 1)
