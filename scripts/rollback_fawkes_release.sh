#!/usr/bin/env bash
set -euo pipefail
cd /home/tvnner/fawkes
.venv/bin/python -B scripts/manage_fawkes_release.py rollback
sudo -n /usr/bin/systemctl restart fawkes.target
./scripts/fawkes_stack_status.sh
