#!/usr/bin/env bash
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
production=/home/tvnner/.local/lib/fawkes-production
if [[ "${1:-}" == --production-root ]]; then
  [[ $# -ge 2 && -n "$2" ]] || { echo 'Missing production root.' >&2; exit 2; }
  production="$2"; shift 2
fi
# Explicit source/state/accepted-receipt arguments are mandatory. This prepares
# dependencies but does not move current or alter the old shared environment.
record=$(python3 -B "$repo/scripts/manage_fawkes_release.py" --production-root "$production" build "$@")
release_id=$(printf '%s' "$record" | python3 -c 'import json,sys; print(json.load(sys.stdin)["release_id"])')
python3 -B "$repo/scripts/manage_fawkes_release.py" --production-root "$production" prepare-env "$release_id" >/dev/null
printf '%s\n' "$record"
