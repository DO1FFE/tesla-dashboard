import json
from datetime import datetime

import pytest


def _log_line(ts, payload):
    return f"{ts.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} {json.dumps(payload)}\n"


def test_compute_parking_losses_tracks_energy_and_range(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_base = datetime(2024, 1, 1, 8, 0, 0, tzinfo=app.LOCAL_TZ)
    entries = [
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": "P"},
                "charge_state": {
                    "battery_level": 80,
                    "ideal_battery_range": 200,
                    "charging_state": "Disconnected",
                },
            },
        },
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": None},
                "charge_state": {
                    "battery_level": 79,
                    "ideal_battery_range": 198,
                    "charging_state": "Disconnected",
                },
            },
        },
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": "D"},
                "charge_state": {
                    "battery_level": 78,
                    "ideal_battery_range": 195,
                    "charging_state": "Disconnected",
                },
            },
        },
    ]

    log_path = tmp_path / "api.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_log_line(ts_base.replace(hour=8 + idx * 2), payload))

    result = app._compute_parking_losses(str(log_path))
    assert "2024-01-01" in result
    day = result["2024-01-01"]
    assert day["energy_pct"] == pytest.approx(2.0)
    # 5 miles total drop -> 5 * 1.60934 km
    assert day["km"] == pytest.approx(5 * app.MILES_TO_KM)


def test_compute_parking_losses_ignores_charging_sessions(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_base = datetime(2024, 2, 1, 6, 0, 0, tzinfo=app.LOCAL_TZ)
    entries = [
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": "P"},
                "charge_state": {
                    "battery_level": 75,
                    "ideal_battery_range": 190,
                    "charging_state": "Stopped",
                },
            },
        },
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": "P"},
                "charge_state": {
                    "battery_level": 73,
                    "ideal_battery_range": 186,
                    "charging_state": "Stopped",
                },
            },
        },
    ]

    log_path = tmp_path / "api.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_log_line(ts_base.replace(minute=idx * 30), payload))

    result = app._compute_parking_losses(str(log_path))
    assert result == {}


def test_compute_statistics_includes_parking_losses(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "STAT_FILE", str(tmp_path / "statistics.json"))

    def fake_state(_entries):
        return {"2024-01-02": {"online": 3600.0, "offline": 0.0, "asleep": 0.0}}

    monkeypatch.setattr(app, "_compute_state_stats", fake_state)
    monkeypatch.setattr(app, "_load_state_entries", lambda: [])
    monkeypatch.setattr(app, "_compute_energy_stats", lambda: {"2024-01-02": 1.0})
    monkeypatch.setattr(app, "_get_trip_files", lambda: [])
    monkeypatch.setattr(
        app,
        "_compute_parking_losses",
        lambda filename=None: {"2024-01-02": {"energy_pct": 3.5, "km": 7.0}},
    )

    stats = app.compute_statistics()
    assert stats["2024-01-02"]["park_energy_pct"] == 3.5
    assert stats["2024-01-02"]["park_km"] == 7.0


def test_compute_statistics_preserves_existing_parking_data(tmp_path, monkeypatch):
    import app

    stat_path = tmp_path / "statistics.json"
    monkeypatch.setattr(app, "STAT_FILE", str(stat_path))

    day = "2024-03-01"

    def fake_state(_entries):
        return {day: {"online": 3600.0, "offline": 0.0, "asleep": 0.0}}

    monkeypatch.setattr(app, "_compute_state_stats", fake_state)
    monkeypatch.setattr(app, "_load_state_entries", lambda: [])
    monkeypatch.setattr(app, "_compute_energy_stats", lambda: {})
    monkeypatch.setattr(app, "_get_trip_files", lambda: [])
    monkeypatch.setattr(
        app,
        "_compute_parking_losses",
        lambda filename=None: {day: {"energy_pct": 4.2, "km": 8.4}},
    )

    first = app.compute_statistics()
    assert first[day]["park_energy_pct"] == 4.2
    assert first[day]["park_km"] == 8.4

    monkeypatch.setattr(app, "_compute_parking_losses", lambda filename=None: {})

    second = app.compute_statistics()
    assert second[day]["park_energy_pct"] == 4.2
    assert second[day]["park_km"] == 8.4


def test_compute_statistics_accumulates_incremental_parking_data(tmp_path, monkeypatch):
    import app

    stat_path = tmp_path / "statistics.json"
    monkeypatch.setattr(app, "STAT_FILE", str(stat_path))

    day = "2024-04-05"

    def fake_state(_entries):
        return {day: {"online": 3600.0, "offline": 0.0, "asleep": 0.0}}

    monkeypatch.setattr(app, "_compute_state_stats", fake_state)
    monkeypatch.setattr(app, "_load_state_entries", lambda: [])
    monkeypatch.setattr(app, "_compute_energy_stats", lambda: {})
    monkeypatch.setattr(app, "_get_trip_files", lambda: [])

    monkeypatch.setattr(
        app,
        "_compute_parking_losses",
        lambda filename=None: {day: {"energy_pct": 1.5, "km": 3.0}},
    )

    first = app.compute_statistics()
    assert first[day]["park_energy_pct"] == 1.5
    assert first[day]["park_km"] == 3.0

    monkeypatch.setattr(
        app,
        "_compute_parking_losses",
        lambda filename=None: {day: {"energy_pct": 0.4, "km": 1.0}},
    )

    second = app.compute_statistics()
    assert second[day]["park_energy_pct"] == 1.9
    assert second[day]["park_km"] == 4.0

    third = app.compute_statistics()
    assert third[day]["park_energy_pct"] == 1.9
    assert third[day]["park_km"] == 4.0
