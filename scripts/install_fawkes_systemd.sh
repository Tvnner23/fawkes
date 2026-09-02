#!/usr/bin/env bash
set -euo pipefail

repo=/home/tvnner/fawkes
install -d -m 0700 -o tvnner -g tvnner /home/tvnner/.config/fawkes /home/tvnner/.local/state/fawkes
test -L /home/tvnner/.local/lib/fawkes-production/current || { echo 'No approved production release is promoted.' >&2; exit 2; }
test -x /home/tvnner/.local/lib/fawkes-production/venv/bin/python || { echo 'Production virtual environment is unavailable.' >&2; exit 2; }
for unit in fawkes-production-ready.service fawkes-app.service fawkes-discord.service fawkes-failure-notifier.service fawkes-failure-notifier.timer fawkes.target; do
  install -m 0644 "$repo/deploy/systemd/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable fawkes.target fawkes-failure-notifier.timer
install -m 0440 "$repo/deploy/sudoers/fawkes-runtime-control" /etc/sudoers.d/fawkes-runtime-control
visudo -cf /etc/sudoers.d/fawkes-runtime-control >/dev/null
echo 'Fawkes systemd definitions installed and enabled. Populate protected credentials before starting fawkes.target.'
