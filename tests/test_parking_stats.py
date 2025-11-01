import json
import os
from datetime import datetime

import pytest


def _log_line(ts, payload):
    return f"{ts.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} {json.dumps(payload)}\n"


@pytest.fixture
def rotated_api_logs(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    start_ts = datetime(2024, 6, 1, 20, 0, 0, tzinfo=app.LOCAL_TZ)
    end_ts = datetime(2024, 6, 1, 22, 0, 0, tzinfo=app.LOCAL_TZ)

    start_payload = {
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
    }
    end_payload = {
        "endpoint": "get_vehicle_data",
        "data": {
            "id_s": "veh",
            "drive_state": {"shift_state": "P"},
            "charge_state": {
                "battery_level": 79,
                "ideal_battery_range": 198,
                "charging_state": "Disconnected",
            },
        },
    }

    rotated_path = tmp_path / "api.log.2024-06-01T200000"
    with rotated_path.open("w", encoding="utf-8") as handle:
        handle.write(_log_line(start_ts, start_payload))
    os.utime(rotated_path, (start_ts.timestamp(), start_ts.timestamp()))

    main_path = tmp_path / "api.log"
    with main_path.open("w", encoding="utf-8") as handle:
        handle.write(_log_line(end_ts, end_payload))
    os.utime(main_path, (end_ts.timestamp(), end_ts.timestamp()))

    return {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "data_dir": tmp_path,
    }


def test_compute_parking_losses_processes_date_rotated_logs(rotated_api_logs):
    import app

    result = app._compute_parking_losses()

    day = rotated_api_logs["start_ts"].date().isoformat()
    assert day in result

    entry = result[day]
    assert entry["energy_pct"] == pytest.approx(1.0)
    assert entry["km"] == pytest.approx(2 * app.MILES_TO_KM)

    log_path = rotated_api_logs["data_dir"] / "park-loss.log"
    assert log_path.exists()

    first_run = log_path.read_text(encoding="utf-8").splitlines()
    assert len(first_run) == 1

    app._compute_parking_losses()

    second_run = log_path.read_text(encoding="utf-8").splitlines()
    assert second_run == first_run


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


def test_compute_parking_losses_handles_offline_entries(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(app, "update_api_list", lambda data: None)
    monkeypatch.setattr(app, "get_tesla", lambda: object())
    monkeypatch.setattr(
        app, "_cached_vehicle_list", lambda tesla, ttl=86400: [{"id_s": "veh"}]
    )
    monkeypatch.setattr(app, "_default_vehicle_id", None)

    log_path = tmp_path / "api.log"

    class Recorder:
        def __init__(self, path):
            self.path = path
            self.next_ts = None

        def set_timestamp(self, ts):
            self.next_ts = ts

        def __call__(self, endpoint, data):
            if self.next_ts is None:
                raise AssertionError("Timestamp must be set before logging")
            entry = {"endpoint": endpoint, "data": data}
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(f"{self.next_ts} {json.dumps(entry)}\n")
            self.next_ts = None

    recorder = Recorder(log_path)
    monkeypatch.setattr(app, "log_api_data", recorder)

    def _fmt(ts):
        return ts.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]

    ts_start = datetime(2024, 3, 1, 22, 0, 0, tzinfo=app.LOCAL_TZ)
    ts_offline = datetime(2024, 3, 1, 23, 30, 0, tzinfo=app.LOCAL_TZ)
    ts_end = datetime(2024, 3, 2, 1, 10, 0, tzinfo=app.LOCAL_TZ)

    start_payload = {
        "id_s": "veh",
        "drive_state": {"shift_state": "P"},
        "charge_state": {
            "battery_level": 80,
            "ideal_battery_range": 240,
            "charging_state": "Disconnected",
        },
    }
    end_payload = {
        "id_s": "veh",
        "drive_state": {"shift_state": "P"},
        "charge_state": {
            "battery_level": 79,
            "ideal_battery_range": 237,
            "charging_state": "Disconnected",
        },
    }

    recorder.set_timestamp(_fmt(ts_start))
    app.log_api_data("get_vehicle_data", start_payload)

    recorder.set_timestamp(_fmt(ts_offline))
    app.get_vehicle_data(vehicle_id="veh", state="offline")

    recorder.set_timestamp(_fmt(ts_end))
    app.log_api_data("get_vehicle_data", end_payload)

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert any("\"state\": \"offline\"" in line for line in lines)

    result = app._compute_parking_losses(str(log_path))
    assert "2024-03-01" in result
    assert "2024-03-02" in result

    day_one = result["2024-03-01"]
    day_two = result["2024-03-02"]

    drop_km = 3 * app.MILES_TO_KM
    total_drop_pct = 1.0
    total_seconds = (ts_end - ts_start).total_seconds()
    midnight = datetime(2024, 3, 2, 0, 0, 0, tzinfo=app.LOCAL_TZ)
    before_midnight = max((midnight - ts_start).total_seconds(), 0.0)
    after_midnight = max(total_seconds - before_midnight, 0.0)

    expected_first_pct = total_drop_pct * before_midnight / total_seconds
    expected_second_pct = total_drop_pct * after_midnight / total_seconds
    expected_first_km = drop_km * before_midnight / total_seconds
    expected_second_km = drop_km * after_midnight / total_seconds

    assert day_one["energy_pct"] == pytest.approx(expected_first_pct)
    assert day_two["energy_pct"] == pytest.approx(expected_second_pct)
    assert day_one["km"] == pytest.approx(expected_first_km)
    assert day_two["km"] == pytest.approx(expected_second_km)


def test_offline_entry_without_charge_data_preserves_session_start(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_start = datetime(2024, 1, 1, 22, 30, 0, tzinfo=app.LOCAL_TZ)
    ts_offline = datetime(2024, 1, 1, 23, 50, 0, tzinfo=app.LOCAL_TZ)
    ts_end = datetime(2024, 1, 2, 1, 10, 0, tzinfo=app.LOCAL_TZ)

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
                "state": "offline",
                "drive_state": {"shift_state": None},
            },
        },
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": "P"},
                "charge_state": {
                    "battery_level": 79,
                    "ideal_battery_range": 207,
                    "charging_state": "Disconnected",
                },
            },
        },
    ]

    log_path = tmp_path / "api.log"
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(_log_line(ts_start, entries[0]))
        handle.write(_log_line(ts_offline, entries[1]))
        handle.write(_log_line(ts_end, entries[2]))

    result = app._compute_parking_losses(str(log_path))

    assert "2024-01-01" in result
    assert "2024-01-02" in result

    total_drop_pct = 1.0
    total_drop_miles = 3.0

    total_seconds = (ts_end - ts_start).total_seconds()
    midnight = datetime(2024, 1, 2, 0, 0, 0, tzinfo=app.LOCAL_TZ)
    before_midnight = max((midnight - ts_start).total_seconds(), 0.0)
    after_midnight = max(total_seconds - before_midnight, 0.0)

    expected_first_pct = total_drop_pct * before_midnight / total_seconds
    expected_second_pct = total_drop_pct * after_midnight / total_seconds
    expected_first_km = total_drop_miles * app.MILES_TO_KM * before_midnight / total_seconds
    expected_second_km = total_drop_miles * app.MILES_TO_KM * after_midnight / total_seconds

    day_one = result["2024-01-01"]
    day_two = result["2024-01-02"]

    assert day_one["energy_pct"] == pytest.approx(expected_first_pct)
    assert day_two["energy_pct"] == pytest.approx(expected_second_pct)
    assert day_one["km"] == pytest.approx(expected_first_km)
    assert day_two["km"] == pytest.approx(expected_second_km)


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


