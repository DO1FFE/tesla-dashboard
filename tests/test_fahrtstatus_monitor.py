import hashlib
import json

from tools import fahrtstatus_monitor


def test_cache_snapshot_enthält_fahrt_navigation_und_öffnungen():
    route_line = "abc123"
    daten = {
        "state": "online",
        "timestamp": 1234,
        "fleet_telemetry_received_at": 1230,
        "drive_state": {
            "timestamp": 1229,
            "gps_as_of": 1228,
            "shift_state": "D",
            "speed": 20,
            "latitude": 51.1,
            "longitude": 7.1,
            "active_route_active": True,
            "active_route_destination": "Ziel",
            "active_route_line": route_line,
        },
        "path": [[51.1, 7.1], [51.2, 7.2]],
        "path_generation": "fahrt-1",
        "charge_state": {
            "charging_state": "Disconnected",
            "charger_power": 0,
        },
        "vehicle_state": {
            "df": 1,
            "fd_window": 0,
        },
        "fleet_telemetry_field_received_at": {
            "Location": 1228,
            "RouteLine": 1227,
        },
    }

    snapshot = fahrtstatus_monitor.cache_snapshot(
        daten,
        beobachtet_am="2026-08-29T14:00:00.000Z",
    )

    assert snapshot["quelle"] == "cache"
    assert snapshot["drive"]["shift_state"] == "D"
    assert snapshot["drive"]["active_route_destination"] == "Ziel"
    assert snapshot["drive"]["route_line"] == {
        "vorhanden": True,
        "zeichen": len(route_line),
        "sha256": hashlib.sha256(route_line.encode("utf-8")).hexdigest(),
    }
    assert snapshot["fahrtpfad"] == {
        "punkte": 2,
        "generation": "fahrt-1",
    }
    assert snapshot["öffnungen"]["df"] == 1
    assert snapshot["feld_empfangen_am"]["RouteLine"] == 1227


def test_profil_snapshot_enthält_synchronisierung_und_wiederholungen():
    snapshot = fahrtstatus_monitor.profil_snapshot({
        "current": "live",
        "target": "live_extended",
        "config_synced": False,
        "config_sync_state": "pending",
        "live_retry_active": True,
        "live_retry_attempts": 3,
        "config_revision": 4,
    })

    assert snapshot["quelle"] == "profil"
    assert snapshot["current"] == "live"
    assert snapshot["target"] == "live_extended"
    assert snapshot["config_sync_state"] == "pending"
    assert snapshot["live_retry_attempts"] == 3
    assert snapshot["config_revision"] == 4


def test_geänderte_snapshots_schreibt_nur_neue_dateistände(tmp_path):
    cache = tmp_path / "cache.json"
    profil = tmp_path / "profil.json"
    cache.write_text(json.dumps({"state": "online"}), encoding="utf-8")
    profil.write_text(json.dumps({"current": "parked"}), encoding="utf-8")
    signaturen = {}
    dateien = (("cache", cache), ("profil", profil))

    erste = fahrtstatus_monitor.geänderte_snapshots(dateien, signaturen)
    zweite = fahrtstatus_monitor.geänderte_snapshots(dateien, signaturen)
    profil.write_text(json.dumps({"current": "live"}), encoding="utf-8")
    dritte = fahrtstatus_monitor.geänderte_snapshots(dateien, signaturen)

    assert [snapshot["quelle"] for snapshot in erste] == ["cache", "profil"]
    assert zweite == []
    assert len(dritte) == 1
    assert dritte[0]["quelle"] == "profil"
    assert dritte[0]["current"] == "live"
