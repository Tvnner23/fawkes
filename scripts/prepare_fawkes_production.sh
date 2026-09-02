#!/usr/bin/env bash
set -euo pipefail
cd /home/tvnner/fawkes
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest \
  tests.test_discord_bot tests.test_discord_webhook tests.test_app_chat \
  tests.test_component_supervision tests.test_fawkes_services tests.test_production_release
validation="production-preparation-$(date -u +%Y%m%dT%H%M%SZ)"
record=$(.venv/bin/python -B scripts/manage_fawkes_release.py build --validation-reference "$validation")
release_id=$(printf '%s' "$record" | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["release_id"])')
.venv/bin/python -B scripts/manage_fawkes_release.py promote "$release_id" >/dev/null
production=/home/tvnner/.local/lib/fawkes-production
if [[ ! -x "$production/venv/bin/python" ]]; then
  python3 -m venv "$production/venv"
fi
"$production/venv/bin/pip" install --disable-pip-version-check -r "$production/current/requirements.txt"
echo "Approved production release prepared: $release_id"
