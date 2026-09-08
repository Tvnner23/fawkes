#!/usr/bin/env bash
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
production=/home/tvnner/.local/lib/fawkes-production
release_id="${1:?Supply the exact prepared accepted release ID}"
case "${2:---app-only}" in
  --app-only) full_stack=false ;;
  --full-stack) full_stack=true ;;
  *) echo 'Use --app-only (default) or --full-stack.' >&2; exit 2 ;;
esac
[[ $# -le 2 ]] || { echo 'Unexpected installer arguments.' >&2; exit 2; }
python3 -B "$repo/scripts/manage_fawkes_release.py" verify-env "$release_id" --require-state-root /home/tvnner/fawkes >/dev/null
release="$production/releases/$release_id"
# A one-time explicit bind-legacy step preserves the actual old release pair.
if [[ -L "$production/current" && ! -f "$production/legacy-environments.json" ]]; then
  echo 'Bind the existing legacy current/previous environments explicitly before installing.' >&2
  exit 2
fi
install -d -m 0700 -o tvnner -g tvnner /home/tvnner/.config/fawkes /home/tvnner/.local/state/fawkes
install -d -m 0700 -o tvnner -g tvnner /home/tvnner/fawkes/component-receipts /home/tvnner/fawkes/pending-failure-notifications /home/tvnner/fawkes/development_attention
install -m 0755 "$release/scripts/run_fawkes_release.py" "$production/run_fawkes_release.py"
units=(fawkes-production-ready.service fawkes-app.service)
if "$full_stack"; then
  units+=(fawkes-discord.service fawkes-failure-notifier.service fawkes-failure-notifier.timer fawkes.target)
fi
for unit in "${units[@]}"; do
  install -m 0644 "$release/deploy/systemd/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
if "$full_stack"; then
  systemctl enable fawkes.target fawkes-discord.service fawkes-failure-notifier.timer
  install -m 0440 "$release/deploy/sudoers/fawkes-runtime-control" /etc/sudoers.d/fawkes-runtime-control
  visudo -cf /etc/sudoers.d/fawkes-runtime-control >/dev/null
else
  systemctl enable fawkes-app.service
fi
echo 'Verified release launcher and systemd definitions installed. No release promoted or service started.'
