#!/bin/bash
# One-time setup for Apple Silicon GPU power telemetry (advisor request
# 2026-07-14: HPC-vs-M5 energy comparison).
#
# Installs a sudoers drop-in allowing THIS user to run /usr/bin/powermetrics
# without a password, so the harness's background telemetry thread can sample
# GPU power during unattended runs. powermetrics is read-only Apple system
# profiling; no other command is granted.
#
#   bash scripts/setup_m5_power.sh        # prompts for your password once
#
# Verify afterwards:
#   sudo -n /usr/bin/powermetrics --samplers gpu_power -i 500 -n 1 | grep "GPU Power"
set -euo pipefail

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This setup is for macOS (Apple Silicon) only." >&2
  exit 1
fi

RULE="$(whoami) ALL=(root) NOPASSWD: /usr/bin/powermetrics"
DEST=/etc/sudoers.d/powermetrics-telemetry

echo "Installing sudoers rule: $RULE"
echo "$RULE" | sudo tee "$DEST" >/dev/null
sudo chmod 440 "$DEST"

# validate the sudoers file we just wrote (a bad drop-in can lock out sudo)
sudo visudo -cf "$DEST"

echo "OK. Verifying passwordless powermetrics..."
if sudo -n /usr/bin/powermetrics --samplers gpu_power -i 500 -n 1 2>/dev/null | grep -q "GPU Power"; then
  echo "✅ GPU power capture is live. Metal rows will now populate gpu_power_w."
else
  echo "⚠️  Rule installed but verification failed — run the verify line above manually." >&2
  exit 1
fi
