import json
from datetime import datetime

import pytest


def _log_line(ts, payload):
    return f"{ts.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} {json.dumps(payload)}\n"


def test_compute_parking_losses_splits_losses_across_midnight(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_start = datetime(2024, 1, 1, 22, 0, 0, tzinfo=app.LOCAL_TZ)
    entries = [
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": "P"},
                "charge_state": {
                    "battery_level": 80,
                    "ideal_battery_range": 210,
                    "charging_state": "Disconnected",
                },
            },
        },
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": "P"},
                "charge_state": {
                    "battery_level": 77,
                    "ideal_battery_range": 201,
                    "charging_state": "Disconnected",
                },
            },
        },
    ]

    log_path = tmp_path / "api.log"
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(_log_line(ts_start, entries[0]))
        handle.write(_log_line(ts_start.replace(day=2, hour=2), entries[1]))

    result = app._compute_parking_losses(str(log_path))
    first_day = result["2024-01-01"]
    second_day = result["2024-01-02"]

    total_drop_pct = 3.0
    total_drop_miles = 9.0

    end_ts = ts_start.replace(day=2, hour=2)
    midnight = datetime(2024, 1, 2, 0, 0, 0, tzinfo=app.LOCAL_TZ)
    total_seconds = (end_ts - ts_start).total_seconds()
    before_midnight = max((midnight - ts_start).total_seconds(), 0.0)
    after_midnight = max(total_seconds - before_midnight, 0.0)

    expected_first_pct = total_drop_pct * before_midnight / total_seconds
    expected_second_pct = total_drop_pct * after_midnight / total_seconds
    expected_first_km = total_drop_miles * app.MILES_TO_KM * before_midnight / total_seconds
    expected_second_km = total_drop_miles * app.MILES_TO_KM * after_midnight / total_seconds

    assert first_day["energy_pct"] == pytest.approx(expected_first_pct)
    assert second_day["energy_pct"] == pytest.approx(expected_second_pct)
    assert first_day["km"] == pytest.approx(expected_first_km)
    assert second_day["km"] == pytest.approx(expected_second_km)


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


def test_compute_parking_losses_uses_est_range_when_ideal_missing(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_base = datetime(2024, 5, 1, 6, 0, 0, tzinfo=app.LOCAL_TZ)
    entries = [
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": "P"},
                "charge_state": {
                    "battery_level": 70,
                    "est_battery_range": 150,
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
                    "battery_level": 69,
                    "est_battery_range": 148,
                    "charging_state": "Disconnected",
                },
            },
        },
    ]

    log_path = tmp_path / "api.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_log_line(ts_base.replace(hour=6 + idx), payload))

    result = app._compute_parking_losses(str(log_path))
    assert "2024-05-01" in result
    day = result["2024-05-01"]
    assert day["energy_pct"] == pytest.approx(1.0)
    assert day["km"] == pytest.approx(2 * app.MILES_TO_KM)


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
