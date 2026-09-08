#!/usr/bin/env bash
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Native unit definitions bind the production owner; alternate roots are for
# build/preparation rehearsals, never native promotion through this wrapper.
for argument in "$@"; do
  [[ "$argument" != --production-root ]] || { echo 'Use the release manager for isolated roots; this native wrapper has a fixed production owner.' >&2; exit 2; }
done
record=$("$repo/scripts/prepare_fawkes_production.sh" "$@")
release_id=$(printf '%s' "$record" | python3 -c 'import json,sys; print(json.load(sys.stdin)["release_id"])')
sudo "$repo/scripts/install_fawkes_systemd.sh" "$release_id"
python3 -B "$repo/scripts/manage_fawkes_release.py" promote "$release_id"
sudo systemctl restart fawkes-app.service
"$repo/scripts/fawkes_stack_status.sh"
