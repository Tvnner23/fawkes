#!/usr/bin/env python3
"""Wait for the existing app listener and record recovery without credentials."""

from pathlib import Path
import sys
import time
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.runtime.component_supervision import ComponentReceiptStore


def main():
    for _ in range(60):
        try:
            with request.urlopen("http://127.0.0.1:8787/", timeout=1) as response:
                if 200 <= response.status < 500:
                    ComponentReceiptStore().recover_latest("app_server")
                    print("Fawkes app server is reachable on port 8787.", flush=True)
                    return
        except Exception:
            time.sleep(0.5)
    raise SystemExit("Fawkes app server did not become reachable on port 8787")


if __name__ == "__main__":
    main()
