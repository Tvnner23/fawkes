#!/usr/bin/env python3
import argparse
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.runtime.production_release import (materialize_release, promote_release,
    rollback_release, verify_release, prepare_environment, bind_legacy_environments,
    PRODUCTION_ROOT, verify_environment)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare/promote exact accepted Fawkes releases")
    parser.add_argument("--production-root", type=Path, default=PRODUCTION_ROOT)
    sub = parser.add_subparsers(dest="action", required=True)
    build = sub.add_parser("build")
    for flag in ("source", "state-root", "instance-id", "accepted-integration",
                 "acceptance-receipt-sha256", "accepted-integration-record-sha256", "validation-reference"):
        build.add_argument("--" + flag, required=True)
    prepare = sub.add_parser("prepare-env"); prepare.add_argument("release_id")
    verify = sub.add_parser("verify-env"); verify.add_argument("release_id")
    verify.add_argument("--require-state-root")
    promote = sub.add_parser("promote"); promote.add_argument("release_id")
    legacy = sub.add_parser("bind-legacy")
    legacy.add_argument("--state-root", required=True); legacy.add_argument("--instance-id", required=True)
    sub.add_parser("rollback")
    sub.add_parser("status")
    args = parser.parse_args(argv)
    root = args.production_root
    if args.action == "build":
        result = materialize_release(source=args.source, state_root=args.state_root,
            instance_id=args.instance_id, accepted_integration=args.accepted_integration,
            acceptance_receipt_sha256=args.acceptance_receipt_sha256,
            accepted_integration_record_sha256=args.accepted_integration_record_sha256,
            validation_reference=args.validation_reference, production_root=root)
    elif args.action == "prepare-env":
        result = prepare_environment(args.release_id, production_root=root)
    elif args.action == "verify-env":
        result = verify_environment(root / "releases" / args.release_id, production_root=root)
        if args.require_state_root:
            record = verify_release(root / "releases" / args.release_id)
            if record["state_owner"]["root"] != str(Path(args.require_state_root).resolve()):
                raise ValueError("native unit state root does not match the prepared release")
    elif args.action == "promote":
        result = promote_release(args.release_id, production_root=root)
    elif args.action == "bind-legacy":
        result = bind_legacy_environments(state_root=args.state_root,
            instance_id=args.instance_id, production_root=root)
    elif args.action == "rollback":
        result = rollback_release(production_root=root)
    elif not (root / "current").is_symlink():
        result = {"status": "no_promoted_release"}
    else:
        result = verify_release(root / "current")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # The operation may have failed before any owner was validated. Report
        # to this caller only; do not initialize a default receipt/notification
        # store or enqueue effects outside the explicitly selected state root.
        raise
