#!/usr/bin/env bash
set -euo pipefail
cd /home/tvnner/fawkes
./scripts/prepare_fawkes_production.sh
sudo -n /usr/bin/systemctl restart fawkes.target
./scripts/fawkes_stack_status.sh
