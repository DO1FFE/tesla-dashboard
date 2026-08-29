#!/usr/bin/env python3
"""Protokolliere lokale Fahrzeug- und Profiländerungen ohne Netzwerkabfragen."""

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path


STANDARD_CACHE_DATEI = Path("data/default/cache.json")
STANDARD_PROFIL_DATEI = Path("data/tesla_fleet/telemetry_profile_status.json")
STANDARD_AUSGABE_DATEI = Path("/tmp/tesla-goal-status-monitor.ndjson")


def utc_zeitstempel():
    """Liefere den aktuellen UTC-Zeitpunkt mit Millisekunden."""

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00",
        "Z",
    )


def _auswahl(daten, felder):
    """Übernehme nur die angegebenen Schlüssel aus einem Wörterbuch."""

    if not isinstance(daten, dict):
        return {}
    return {feld: daten.get(feld) for feld in felder}


def _routeline_info(route_line):
    """Erzeuge eine kompakte Signatur der RouteLine ohne deren Inhalt zu duplizieren."""

    if not isinstance(route_line, str) or not route_line:
        return {
            "vorhanden": False,
            "zeichen": 0,
            "sha256": None,
        }
    return {
        "vorhanden": True,
        "zeichen": len(route_line),
        "sha256": hashlib.sha256(route_line.encode("utf-8")).hexdigest(),
    }


def cache_snapshot(daten, beobachtet_am=None):
    """Reduziere den Dashboard-Cache auf die für eine Probefahrt relevanten Werte."""

    drive = daten.get("drive_state") if isinstance(daten, dict) else {}
    charge = daten.get("charge_state") if isinstance(daten, dict) else {}
    vehicle = daten.get("vehicle_state") if isinstance(daten, dict) else {}
    feld_empfang = (
        daten.get("fleet_telemetry_field_received_at")
        if isinstance(daten, dict)
        else {}
    )
    pfad = daten.get("path") if isinstance(daten, dict) else None
    if not isinstance(pfad, list):
        pfad = []

    return {
        "beobachtet_am_utc": beobachtet_am or utc_zeitstempel(),
        "quelle": "cache",
        "state": daten.get("state"),
        "timestamp": daten.get("timestamp"),
        "telemetrie_empfangen_am": daten.get("fleet_telemetry_received_at"),
        "drive": {
            **_auswahl(
                drive,
                (
                    "timestamp",
                    "gps_as_of",
                    "shift_state",
                    "speed",
                    "latitude",
                    "longitude",
                    "active_route_active",
                    "active_route_destination",
                    "active_route_latitude",
                    "active_route_longitude",
                    "active_route_updated_at",
                ),
            ),
            "route_line": _routeline_info(
                drive.get("active_route_line") if isinstance(drive, dict) else None
            ),
        },
        "fahrtpfad": {
            "punkte": len(pfad),
            "generation": daten.get("path_generation"),
        },
        "charge": _auswahl(
            charge,
            (
                "charging_state",
                "charger_power",
                "battery_level",
                "charge_port_door_open",
            ),
        ),
        "öffnungen": _auswahl(
            vehicle,
            (
                "df",
                "dr",
                "pf",
                "pr",
                "fd_window",
                "fp_window",
                "rd_window",
                "rp_window",
            ),
        ),
        "feld_empfangen_am": _auswahl(
            feld_empfang,
            (
                "Gear",
                "VehicleSpeed",
                "Location",
                "GpsHeading",
                "DestinationLocation",
                "DestinationName",
                "RouteLine",
                "DoorState",
                "FdWindow",
                "FpWindow",
                "RdWindow",
                "RpWindow",
                "ChargeState",
                "ACChargingPower",
                "DCChargingPower",
            ),
        ),
    }


