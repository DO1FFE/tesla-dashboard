#!/usr/bin/env bash
set -euo pipefail

SKRIPT_VERZEICHNIS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJEKT_VERZEICHNIS="$(cd "$SKRIPT_VERZEICHNIS/.." && pwd)"

sudo install -d -o root -g root -m 0755 /usr/local/libexec/tesla-dashboard
sudo install -o root -g root -m 0755 \
  "$PROJEKT_VERZEICHNIS/tools/telemetrie_zertifikat_warten.py" \
  /usr/local/libexec/tesla-dashboard/telemetrie_zertifikat_warten.py
sudo install -o root -g root -m 0644 \
  "$SKRIPT_VERZEICHNIS/tesla-dashboard-zertifikat.service" \
  "$SKRIPT_VERZEICHNIS/tesla-dashboard-zertifikat.timer" \
  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tesla-dashboard-zertifikat.timer

echo "Automatische Tesla-Telemetrie-Zertifikatswartung ist aktiv."

# © 2026 Erik Schauer, do1ffe@darc.de
