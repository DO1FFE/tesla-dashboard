import logging
import os
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

    lines = [
        line
        for line in energy_file.read_text(encoding="utf-8").splitlines()
        if line
    ]
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


def test_save_session_start_handles_naive_datetime(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    app._charging_session_start.clear()
    app._recently_logged_sessions.clear()

    vehicle_id = "veh"
    naive_start = datetime(2024, 1, 5, 8, 30)

    app._save_session_start(vehicle_id, naive_start)

    loaded = app._load_session_start(vehicle_id)
    assert loaded is not None
    assert loaded.tzinfo == app.LOCAL_TZ
    assert loaded.replace(tzinfo=None) == naive_start


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


def test_log_energy_allows_new_session_with_same_amount(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    old_handlers = list(app.energy_logger.handlers)
    for handler in old_handlers:
        app.energy_logger.removeHandler(handler)

    energy_file = tmp_path / "energy.log"
    handler = logging.FileHandler(energy_file, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    app.energy_logger.addHandler(handler)
    app._recently_logged_sessions.clear()
    app._last_energy_markers.clear()

    vehicle_id = "veh"

    try:
        first_ts = datetime(2024, 2, 6, 10, 0, tzinfo=app.LOCAL_TZ)
        second_ts = first_ts + timedelta(minutes=20)

        app._log_energy(vehicle_id, 5.0, timestamp=first_ts)
        handler.flush()
        app._save_last_energy(vehicle_id, 5.0)

        app._clear_session_start(vehicle_id)

        app._log_energy(vehicle_id, 5.0, timestamp=second_ts)
        handler.flush()
    finally:
        app.energy_logger.removeHandler(handler)
        handler.close()
        for original in old_handlers:
            app.energy_logger.addHandler(original)

    lines = [line for line in energy_file.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 2
    assert '"added_energy": 5.0' in lines[0]
    assert '"added_energy": 5.0' in lines[1]


def test_fetch_data_logs_session_and_updates_last_energy(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    os.makedirs(app.DATA_DIR, exist_ok=True)

    old_handlers = list(app.energy_logger.handlers)
    for handler in old_handlers:
        app.energy_logger.removeHandler(handler)

    energy_file = tmp_path / "energy.log"
    handler = logging.FileHandler(energy_file, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    app.energy_logger.addHandler(handler)

    app._charging_session_start.clear()
    app._recently_logged_sessions.clear()

    vehicle_id = "veh"

    state_responses = iter([
        {"state": "online"},
        {"state": "online"},
    ])
    data_responses = iter(
        [
            {
                "state": "online",
                "charge_state": {
                    "charging_state": "Charging",
                    "charge_energy_added": 7.25,
                },
                "drive_state": {},
            },
            {
                "state": "online",
                "charge_state": {
                    "charging_state": "Complete",
                    "charge_energy_added": 7.25,
                },
                "drive_state": {},
            },
        ]
    )

    monkeypatch.setattr(app, "get_vehicle_state", lambda vid: next(state_responses))
    monkeypatch.setattr(
        app, "get_vehicle_data", lambda vid, state=None: next(data_responses)
    )
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: None)
    monkeypatch.setattr(app, "_save_cached", lambda vehicle_id, data: None)

    try:
        app._fetch_data_once(vehicle_id)
        app._fetch_data_once(vehicle_id)
        handler.flush()
    finally:
        app.energy_logger.removeHandler(handler)
        handler.close()
        for original in old_handlers:
            app.energy_logger.addHandler(original)

    energy_lines = [
        line for line in energy_file.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(energy_lines) == 1
    assert '"added_energy": 7.25' in energy_lines[0]

    last_energy_file = pathlib.Path(app.vehicle_dir(vehicle_id)) / "last_energy.txt"
    assert last_energy_file.exists()
    assert last_energy_file.read_text(encoding="utf-8").strip() == "7.25"


def test_fetch_data_does_not_duplicate_last_session_after_restart(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    os.makedirs(app.DATA_DIR, exist_ok=True)

    old_handlers = list(app.energy_logger.handlers)
    for handler in old_handlers:
        app.energy_logger.removeHandler(handler)

    energy_file = tmp_path / "energy.log"
    handler = logging.FileHandler(energy_file, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    app.energy_logger.addHandler(handler)

    app._charging_session_start.clear()
    app._recently_logged_sessions.clear()

    vehicle_id = "veh"

    state_responses = [
        {"state": "online"},
        {"state": "online"},
        {"state": "online"},
    ]
    data_responses = [
        {
            "state": "online",
            "charge_state": {
                "charging_state": "Charging",
                "charge_energy_added": 4.5,
            },
            "drive_state": {},
        },
        {
            "state": "online",
            "charge_state": {
                "charging_state": "Complete",
                "charge_energy_added": 4.5,
            },
            "drive_state": {},
        },
        {
            "state": "online",
            "charge_state": {
                "charging_state": "Complete",
                "charge_energy_added": 4.5,
            },
            "drive_state": {},
        },
    ]

    def fake_state(vid):
        return state_responses.pop(0)

    def fake_data(vid, state=None):
        return data_responses.pop(0)

    monkeypatch.setattr(app, "get_vehicle_state", fake_state)
    monkeypatch.setattr(app, "get_vehicle_data", fake_data)
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: None)
    monkeypatch.setattr(app, "_save_cached", lambda vehicle_id, data: None)

    try:
        app._fetch_data_once(vehicle_id)
        app._fetch_data_once(vehicle_id)
        handler.flush()

        app._recently_logged_sessions.clear()
        app._last_energy_markers.clear()

        app._fetch_data_once(vehicle_id)
        handler.flush()
    finally:
        app.energy_logger.removeHandler(handler)
        handler.close()
        for original in old_handlers:
            app.energy_logger.addHandler(original)

    energy_lines = [
        line for line in energy_file.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(energy_lines) == 1
    assert '"added_energy": 4.5' in energy_lines[0]


def test_fleet_telemetrie_traegt_beendete_ladung_nach(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    os.makedirs(app.DATA_DIR, exist_ok=True)

    vehicle_id = "fleet_nachtrag"
    fahrzeug_dir = pathlib.Path(app.vehicle_dir(vehicle_id))
    (fahrzeug_dir / "last_energy.txt").write_text("16.04", encoding="utf-8")

    old_handlers = list(app.energy_logger.handlers)
    for handler in old_handlers:
        app.energy_logger.removeHandler(handler)

    logger = logging.getLogger(f"energy_logger_{app._vehicle_key(vehicle_id)}")
    alte_logger_handler = list(logger.handlers)
    for handler in alte_logger_handler:
        logger.removeHandler(handler)

    app._charging_session_start.clear()
    app._charging_session_start_soc.clear()
    app._charging_session_last_soc.clear()
    app._recently_logged_sessions.clear()
    app._last_energy_markers.clear()

    daten = {
        "state": "online",
        "charge_state": {
            "charging_state": "Disconnected",
            "charge_energy_added": 30.1,
            "battery_level": 91,
        },
        "drive_state": {},
    }
    cached = {
        "last_charge_energy_added": 30.1,
        "charge_state": {
            "charging_state": "Disconnected",
            "battery_level": 70,
        },
    }

    try:
        app._fleet_telemetrie_ladeinformationen_aktualisieren(
            vehicle_id, daten, cached
        )
        for handler in logger.handlers:
            handler.flush()
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        for handler in alte_logger_handler:
            logger.addHandler(handler)
        for handler in old_handlers:
            app.energy_logger.addHandler(handler)

    energy_file = fahrzeug_dir / "energy.log"
    lines = [
        line
        for line in energy_file.read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert len(lines) == 1
    assert '"added_energy": 30.1' in lines[0]
    assert (fahrzeug_dir / "last_energy.txt").read_text(encoding="utf-8") == "30.1"
    assert daten["last_charge_energy_added"] == 30.1
    assert daten["charge_state"]["last_charge_energy_added"] == 30.1
    assert list(app._compute_energy_stats(vehicle_id=vehicle_id).values()) == [30.1]


def test_fleet_telemetrie_ignoriert_stale_ladeenergie_ohne_soc_anstieg(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    os.makedirs(app.DATA_DIR, exist_ok=True)

    vehicle_id = "fleet_stale_energie"
    fahrzeug_dir = pathlib.Path(app.vehicle_dir(vehicle_id))
    (fahrzeug_dir / "last_energy.txt").write_text("7.53", encoding="utf-8")

    app._charging_session_start.clear()
    app._charging_session_start_soc.clear()
    app._charging_session_last_soc.clear()
    app._recently_logged_sessions.clear()
    app._last_energy_markers.clear()

    daten = {
        "state": "online",
        "charge_state": {
            "charging_state": "Disconnected",
            "charge_energy_added": 27.4,
            "battery_level": 85,
        },
        "drive_state": {},
    }
    cached = {
        "last_charge_energy_added": 7.53,
        "charge_state": {
            "charging_state": "Disconnected",
            "battery_level": 85,
        },
    }

    app._fleet_telemetrie_ladeinformationen_aktualisieren(
        vehicle_id, daten, cached
    )

    energy_file = fahrzeug_dir / "energy.log"
    if energy_file.exists():
        assert energy_file.read_text(encoding="utf-8").strip() == ""
    assert (fahrzeug_dir / "last_energy.txt").read_text(
        encoding="utf-8"
    ) == "7.53"


def test_fleet_telemetrie_schreibt_ladung_nicht_fuer_alias_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    os.makedirs(app.DATA_DIR, exist_ok=True)

    daten = {
        "id_s": "primaer",
        "charge_state": {
            "charging_state": "Disconnected",
            "charge_energy_added": 12.0,
        },
    }

    app._fleet_telemetrie_ladeinformationen_aktualisieren("default", daten, daten)

    assert not (pathlib.Path(app.vehicle_dir("default")) / "energy.log").exists()
    assert "last_charge_energy_added" not in daten


def test_fleet_telemetrie_v2l_oeffnet_keine_ladesitzung(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    vehicle_id = "fleet_v2l"
    alter_start = datetime(2026, 8, 30, 16, 32, tzinfo=app.LOCAL_TZ)
    app._save_session_start(vehicle_id, alter_start)
    app._save_session_start_soc(vehicle_id, 71)

    daten = {
        "id_s": vehicle_id,
        "v2l_active": True,
        "charge_state": {
            "charging_state": "Starting",
            "charger_power": 4.0,
            "charge_energy_added": 0.0,
            "usable_battery_level": 71,
            "pack_power": -4.5,
            "pack_voltage": 380.0,
            "pack_current": -11.84,
            "charge_session_start": alter_start.isoformat(),
            "charge_session_start_soc": 71,
        },
        "drive_state": {"shift_state": "P", "speed": 0},
    }

    app._fleet_telemetrie_ladeinformationen_aktualisieren(vehicle_id, daten)

    assert app._load_session_start(vehicle_id) is None
    assert app._load_session_start_soc(vehicle_id) is None
    assert "charge_session_start" not in daten["charge_state"]
    assert "charge_session_start_soc" not in daten["charge_state"]
    assert not (pathlib.Path(app.vehicle_dir(vehicle_id)) / "energy.log").exists()


def test_fleet_telemetrie_beendet_ladung_bereits_bei_standby(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    vehicle_id = "fleet_standby"
    protokolliert = []
    monkeypatch.setattr(
        app,
        "_log_energy",
        lambda fahrzeug, energie, timestamp=None: (
            protokolliert.append((fahrzeug, energie, timestamp)) or True
        ),
    )
    app._charging_session_start.clear()
    app._charging_session_start_soc.clear()
    app._charging_session_last_soc.clear()
    app._recently_logged_sessions.clear()
    app._last_energy_markers.clear()

    start = {
        "id_s": vehicle_id,
        "charge_state": {
            "charging_state": "Starting",
            "charge_energy_added": 0.0,
            "usable_battery_level": 31,
        },
        "drive_state": {"shift_state": "P", "speed": 0},
    }
    app._fleet_telemetrie_ladeinformationen_aktualisieren(vehicle_id, start)

    ende = {
        "id_s": vehicle_id,
        "charge_state": {
            "charging_state": "Standby",
            "charge_energy_added": 11.2022222222,
            "ac_charge_energy_added": 11.2022222222,
            "dc_charge_energy_added": 10.9188363036,
            "usable_battery_level": 46,
        },
        "drive_state": {"shift_state": "P", "speed": 0},
    }
    app._fleet_telemetrie_ladeinformationen_aktualisieren(
        vehicle_id,
        ende,
        start,
    )

    assert len(protokolliert) == 1
    assert protokolliert[0][0] == vehicle_id
    assert protokolliert[0][1] == 10.9188363036
    assert isinstance(protokolliert[0][2], datetime)
    assert app._load_session_start(vehicle_id) is None
    assert app._load_last_charge_start_soc(vehicle_id) == 31
    assert app._load_last_charge_end_soc(vehicle_id) == 46
    assert app._load_last_charge_added_percent(vehicle_id) == 15


def test_fleet_telemetrie_verwirft_beendete_sitzung_auch_ohne_energie(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    vehicle_id = "fleet_ohne_energie"
    app._save_session_start(
        vehicle_id,
        datetime.now(app.LOCAL_TZ) - timedelta(minutes=5),
    )
    app._save_session_start_soc(vehicle_id, 40)

    daten = {
        "id_s": vehicle_id,
        "charge_state": {
            "charging_state": "Disconnected",
            "usable_battery_level": 42,
            "charge_session_start": "2026-09-01T08:00:00+02:00",
            "charge_session_duration_s": 300,
            "charge_session_start_soc": 40,
            "charge_added_percent": 2,
        },
        "drive_state": {"shift_state": "P", "speed": 0},
    }
    app._fleet_telemetrie_ladeinformationen_aktualisieren(vehicle_id, daten)

    assert app._load_session_start(vehicle_id) is None
    assert app._load_last_charge_start_soc(vehicle_id) == 40
    assert app._load_last_charge_end_soc(vehicle_id) == 42
    assert app._load_last_charge_added_percent(vehicle_id) == 2
    assert "charge_session_start" not in daten["charge_state"]
    assert "charge_session_duration_s" not in daten["charge_state"]
    assert "charge_session_start_soc" not in daten["charge_state"]
    assert "charge_added_percent" not in daten["charge_state"]
    assert not (pathlib.Path(app.vehicle_dir(vehicle_id)) / "energy.log").exists()


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


def test_compute_energy_stats_ersetzt_spaete_kleine_korrektur(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))

    energy_file = tmp_path / "energy.log"
    energy_file.write_text(
        "\n".join(
            [
                '2026-07-06 13:24:32,836 {"vehicle_id": "veh", "added_energy": 31.31305054247334}',
                '2026-07-06 14:09:34,285 {"vehicle_id": "veh", "added_energy": 31.42215524819624}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    stats = app._compute_energy_stats()

    assert stats == {"2026-07-06": 31.422155}
