#!/usr/bin/env bash
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -B "$repo/scripts/manage_fawkes_release.py" rollback
sudo systemctl restart fawkes-app.service
"$repo/scripts/fawkes_stack_status.sh"
