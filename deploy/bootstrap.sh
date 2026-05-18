#!/usr/bin/env bash
# bootstrap.sh -- ONE-SHOT VPS bootstrap (run as root on Ubuntu 24.04 LTS).
# Idempotent: rerunning is safe. Hardens the host per RUNBOOK, lays out
# /opt/kuwai + /var/lib/kuwai, installs systemd units. The operator pastes
# /etc/kuwai/agent.env from agent.env.template AFTER this, then triggers ONE
# paper wake via run_wake_once.sh. NO secret is in this script.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "run as root"; exit 1; fi

# 1. UTC + system updates + python3
timedatectl set-timezone UTC
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3 python3-venv ufw unattended-upgrades

# 2. Firewall: only SSH in; outbound restricted is set by host provider in
#    most cases; the agent's outbound surface is just Alpaca + Anthropic
#    (+ Apify if Block N is live). Default-deny inbound is enough here.
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
yes | ufw enable >/dev/null

# 3. Unattended security upgrades
dpkg-reconfigure -fnoninteractive unattended-upgrades || true

# 4. User and dirs
id kuwai >/dev/null 2>&1 || useradd -m -s /bin/bash kuwai
install -d -o kuwai -g kuwai -m 750 /opt/kuwai
install -d -o kuwai -g kuwai -m 750 /var/lib/kuwai
install -d -o root  -g root  -m 700 /etc/kuwai

# 5. Lay out the build (the operator scp's the tarball to /tmp/kuwai-bundle.tgz).
#    The tarball has top-level dirs commitment-v2/ and deploy/ which land
#    directly under /opt/kuwai/ (no strip-components).
if [[ -f /tmp/kuwai-bundle.tgz ]]; then
    tar -xzf /tmp/kuwai-bundle.tgz -C /opt/kuwai/
    chown -R kuwai:kuwai /opt/kuwai
fi

# 6. systemd units
cp -f /opt/kuwai/deploy/kuwai-agent.service     /etc/systemd/system/
cp -f /opt/kuwai/deploy/kuwai-agent.timer       /etc/systemd/system/
cp -f /opt/kuwai/deploy/kuwai-watchdog.service  /etc/systemd/system/
cp -f /opt/kuwai/deploy/kuwai-watchdog.timer    /etc/systemd/system/
systemctl daemon-reload

# 7. Env template (no values; operator fills before enabling)
if [[ ! -f /etc/kuwai/agent.env ]]; then
    cp /opt/kuwai/deploy/agent.env.template /etc/kuwai/agent.env
    chmod 600 /etc/kuwai/agent.env
    echo "NEXT: edit /etc/kuwai/agent.env (chmod 600) and paste the tokens"
    echo "      from /Users/maraneweda/config/ on your laptop, then enable"
    echo "      timers and run one paper wake:"
    echo "        systemctl enable --now kuwai-watchdog.timer"
    echo "        bash /opt/kuwai/deploy/run_wake_once.sh"
fi

echo "bootstrap OK (host hardened; units installed; paste /etc/kuwai/agent.env)"
