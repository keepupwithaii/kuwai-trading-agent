#!/usr/bin/env bash
# run_wake_once.sh -- trigger ONE wake of the agent (paper cycle). Reads the
# env file directly; the systemd unit is bypassed for this single observed
# wake so we can watch its output. After green, enable the timer for normal
# unattended ops.
set -euo pipefail
set -a; . /etc/kuwai/agent.env; set +a
export PYTHONDONTWRITEBYTECODE=1
echo "== one paper wake =="
sudo -u kuwai -E /usr/bin/python3 -B /opt/kuwai/deploy/run_agent.py
echo "== last 6 ledger entries =="
sudo -u kuwai tail -6 /var/lib/kuwai/ledger.log 2>/dev/null || true
echo "== verify chain =="
sudo -u kuwai /usr/bin/python3 -B -c "
import sys; sys.path.insert(0,'/opt/kuwai/commitment-v2/code')
from hashlog import HashLog
print('chain_ok =', HashLog('/var/lib/kuwai/ledger.log').verify_chain())
"
