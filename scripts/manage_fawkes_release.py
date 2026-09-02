#!/usr/bin/env python3
import argparse
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.runtime.production_release import materialize_release, promote_release, rollback_release, verify_release, CURRENT_LINK
from src.runtime.component_supervision import ComponentReceiptStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="Materialize/promote exact Fawkes production releases")
    sub = parser.add_subparsers(dest="action", required=True)
    build = sub.add_parser("build"); build.add_argument("--validation-reference", required=True)
    promote = sub.add_parser("promote"); promote.add_argument("release_id")
    sub.add_parser("rollback")
    sub.add_parser("status")
    args = parser.parse_args(argv)
    if args.action == "build": result = materialize_release(validation_reference=args.validation_reference)
    elif args.action == "promote": result = promote_release(args.release_id)
    elif args.action == "rollback": result = rollback_release()
    elif not CURRENT_LINK.is_symlink(): result = {"status": "no_promoted_release"}
    else: result = verify_release(CURRENT_LINK)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        ComponentReceiptStore().failure(
            component="release_manager", stage="promotion_or_rollback",
            category="release_operation_failed", exception=exc,
            service_state="needs_tanner", notify=True,
        )
        raise
