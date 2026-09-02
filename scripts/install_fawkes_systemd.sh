#!/usr/bin/env bash
set -euo pipefail

repo=/home/tvnner/fawkes
install -d -m 0700 -o tvnner -g tvnner /home/tvnner/.config/fawkes /home/tvnner/.local/state/fawkes
for unit in fawkes-app.service fawkes-discord.service fawkes-failure-notifier.service fawkes-failure-notifier.timer fawkes.target; do
  install -m 0644 "$repo/deploy/systemd/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable fawkes.target fawkes-failure-notifier.timer
echo 'Fawkes systemd definitions installed and enabled. Populate protected credentials before starting fawkes.target.'
