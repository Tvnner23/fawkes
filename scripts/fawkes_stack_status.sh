#!/usr/bin/env bash
set -euo pipefail
systemctl status --no-pager fawkes.target fawkes-app.service fawkes-discord.service || true
curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8787/ >/dev/null && echo 'app_server=reachable'
if [[ -L /home/tvnner/.local/lib/fawkes-production/current ]]; then
  echo "production_release=$(basename "$(readlink -f /home/tvnner/.local/lib/fawkes-production/current)")"
else
  echo 'production_release=not_promoted'
fi
if [[ -r /home/tvnner/.local/state/fawkes/discord-bridge-status.json ]]; then
  python3 -B -c 'import json; print("discord_bridge=" + json.load(open("/home/tvnner/.local/state/fawkes/discord-bridge-status.json"))["state"])'
else
  echo 'discord_bridge=no_status'
fi
echo 'development_url=http://localhost:8787/?view=developer'
