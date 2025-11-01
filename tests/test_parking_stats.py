import json
import os
from datetime import datetime, timedelta

import pytest


def _park_line(ts, payload):
    return f"{ts.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} {json.dumps(payload)}\n"


def _api_log_line(ts, payload):
    body = {"endpoint": "get_vehicle_data", "data": payload}
    return f"{ts.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} {json.dumps(body)}\n"


@pytest.fixture
def rotated_parking_logs(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    start_ts = datetime(2024, 6, 1, 20, 0, 0, tzinfo=app.LOCAL_TZ)
    end_ts = datetime(2024, 6, 1, 22, 0, 0, tzinfo=app.LOCAL_TZ)
    session_id = "sess-veh-1"

    start_payload = {
        "vehicle_id": "veh",
        "battery_pct": 80.0,
        "range_km": round(200 * app.MILES_TO_KM, 6),
        "state": "parked",
        "session": session_id,
    }
    end_payload = {
        "vehicle_id": "veh",
        "battery_pct": 79.0,
        "range_km": round(198 * app.MILES_TO_KM, 6),
        "state": "parked",
        "session": session_id,
    }

    rotated_path = tmp_path / "park-ui.log.2024-06-01T200000"
    with rotated_path.open("w", encoding="utf-8") as handle:
        handle.write(_park_line(start_ts, start_payload))
    os.utime(rotated_path, (start_ts.timestamp(), start_ts.timestamp()))

    main_path = tmp_path / "park-ui.log"
    with main_path.open("w", encoding="utf-8") as handle:
        handle.write(_park_line(end_ts, end_payload))
    os.utime(main_path, (end_ts.timestamp(), end_ts.timestamp()))

    return {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "data_dir": tmp_path,
    }


def test_log_dashboard_parking_sample_deduplicates(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    app._last_parking_samples.clear()
    app._active_parking_sessions.clear()

    ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=app.LOCAL_TZ)
    session_id = "veh-dedupe"

    first = app._log_dashboard_parking_sample(
        "veh",
        timestamp=ts,
        battery_pct=80.0,
        range_km=round(150 * app.MILES_TO_KM, 6),
        state="parked",
        session=session_id,
    )
    assert first is True

    duplicate = app._log_dashboard_parking_sample(
        "veh",
        timestamp=ts + timedelta(minutes=5),
        battery_pct=80.0,
        range_km=round(150 * app.MILES_TO_KM, 6),
        state="parked",
        session=session_id,
    )
    assert duplicate is False

    state_change = app._log_dashboard_parking_sample(
        "veh",
        timestamp=ts + timedelta(minutes=10),
        battery_pct=80.0,
        range_km=round(150 * app.MILES_TO_KM, 6),
        state="offline",
        session=session_id,
    )
    assert state_change is True

    log_path = tmp_path / app.PARK_UI_LOG
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_compute_parking_losses_processes_date_rotated_logs(rotated_parking_logs):
    import app

    result = app._compute_parking_losses()

    day = rotated_parking_logs["start_ts"].date().isoformat()
    assert day in result

    entry = result[day]
    assert entry["energy_pct"] == pytest.approx(1.0)
    assert entry["km"] == pytest.approx(2 * app.MILES_TO_KM)

    log_path = rotated_parking_logs["data_dir"] / "park-loss.log"
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
    session_id = "veh-midnight"
    entries = [
        {
            "vehicle_id": "veh",
            "battery_pct": 80.0,
            "range_km": round(210 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": session_id,
        },
        {
            "vehicle_id": "veh",
            "battery_pct": 77.0,
            "range_km": round(201 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": session_id,
        },
    ]

    log_path = tmp_path / "park-ui.log"
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(_park_line(ts_start, entries[0]))
        handle.write(_park_line(ts_start.replace(day=2, hour=2), entries[1]))

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
    ts_start = datetime(2024, 3, 1, 22, 0, 0, tzinfo=app.LOCAL_TZ)
    ts_offline = datetime(2024, 3, 1, 23, 30, 0, tzinfo=app.LOCAL_TZ)
    ts_end = datetime(2024, 3, 2, 1, 10, 0, tzinfo=app.LOCAL_TZ)

    session_id = "veh-offline"
    entries = [
        {
            "vehicle_id": "veh",
            "battery_pct": 80.0,
            "range_km": round(240 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": session_id,
        },
        {
            "vehicle_id": "veh",
            "battery_pct": None,
            "range_km": None,
            "state": "offline",
            "session": session_id,
        },
        {
            "vehicle_id": "veh",
            "battery_pct": 79.0,
            "range_km": round(237 * app.MILES_TO_KM, 6),
            "state": "offline",
            "session": session_id,
        },
    ]

    log_path = tmp_path / "park-ui.log"
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(_park_line(ts_start, entries[0]))
        handle.write(_park_line(ts_offline, entries[1]))
        handle.write(_park_line(ts_end, entries[2]))

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


def test_record_dashboard_parking_state_accepts_blank_shift(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    app._active_parking_sessions.clear()
    app._last_parking_samples.clear()

    calls = []

    def fake_log(vehicle_id, **kwargs):
        calls.append({"vehicle_id": vehicle_id, **kwargs})
        return True

    monkeypatch.setattr(app, "_log_dashboard_parking_sample", fake_log)

    base_data = {
        "drive_state": {"shift_state": "P"},
        "charge_state": {
            "battery_level": 80,
            "ideal_battery_range": 200,
            "charging_state": "Disconnected",
        },
        "state": "parked",
    }

    app._record_dashboard_parking_state("veh", base_data)
    assert len(calls) == 1

    blank_shift = {
        "drive_state": {"shift_state": " "},
        "charge_state": {
            "battery_level": 79,
            "ideal_battery_range": 198,
            "charging_state": "Disconnected",
        },
        "state": "offline",
    }

    app._record_dashboard_parking_state("veh", blank_shift)
    assert len(calls) == 2
    assert calls[-1]["battery_pct"] == pytest.approx(79.0)
    assert calls[-1]["range_km"] == pytest.approx(198 * app.MILES_TO_KM)


def test_offline_entry_without_charge_data_preserves_session_start(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_start = datetime(2024, 1, 1, 22, 30, 0, tzinfo=app.LOCAL_TZ)
    ts_offline = datetime(2024, 1, 1, 23, 50, 0, tzinfo=app.LOCAL_TZ)
    ts_end = datetime(2024, 1, 2, 1, 10, 0, tzinfo=app.LOCAL_TZ)

    entries = [
        {
            "vehicle_id": "veh",
            "battery_pct": 80.0,
            "range_km": round(210 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-offline-gap",
        },
        {
            "vehicle_id": "veh",
            "battery_pct": None,
            "range_km": None,
            "state": "offline",
            "session": "veh-offline-gap",
        },
        {
            "vehicle_id": "veh",
            "battery_pct": 79.0,
            "range_km": round(207 * app.MILES_TO_KM, 6),
            "state": "offline",
            "session": "veh-offline-gap",
        },
    ]

    log_path = tmp_path / "park-ui.log"
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(_park_line(ts_start, entries[0]))
        handle.write(_park_line(ts_offline, entries[1]))
        handle.write(_park_line(ts_end, entries[2]))

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
            "vehicle_id": "veh",
            "battery_pct": 80.0,
            "range_km": round(200 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-tracking",
        },
        {
            "vehicle_id": "veh",
            "battery_pct": 79.0,
            "range_km": round(198 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-tracking",
        },
        {
            "vehicle_id": "veh",
            "battery_pct": 78.0,
            "range_km": round(195 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-tracking",
        },
    ]

    log_path = tmp_path / "park-ui.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_park_line(ts_base.replace(hour=8 + idx * 2), payload))

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
            "vehicle_id": "veh",
            "battery_pct": 70.0,
            "range_km": round(150 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-est",
        },
        {
            "vehicle_id": "veh",
            "battery_pct": 69.0,
            "range_km": round(148 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-est",
        },
    ]

    log_path = tmp_path / "park-ui.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_park_line(ts_base.replace(hour=6 + idx), payload))

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
            "vehicle_id": "veh",
            "battery_pct": 80.0,
            "range_km": round(300 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-drive-1",
        },
        {
            "vehicle_id": "veh",
            "battery_pct": 69.0,
            "range_km": round(270 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-drive-2",
        },
    ]

    log_path = tmp_path / "park-ui.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_park_line(ts_base.replace(hour=9 + idx), payload))

    result = app._compute_parking_losses(str(log_path))
    assert result == {}


def test_compute_parking_losses_counts_drive_transition_losses(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_base = datetime(2024, 7, 1, 9, 0, 0, tzinfo=app.LOCAL_TZ)
    entries = [
        {
            "vehicle_id": "veh",
            "battery_pct": 80.0,
            "range_km": round(300 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-drive-transition",
        },
        {
            "vehicle_id": "veh",
            "battery_pct": 78.0,
            "range_km": round(294 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-drive-transition",
        },
    ]

    log_path = tmp_path / "park-ui.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_park_line(ts_base.replace(hour=9 + idx), payload))

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
            "vehicle_id": "veh",
            "battery_pct": 60.0,
            "range_km": round(200 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-log",
        },
        {
            "vehicle_id": "veh",
            "battery_pct": 59.0,
            "range_km": round(198 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-log",
        },
    ]

    log_path = tmp_path / "park-ui.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_park_line(ts_base.replace(minute=idx * 30), payload))

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
            "vehicle_id": "veh",
            "battery_pct": 70.0,
            "range_km": round(210 * app.MILES_TO_KM, 6),
            "state": "offline",
            "session": "veh-state",
        },
        {
            "vehicle_id": "veh",
            "battery_pct": 68.0,
            "range_km": round(204 * app.MILES_TO_KM, 6),
            "state": "asleep",
            "session": "veh-state",
        },
    ]

    log_path = tmp_path / "park-ui.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_park_line(ts_base.replace(minute=idx * 30), payload))

    result = app._compute_parking_losses(str(log_path))
    assert "2024-09-01" in result

    park_log = tmp_path / "park-loss.log"
    assert park_log.exists()
    lines = park_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["context"] == "asleep"


def test_compute_parking_losses_handles_blank_shift_in_legacy_log(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_start = datetime(2024, 5, 1, 8, 0, 0, tzinfo=app.LOCAL_TZ)
    ts_end = ts_start.replace(hour=10)

    first_payload = {
        "id_s": "veh",
        "charge_state": {
            "battery_level": 80,
            "ideal_battery_range": 200,
            "charging_state": "Disconnected",
        },
        "drive_state": {"shift_state": "P"},
        "state": "parked",
    }

    second_payload = {
        "id_s": "veh",
        "charge_state": {
            "battery_level": 79,
            "ideal_battery_range": 198,
            "charging_state": "Disconnected",
        },
        "drive_state": {"shift_state": ""},
        "state": "offline",
    }

    log_path = tmp_path / "api.log"
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(_api_log_line(ts_start, first_payload))
        handle.write(_api_log_line(ts_end, second_payload))

    result = app._compute_parking_losses(str(log_path))
    day = ts_start.date().isoformat()
    assert day in result

    entry = result[day]
    assert entry["energy_pct"] == pytest.approx(1.0)
    assert entry["km"] == pytest.approx(2 * app.MILES_TO_KM)


def test_compute_parking_losses_uses_battery_range_fallback(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    ts_base = datetime(2024, 6, 1, 7, 0, 0, tzinfo=app.LOCAL_TZ)
    entries = [
        {
            "vehicle_id": "veh",
            "battery_pct": 65.0,
            "range_km": round(180 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-battery",
        },
        {
            "vehicle_id": "veh",
            "battery_pct": 64.0,
            "range_km": round(178 * app.MILES_TO_KM, 6),
            "state": "parked",
            "session": "veh-battery",
        },
    ]

    log_path = tmp_path / "park-ui.log"
    with log_path.open("w", encoding="utf-8") as handle:
        for idx, payload in enumerate(entries):
            handle.write(_park_line(ts_base.replace(hour=7 + idx * 3), payload))

    result = app._compute_parking_losses(str(log_path))
    assert "2024-06-01" in result
    day = result["2024-06-01"]
    assert day["energy_pct"] == pytest.approx(1.0)
    assert day["km"] == pytest.approx(2 * app.MILES_TO_KM)


def test_compute_parking_losses_ignores_charging_sessions(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    app._active_parking_sessions.clear()

    charging_data = {
        "drive_state": {"shift_state": "P"},
        "charge_state": {
            "battery_level": 75,
            "ideal_battery_range": 190,
            "charging_state": "Stopped",
        },
    }

    app._record_dashboard_parking_state("veh", charging_data)

    log_path = tmp_path / app.PARK_UI_LOG
    if log_path.exists():
        assert log_path.read_text(encoding="utf-8").strip() == ""

    result = app._compute_parking_losses()
    assert result == {}


def test_compute_parking_losses_requires_explicit_park_start(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    app._active_parking_sessions.clear()

    data = {
        "drive_state": {"shift_state": None},
        "charge_state": {
            "battery_level": 80,
            "ideal_battery_range": 200,
            "charging_state": "Disconnected",
        },
    }
    app._record_dashboard_parking_state("veh", data)

    data_drop = {
        "drive_state": {"shift_state": None},
        "charge_state": {
            "battery_level": 79,
            "ideal_battery_range": 198,
            "charging_state": "Disconnected",
        },
    }
    app._record_dashboard_parking_state("veh", data_drop)

    log_path = tmp_path / app.PARK_UI_LOG
    if log_path.exists():
        assert log_path.read_text(encoding="utf-8").strip() == ""

    result = app._compute_parking_losses()
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
