#!/usr/bin/env bash
set -euo pipefail
systemctl status --no-pager fawkes.target fawkes-app.service fawkes-discord.service || true
curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8787/ >/dev/null && echo 'app_server=reachable'
if [[ -r /home/tvnner/.local/state/fawkes/discord-bridge-status.json ]]; then
  /home/tvnner/fawkes/.venv/bin/python -B -c 'import json; print("discord_bridge=" + json.load(open("/home/tvnner/.local/state/fawkes/discord-bridge-status.json"))["state"])'
else
  echo 'discord_bridge=no_status'
fi
