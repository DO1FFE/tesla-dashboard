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