def test_compute_parking_losses_excludes_drive_losses(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_base = datetime(2024, 7, 1, 9, 0, 0, tzinfo=app.LOCAL_TZ)
    entries = [
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": "D"},
                "charge_state": {
                    "battery_level": 80,
                    "ideal_battery_range": 300,
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
                    "battery_level": 69,
                    "ideal_battery_range": 270,
                    "charging_state": "Disconnected",
                },
            },
        },
    ]

    log_path = tmp_path / "api.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_log_line(ts_base.replace(hour=9 + idx), payload))

    result = app._compute_parking_losses(str(log_path))
    assert result == {}


def test_compute_parking_losses_counts_drive_transition_losses(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_base = datetime(2024, 7, 1, 9, 0, 0, tzinfo=app.LOCAL_TZ)
    entries = [
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": "P"},
                "charge_state": {
                    "battery_level": 80,
                    "ideal_battery_range": 300,
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
                    "ideal_battery_range": 294,
                    "charging_state": "Disconnected",
                },
            },
        },
    ]

    log_path = tmp_path / "api.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_log_line(ts_base.replace(hour=9 + idx), payload))

    result = app._compute_parking_losses(str(log_path))
    assert "2024-07-01" in result
    day = result["2024-07-01"]
    assert day["energy_pct"] == pytest.approx(2.0)
    assert day["km"] == pytest.approx(6 * app.MILES_TO_KM)


