#!/usr/bin/env python3
"""Record a sanitized systemd component exit without accessing service secrets."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.component_supervision import ComponentReceiptStore


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("component", choices=("app_server", "discord_bridge"))
    parser.add_argument("--result", default="unknown")
    parser.add_argument("--exit-code")
    parser.add_argument("--exit-status")
    parser.add_argument("--restart-attempt", type=int, default=1)
    args = parser.parse_args(argv)
    if args.result in {"success", "done"}:
        return
    code = args.exit_status if args.exit_status not in {None, ""} else args.exit_code
    store = ComponentReceiptStore()
    attempt = max(args.restart_attempt, store.next_restart_attempt(args.component))
    store.failure(
        component=args.component, stage="process_exit", category=args.result,
        process_exit_code=code, restart_attempt=attempt,
        service_state="activating", notify=attempt >= 3,
    )


if __name__ == "__main__":
    main()
