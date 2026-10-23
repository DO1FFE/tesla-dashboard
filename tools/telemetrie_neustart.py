#!/usr/bin/python3 -I
"""Privilegierter, fest begrenzter Neustart ausschließlich mit Abfrageschutz."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time


ENDE = "2026-10-25T13:50:00Z"
VERZEICHNIS = Path("/usr/local/libexec/tesla-dashboard")
DIENST = "tesla-dashboard.service"


def geschützt(pfad):
    daten = pfad.lstat()
    if (not stat.S_ISREG(daten.st_mode) or daten.st_uid != 0
            or daten.st_mode & 0o022):
        raise RuntimeError("Neustartschutz ist nicht schreibgeschützt installiert")


def prüfen():
    if datetime.now(timezone.utc) >= datetime.fromisoformat(ENDE.replace("Z", "+00:00")):
        raise RuntimeError("Automatischer Neustart nach Überwachungsende verweigert")
    for name in ("telemetrie_neustart.py", "telemetrie_geschuetzter_start.py",
                 "fahrzeugzugriffsschutz.py"):
        geschützt(VERZEICHNIS / name)
    geschützt(Path("/etc/systemd/system/tesla-dashboard.service.d/abfrageschutz.conf"))
    ausgabe = subprocess.check_output([
        "/usr/bin/systemctl", "show", DIENST, "-p", "Environment", "-p", "ExecStart",
    ], text=True, timeout=15)
    if (f"TESLA_DASHBOARD_ABFRAGESPERRE_BIS={ENDE}" not in ausgabe
            or str(VERZEICHNIS / "telemetrie_geschuetzter_start.py") not in ausgabe):
        raise RuntimeError("Dienst verwendet keinen abgesicherten Start")


def neustarten():
    prüfen()
    subprocess.run(["/usr/bin/systemctl", "restart", DIENST], check=True, timeout=60)
    for _ in range(30):
        pid = subprocess.check_output([
            "/usr/bin/systemctl", "show", DIENST, "-p", "MainPID", "--value",
        ], text=True, timeout=10).strip()
        try:
            status = json.loads(Path(
                "/home/do1ffe/tesla-dashboard/data/neustartschutz.json",
            ).read_text(encoding="utf-8"))
            socket = subprocess.check_output([
                "/usr/bin/ss", "-H", "-ltnp", "sport = :8013",
            ], text=True, timeout=10)
            if (pid != "0" and status.get("pid") == int(pid) and f"pid={pid}," in socket
                    and status.get("transport_geschützt") is True and status.get("ende") == ENDE):
                print("Geschützter Dienststart bestätigt; kein HTTP-Gesundheitscheck.")
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError("Geschützter Dienststart nicht bestätigt")


if __name__ == "__main__":
    if os.geteuid() != 0 or sys.argv[1:] not in ([], ["--prüfen"]):
        raise SystemExit("Nur privilegierter Aufruf ohne freie Dienstargumente erlaubt")
    prüfen() if sys.argv[1:] else neustarten()

# © 2026 Erik Schauer, do1ffe@darc.de