def test_compute_parking_losses_logs_losses(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_base = datetime(2024, 8, 1, 10, 0, 0, tzinfo=app.LOCAL_TZ)
    entries = [
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": "P"},
                "charge_state": {
                    "battery_level": 60,
                    "ideal_battery_range": 200,
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
                    "battery_level": 59,
                    "ideal_battery_range": 198,
                    "charging_state": "Disconnected",
                },
            },
        },
    ]

    log_path = tmp_path / "api.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_log_line(ts_base.replace(minute=idx * 30), payload))

    result = app._compute_parking_losses(str(log_path))
    assert "2024-08-01" in result

    park_log = tmp_path / "park-loss.log"
    assert park_log.exists()
    lines = park_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["energy_pct"] == pytest.approx(1.0)
    assert record["range_km"] == pytest.approx(2 * app.MILES_TO_KM)


def test_compute_parking_losses_logs_state_context(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_base = datetime(2024, 9, 1, 1, 0, 0, tzinfo=app.LOCAL_TZ)
    entries = [
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "state": "offline",
                "drive_state": {"shift_state": "P"},
                "charge_state": {
                    "battery_level": 70,
                    "ideal_battery_range": 210,
                    "charging_state": "Disconnected",
                },
            },
        },
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "state": "asleep",
                "drive_state": {"shift_state": "P"},
                "charge_state": {
                    "battery_level": 68,
                    "ideal_battery_range": 204,
                    "charging_state": "Disconnected",
                },
            },
        },
    ]

    log_path = tmp_path / "api.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_log_line(ts_base.replace(minute=idx * 30), payload))

    result = app._compute_parking_losses(str(log_path))
    assert "2024-09-01" in result

    park_log = tmp_path / "park-loss.log"
    assert park_log.exists()
    lines = park_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["context"] == "asleep"


def test_compute_parking_losses_uses_battery_range_fallback(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_base = datetime(2024, 6, 1, 7, 0, 0, tzinfo=app.LOCAL_TZ)
    entries = [
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": "P"},
                "charge_state": {
                    "battery_level": 65,
                    "battery_range": 180,
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
                    "battery_level": 64,
                    "battery_range": 178,
                    "charging_state": "Disconnected",
                },
            },
        },
    ]

    log_path = tmp_path / "api.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_log_line(ts_base.replace(hour=7 + idx * 3), payload))

    result = app._compute_parking_losses(str(log_path))
    assert "2024-06-01" in result
    day = result["2024-06-01"]
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


def test_compute_parking_losses_requires_explicit_park_start(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_base = datetime(2024, 4, 1, 12, 0, 0, tzinfo=app.LOCAL_TZ)
    entries = [
        {
            "endpoint": "get_vehicle_data",
            "data": {
                "id_s": "veh",
                "drive_state": {"shift_state": None},
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
    ]

    log_path = tmp_path / "api.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_log_line(ts_base.replace(hour=12 + idx), payload))

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
