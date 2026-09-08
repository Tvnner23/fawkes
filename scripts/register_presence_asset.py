"""Register an approved development GLB for one Phoenix; never callable from Chat."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.capabilities.phoenix_presence import (
    PresenceProfileStore, RIG_CONTRACT_VERSION, WORKSHOP_STATIC_CONTRACT_VERSION,
)
from src.instances import get_instance


def main():
    parser = argparse.ArgumentParser(description="Validate and register a local Phoenix development GLB")
    parser.add_argument("glb")
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--revision", required=True, type=int)
    parser.add_argument("--license", required=True)
    parser.add_argument("--creator", required=True)
    parser.add_argument("--source-reference")
    parser.add_argument("--workshop-static", action="store_true",
                        help="register a static experimental manifestation without claiming Presence v1 rig compliance")
    args = parser.parse_args()
    if get_instance(args.instance_id) is None:
        raise SystemExit("instance-id is not a registered Phoenix")
    profile = PresenceProfileStore(args.instance_id).install_development_asset(
        args.glb, asset_id=args.asset_id, revision=args.revision,
        rights={"license": args.license, "creator": args.creator},
        source_reference=args.source_reference,
        actor_principal_id="developer:local_presence_registrar",
        contract_version=(WORKSHOP_STATIC_CONTRACT_VERSION if args.workshop_static else RIG_CONTRACT_VERSION),
    )
    print(json.dumps({"profile_id": profile["profile_id"], "profile_revision": profile["profile_revision"],
                      "asset_id": profile["asset"]["asset_id"], "sha256": profile["asset"]["sha256"],
                      "status": profile["asset"]["status"]}, indent=2))


if __name__ == "__main__": main()
