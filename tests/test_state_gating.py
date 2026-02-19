import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


def _setze_neutrale_ladehilfen(monkeypatch):
    monkeypatch.setattr(app, "_load_last_energy", lambda vehicle_id: None)
    monkeypatch.setattr(app, "_load_last_charge_duration", lambda vehicle_id: None)
    monkeypatch.setattr(app, "_load_last_charge_added_percent", lambda vehicle_id: None)
    monkeypatch.setattr(app, "_load_last_charge_start_soc", lambda vehicle_id: None)
    monkeypatch.setattr(app, "_load_last_charge_end_soc", lambda vehicle_id: None)
    monkeypatch.setattr(app, "_load_session_start", lambda vehicle_id: None)
    monkeypatch.setattr(app, "_load_session_start_soc", lambda vehicle_id: None)
    monkeypatch.setattr(app, "_load_session_last_soc", lambda vehicle_id: None)
    monkeypatch.setattr(app, "_save_cached", lambda vehicle_id, data: None)
    monkeypatch.setattr(app, "_record_dashboard_parking_state", lambda vehicle_id, data: None)


def test_fetch_data_once_offline_nutzt_nur_cache(monkeypatch):
    aufrufe_get_vehicle_data = []
    cache_daten = {
        "state": "online",
        "charge_state": {},
        "drive_state": {},
    }

    _setze_neutrale_ladehilfen(monkeypatch)
    monkeypatch.setattr(app, "get_vehicle_state", lambda vid: {"state": "offline"})
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: dict(cache_daten))

    def _fake_get_vehicle_data(vid, state=None):
        aufrufe_get_vehicle_data.append((vid, state))
        return {"state": "online", "charge_state": {}, "drive_state": {}}

    monkeypatch.setattr(app, "get_vehicle_data", _fake_get_vehicle_data)

    daten = app._fetch_data_once("veh-offline")

    assert aufrufe_get_vehicle_data == []
    assert daten["state"] == "offline"
    assert daten["_live"] is False


def test_fetch_data_once_asleep_nutzt_nur_cache(monkeypatch):
    aufrufe_get_vehicle_data = []

    _setze_neutrale_ladehilfen(monkeypatch)
    monkeypatch.setattr(app, "get_vehicle_state", lambda vid: {"state": "asleep"})
    monkeypatch.setattr(
        app,
        "_load_cached",
        lambda vehicle_id: {"state": "online", "charge_state": {}, "drive_state": {}},
    )

    def _fake_get_vehicle_data(vid, state=None):
        aufrufe_get_vehicle_data.append((vid, state))
        return {"state": "online", "charge_state": {}, "drive_state": {}}

    monkeypatch.setattr(app, "get_vehicle_data", _fake_get_vehicle_data)

    daten = app._fetch_data_once("veh-asleep")

    assert aufrufe_get_vehicle_data == []
    assert daten["state"] == "asleep"
    assert daten["_live"] is False


def test_fetch_data_once_online_ruft_live_abruf_auf_und_nutzt_fallback(monkeypatch):
    aufrufe_get_vehicle_data = []

    _setze_neutrale_ladehilfen(monkeypatch)
    monkeypatch.setattr(app, "get_vehicle_state", lambda vid: {"state": "online"})
    monkeypatch.setattr(
        app,
        "_load_cached",
        lambda vehicle_id: {
            "state": "offline",
            "charge_state": {},
            "drive_state": {},
            "source": "cache",
        },
    )

    def _fake_get_vehicle_data(vid, state=None):
        aufrufe_get_vehicle_data.append((vid, state))
        return {"error": "api-unavailable"}

    monkeypatch.setattr(app, "get_vehicle_data", _fake_get_vehicle_data)

    daten = app._fetch_data_once("veh-online")

    assert aufrufe_get_vehicle_data == [("veh-online", "online")]
    assert daten["state"] == "online"
    assert daten["source"] == "cache"
    assert daten["_live"] is False
