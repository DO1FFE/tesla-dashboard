import logging
import pathlib
import sys
from datetime import datetime, timedelta

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import app


def test_log_energy_uses_provided_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    old_handlers = list(app.energy_logger.handlers)
    for handler in old_handlers:
        app.energy_logger.removeHandler(handler)

    energy_file = tmp_path / "energy.log"
    handler = logging.FileHandler(energy_file, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    app.energy_logger.addHandler(handler)
    app._recently_logged_sessions.clear()

    try:
        ts = datetime(2024, 1, 1, 23, 30, tzinfo=app.LOCAL_TZ)
        app._log_energy("veh", 12.5, timestamp=ts)
        handler.flush()
    finally:
        app.energy_logger.removeHandler(handler)
        handler.close()
        for original in old_handlers:
            app.energy_logger.addHandler(original)

    content = energy_file.read_text(encoding="utf-8").strip()
    assert content.startswith("2024-01-01 23:30:00")


def test_log_energy_prevents_follow_up_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    old_handlers = list(app.energy_logger.handlers)
    for handler in old_handlers:
        app.energy_logger.removeHandler(handler)

    energy_file = tmp_path / "energy.log"
    handler = logging.FileHandler(energy_file, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    app.energy_logger.addHandler(handler)
    app._recently_logged_sessions.clear()

    try:
        ts = datetime(2024, 1, 5, 21, 0, tzinfo=app.LOCAL_TZ)
        app._log_energy("veh", 15.0, timestamp=ts)

        earlier = ts - timedelta(days=1)
        app._log_energy("veh", 18.0, timestamp=earlier)
        handler.flush()
    finally:
        app.energy_logger.removeHandler(handler)
        handler.close()
        for original in old_handlers:
            app.energy_logger.addHandler(original)

    lines = [line for line in energy_file.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
    assert '"added_energy": 15.0' in lines[0]


def test_session_start_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    vehicle_id = "veh"

    app._clear_session_start(vehicle_id)

    start = datetime(2024, 1, 2, 21, 15, tzinfo=app.LOCAL_TZ)
    app._save_session_start(vehicle_id, start)

    loaded = app._load_session_start(vehicle_id)
    assert loaded is not None
    assert loaded.isoformat() == start.isoformat()

    app._clear_session_start(vehicle_id)
    assert app._load_session_start(vehicle_id) is None


def test_clear_session_allows_follow_up_logging(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    old_handlers = list(app.energy_logger.handlers)
    for handler in old_handlers:
        app.energy_logger.removeHandler(handler)

    energy_file = tmp_path / "energy.log"
    handler = logging.FileHandler(energy_file, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    app.energy_logger.addHandler(handler)
    app._recently_logged_sessions.clear()

    vehicle_id = "veh"

    try:
        first_ts = datetime(2024, 1, 10, 10, 0, tzinfo=app.LOCAL_TZ)
        second_ts = first_ts + timedelta(days=1)

        app._log_energy(vehicle_id, 8.5, timestamp=first_ts)
        handler.flush()

        app._clear_session_start(vehicle_id)

        app._log_energy(vehicle_id, 12.0, timestamp=second_ts)
        handler.flush()
    finally:
        app.energy_logger.removeHandler(handler)
        handler.close()
        for original in old_handlers:
            app.energy_logger.addHandler(original)

    lines = [line for line in energy_file.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 2
    assert '"added_energy": 8.5' in lines[0]
    assert '"added_energy": 12.0' in lines[1]


def test_log_energy_updates_running_session(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    old_handlers = list(app.energy_logger.handlers)
    for handler in old_handlers:
        app.energy_logger.removeHandler(handler)

    energy_file = tmp_path / "energy.log"
    handler = logging.FileHandler(energy_file, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    app.energy_logger.addHandler(handler)
    app._recently_logged_sessions.clear()

    vehicle_id = "veh"

    try:
        start_ts = datetime(2024, 2, 5, 19, 0, tzinfo=app.LOCAL_TZ)

        app._log_energy(vehicle_id, 6.0, timestamp=start_ts)
        app._log_energy(vehicle_id, 8.0, timestamp=start_ts)
        handler.flush()
    finally:
        app.energy_logger.removeHandler(handler)
        handler.close()
        for original in old_handlers:
            app.energy_logger.addHandler(original)

    lines = [line for line in energy_file.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 2
    assert '"added_energy": 8.0' in lines[-1]

    stats = app._compute_energy_stats(str(energy_file))
    assert stats == {start_ts.date().isoformat(): 8.0}


def test_compute_energy_stats_respects_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    energy_file = tmp_path / "energy.log"
    energy_file.write_text(
        '2024-02-25 08:00:00 {"vehicle_id": "veh", "added_energy": 12.3}\n',
        encoding="utf-8",
    )

    stats = app._compute_energy_stats()
    assert stats == {"2024-02-25": 12.3}


def test_compute_energy_stats_assigns_session_to_last_day(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    energy_file = tmp_path / "energy.log"
    energy_file.write_text(
        "\n".join(
            [
                '2024-03-01 23:45:00 {"vehicle_id": "veh", "added_energy": 4.0}',
                '2024-03-02 00:15:00 {"vehicle_id": "veh", "added_energy": 6.5}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    stats = app._compute_energy_stats()
    assert stats == {"2024-03-01": 4.0, "2024-03-02": 6.5}


def test_compute_energy_stats_sums_same_day_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    energy_file = tmp_path / "energy.log"
    energy_file.write_text(
        "\n".join(
            [
                '2024-04-01 08:00:00 {"vehicle_id": "veh", "added_energy": 4.0}',
                '2024-04-01 12:30:00 {"vehicle_id": "veh", "added_energy": 6.5}',
                '2024-04-01 18:00:00 {"vehicle_id": "veh2", "added_energy": 3.5}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    stats = app._compute_energy_stats()
    assert stats == {"2024-04-01": 14.0}


def test_compute_energy_stats_uses_latest_value_per_session(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    energy_file = tmp_path / "energy.log"
    energy_file.write_text(
        "\n".join(
            [
                '2024-05-01 10:00:00 {"vehicle_id": "veh", "added_energy": 5.0}',
                '2024-05-01 10:00:00 {"vehicle_id": "veh", "added_energy": 6.5}',
                '2024-05-01 21:15:00 {"vehicle_id": "veh", "added_energy": 4.0}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    stats = app._compute_energy_stats()
    assert stats == {"2024-05-01": 10.5}