def profil_snapshot(daten, beobachtet_am=None):
    """Reduziere den Profilstatus auf Umschaltung und Tesla-Bestätigung."""

    snapshot = {
        "beobachtet_am_utc": beobachtet_am or utc_zeitstempel(),
        "quelle": "profil",
    }
    snapshot.update(
        _auswahl(
            daten,
            (
                "current",
                "target",
                "target_since",
                "last_sent",
                "last_sent_profile",
                "last_posted_at",
                "last_posted_profile",
                "config_synced",
                "config_sync_state",
                "config_sync_profile",
                "config_sync_checked_at",
                "config_sync_error",
                "config_revision",
                "live_retry_active",
                "live_retry_attempts",
                "live_stable_since",
                "charging_observed",
                "post_charge_live_since",
                "updated_at",
            ),
        )
    )
    return snapshot


def _datei_signatur(pfad):
    """Erkenne auch mehrere Dateiänderungen innerhalb derselben Sekunde."""

    status = pfad.stat()
    return status.st_mtime_ns, status.st_size


def _snapshot_laden(pfad, quelle, beobachtet_am=None):
    """Lade eine JSON-Datei und erzeuge den passenden Snapshot."""

    with pfad.open("r", encoding="utf-8") as datei:
        daten = json.load(datei)
    if quelle == "cache":
        return cache_snapshot(daten, beobachtet_am=beobachtet_am)
    return profil_snapshot(daten, beobachtet_am=beobachtet_am)


def geänderte_snapshots(dateien, letzte_signaturen):
    """Liefere Snapshots aller seit der letzten Prüfung geänderten Dateien."""

    ergebnis = []
    for quelle, pfad in dateien:
        try:
            signatur = _datei_signatur(pfad)
        except OSError:
            continue
        if letzte_signaturen.get(quelle) == signatur:
            continue
        try:
            snapshot = _snapshot_laden(pfad, quelle)
        except (OSError, json.JSONDecodeError):
            continue
        letzte_signaturen[quelle] = signatur
        ergebnis.append(snapshot)
    return ergebnis


def monitor_starten(cache_datei, profil_datei, ausgabe_datei, intervall, dauer):
    """Schreibe lokale Zustandsänderungen fortlaufend als NDJSON."""

    dateien = (
        ("cache", cache_datei),
        ("profil", profil_datei),
    )
    letzte_signaturen = {}
    ende = None if dauer <= 0 else time.monotonic() + dauer
    ausgabe_datei.parent.mkdir(parents=True, exist_ok=True)

    with ausgabe_datei.open("a", encoding="utf-8") as ausgabe:
        while ende is None or time.monotonic() < ende:
            for snapshot in geänderte_snapshots(dateien, letzte_signaturen):
                ausgabe.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
                ausgabe.flush()
            time.sleep(intervall)


def parser_erstellen():
    """Erstelle den Kommandozeilenparser."""

    parser = argparse.ArgumentParser(
        description="Lokaler Fahrt- und Telemetrieprofil-Monitor ohne Netzwerkzugriff.",
    )
    parser.add_argument("--cache", type=Path, default=STANDARD_CACHE_DATEI)
    parser.add_argument("--profil", type=Path, default=STANDARD_PROFIL_DATEI)
    parser.add_argument("--ausgabe", type=Path, default=STANDARD_AUSGABE_DATEI)
    parser.add_argument("--intervall", type=float, default=0.5)
    parser.add_argument(
        "--dauer",
        type=float,
        default=172800.0,
        help="Laufzeit in Sekunden; 0 bedeutet unbegrenzt.",
    )
    return parser


def main(argv=None):
    """Starte den lokalen Zustandsmonitor."""

    args = parser_erstellen().parse_args(argv)
    if args.intervall <= 0:
        raise SystemExit("Das Intervall muss größer als 0 sein.")
    monitor_starten(
        args.cache,
        args.profil,
        args.ausgabe,
        args.intervall,
        args.dauer,
    )


if __name__ == "__main__":
    main()


# © 2026 Erik Schauer, do1ffe@darc.de
