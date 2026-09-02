#!/usr/bin/env bash

set -euo pipefail

SKRIPT_VERZEICHNIS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJEKT_VERZEICHNIS="$(cd "$SKRIPT_VERZEICHNIS/.." && pwd)"
MONITORING_VERZEICHNIS="$PROJEKT_VERZEICHNIS/data/monitoring"

install -d -m 0700 "$MONITORING_VERZEICHNIS"
touch \
  "$MONITORING_VERZEICHNIS/fleet-mqtt.tsv" \
  "$MONITORING_VERZEICHNIS/fahrtstatus.ndjson"
chmod 0600 \
  "$MONITORING_VERZEICHNIS/fleet-mqtt.tsv" \
  "$MONITORING_VERZEICHNIS/fahrtstatus.ndjson"

sudo install -m 0644 \
  "$SKRIPT_VERZEICHNIS/tesla-dashboard-mqtt-monitor.service" \
  /etc/systemd/system/tesla-dashboard-mqtt-monitor.service
sudo install -m 0644 \
  "$SKRIPT_VERZEICHNIS/tesla-dashboard-status-monitor.service" \
  /etc/systemd/system/tesla-dashboard-status-monitor.service
sudo install -m 0644 \
  "$SKRIPT_VERZEICHNIS/tesla-dashboard-monitoring.logrotate" \
  /etc/logrotate.d/tesla-dashboard-monitoring

sudo systemctl daemon-reload
sudo systemctl enable --now \
  tesla-dashboard-mqtt-monitor.service \
  tesla-dashboard-status-monitor.service

echo "Dauerhafte Tesla-Telemetrieüberwachung ist aktiv."

# © 2026 Erik Schauer, do1ffe@darc.de
