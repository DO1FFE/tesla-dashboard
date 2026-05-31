import pathlib
import sys
import time

import pytest

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
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "last_vehicle_state", {"veh-offline": "online"})
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


def test_vorklimatisierung_wird_nur_im_stand_angezeigt(monkeypatch):
    monkeypatch.setattr(app, "occupant_present", False)

    assert app._vorklimatisierung_im_stand_erlaubt({
        "state": "online",
        "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
    }) is True
    assert app._vorklimatisierung_im_stand_erlaubt({
        "state": "online",
        "drive_state": {"shift_state": None, "speed": 0, "power": 0},
    }) is True
    assert app._vorklimatisierung_im_stand_erlaubt({
        "state": "online",
        "drive_state": {"shift_state": "D", "speed": 0, "power": 0},
    }) is False
    assert app._vorklimatisierung_im_stand_erlaubt({
        "state": "online",
        "drive_state": {"shift_state": None, "speed": 12, "power": 8},
    }) is False
    assert app._vorklimatisierung_im_stand_erlaubt({
        "state": "online",
        "drive_state": {"shift_state": None, "speed": None, "power": 8},
        "climate_state": {
            "is_climate_on": True,
            "is_preconditioning": True,
        },
    }) is True
    assert app._vorklimatisierung_im_stand_erlaubt({
        "state": "online",
        "drive_state": {"shift_state": None, "speed": None, "power": 8},
        "climate_state": {"is_climate_on": False},
    }) is False
    assert app._vorklimatisierung_im_stand_erlaubt({
        "state": "online",
        "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
        "vehicle_state": {"locked": False},
    }) is False
    assert app._vorklimatisierung_im_stand_erlaubt({
        "state": "online",
        "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
        "vehicle_state": {"fd_window": 1},
    }) is False
    assert app._vorklimatisierung_im_stand_erlaubt({
        "state": "online",
        "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
        "vehicle_state": {"sun_roof_state": "open", "sun_roof_percent_open": 12},
    }) is False
    assert app._vorklimatisierung_im_stand_erlaubt({
        "state": "online",
        "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
        "vehicle_state": {"is_user_present": True},
    }) is False

    monkeypatch.setattr(app, "occupant_present", True)
    assert app._vorklimatisierung_im_stand_erlaubt({
        "state": "online",
        "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
        "vehicle_state": {"is_user_present": False},
    }) is False


def test_api_occupant_blendet_vorklimatisierung_sofort_aus(monkeypatch):
    monkeypatch.setattr(app, "occupant_present", False)
    monkeypatch.setattr(app, "subscribers", {})
    monkeypatch.setattr(app, "latest_data", {
        "default": {
            "state": "online",
            "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
            "vehicle_state": {"locked": True, "is_user_present": False},
            "climate_state": {
                "is_climate_on": True,
                "is_preconditioning": True,
            },
            "preconditioning_display_allowed": True,
        },
    })

    response = app.app.test_client().post("/api/occupant", json={"present": True})

    assert response.status_code == 200
    assert response.get_json()["present"] is True
    assert app.latest_data["default"]["preconditioning_display_allowed"] is False


def test_fetch_data_once_asleep_nutzt_nur_cache(monkeypatch):
    aufrufe_get_vehicle_data = []

    _setze_neutrale_ladehilfen(monkeypatch)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "last_vehicle_state", {"veh-asleep": "offline"})
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


def test_fetch_data_once_asleep_mit_offenem_schiebedach_ruft_keine_vollen_daten_ab(monkeypatch):
    aufrufe_get_vehicle_data = []

    _setze_neutrale_ladehilfen(monkeypatch)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "last_vehicle_state", {"veh-asleep-open": "online"})
    monkeypatch.setattr(app, "get_vehicle_state", lambda vid: {"state": "asleep"})
    monkeypatch.setattr(
        app,
        "_load_cached",
        lambda vehicle_id: {
            "state": "online",
            "charge_state": {"charging_state": "Disconnected"},
            "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
            "vehicle_state": {
                "locked": True,
                "is_user_present": False,
                "sun_roof_state": "open",
                "sun_roof_percent_open": 20,
            },
        },
    )

    def _fake_get_vehicle_data(vid, state=None):
        aufrufe_get_vehicle_data.append((vid, state))
        return {"state": "online", "charge_state": {}, "drive_state": {}}

    monkeypatch.setattr(app, "get_vehicle_data", _fake_get_vehicle_data)

    daten = app._fetch_data_once("veh-asleep-open")

    assert aufrufe_get_vehicle_data == []
    assert daten["state"] == "asleep"
    assert daten["_live"] is False


def test_get_vehicle_state_asleep_prueft_state_erst_nach_10_sekunden(monkeypatch):
    aufrufe_summary = []
    aufrufe_fahrzeugliste = []
    aktuelle_zeit = [109.0]

    class FakeVehicle(dict):
        def get_vehicle_summary(self):
            aufrufe_summary.append("summary")
            self["state"] = "asleep"

    fahrzeug = FakeVehicle({"id_s": "veh-state-sleep", "state": "asleep"})

    monkeypatch.setattr(app, "last_vehicle_state", {"veh-state-sleep": "asleep"})
    monkeypatch.setattr(app, "_last_state_refresh_ts", {"veh-state-sleep": 100.0})
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "occupant_present", False)
    monkeypatch.setattr(
        app,
        "load_config",
        lambda vehicle_id=None: {"api_interval": 1, "api_interval_idle": 30},
    )
    monkeypatch.setattr(
        app,
        "_load_cached",
        lambda vehicle_id: {
            "state": "online",
            "vehicle_state": {
                "locked": False,
                "is_user_present": False,
                "sun_roof_state": "open",
                "sun_roof_percent_open": 20,
            },
        },
    )
    monkeypatch.setattr(app.time, "time", lambda: aktuelle_zeit[0])
    monkeypatch.setattr(app, "get_tesla", lambda: object())

    def _fake_fahrzeugliste(tesla, ttl=86400, allow_refresh=True):
        aufrufe_fahrzeugliste.append(allow_refresh)
        return [fahrzeug]

    monkeypatch.setattr(app, "_cached_vehicle_list", _fake_fahrzeugliste)

    daten = app.get_vehicle_state("veh-state-sleep")

    assert daten["state"] == "asleep"
    assert daten["state_checked_at"] == 100000
    assert aufrufe_summary == []
    assert aufrufe_fahrzeugliste == []

    aktuelle_zeit[0] = 110.0
    daten = app.get_vehicle_state("veh-state-sleep")

    assert daten["state"] == "asleep"
    assert daten["state_checked_at"] == 110000
    assert aufrufe_summary == ["summary"]
    assert aufrufe_fahrzeugliste == [False]


def test_fetch_data_once_online_ruft_live_abruf_auf_und_nutzt_fallback(monkeypatch):
    aufrufe_get_vehicle_data = []

    _setze_neutrale_ladehilfen(monkeypatch)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "last_vehicle_state", {"veh-online": "asleep"})
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


def test_fetch_data_once_online_geparkt_nutzt_cache_ohne_live(monkeypatch):
    aufrufe_get_vehicle_data = []

    _setze_neutrale_ladehilfen(monkeypatch)
    monkeypatch.setattr(app, "occupant_present", False)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "last_vehicle_state", {"veh-parked": "online"})
    monkeypatch.setattr(app, "get_vehicle_state", lambda vid: {"state": "online"})
    monkeypatch.setattr(
        app,
        "_load_cached",
        lambda vehicle_id: {
            "state": "online",
            "charge_state": {"charging_state": "Disconnected"},
            "drive_state": {"shift_state": None, "speed": 0, "power": 0},
            "vehicle_state": {
                "locked": True,
                "is_user_present": False,
                "df": 0,
                "dr": 0,
                "pf": 0,
                "pr": 0,
                "ft": 0,
                "rt": 0,
                "fd_window": 0,
                "rd_window": 0,
                "fp_window": 0,
                "rp_window": 0,
            },
            "source": "cache",
        },
    )

    def _fake_get_vehicle_data(vid, state=None):
        aufrufe_get_vehicle_data.append((vid, state))
        return {"state": "online", "charge_state": {}, "drive_state": {}}

    monkeypatch.setattr(app, "get_vehicle_data", _fake_get_vehicle_data)

    daten = app._fetch_data_once("veh-parked")

    assert aufrufe_get_vehicle_data == []
    assert daten["state"] == "online"
    assert daten["source"] == "cache"
    assert daten["_live"] is False


def test_fetch_data_once_online_geparkt_prueft_alten_schiebedachstatus_live(monkeypatch):
    aufrufe_get_vehicle_data = []
    alter_zeitstempel = int((time.time() - 120) * 1000)

    _setze_neutrale_ladehilfen(monkeypatch)
    monkeypatch.setattr(
        app,
        "load_config",
        lambda vehicle_id=None: {"api_interval": 3, "api_interval_idle": 30},
    )
    monkeypatch.setattr(app, "occupant_present", False)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "last_vehicle_state", {"veh-sunroof-stale": "online"})
    monkeypatch.setattr(app, "get_vehicle_state", lambda vid: {"state": "online"})
    monkeypatch.setattr(
        app,
        "_load_cached",
        lambda vehicle_id: {
            "state": "online",
            "charge_state": {"charging_state": "Disconnected"},
            "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
            "vehicle_state": {
                "timestamp": alter_zeitstempel,
                "locked": True,
                "is_user_present": False,
                "df": 0,
                "dr": 0,
                "pf": 0,
                "pr": 0,
                "ft": 0,
                "rt": 0,
                "fd_window": 0,
                "rd_window": 0,
                "fp_window": 0,
                "rp_window": 0,
                "sun_roof_state": "closed",
                "sun_roof_percent_open": 0,
            },
            "source": "cache",
        },
    )

    def _fake_get_vehicle_data(vid, state=None):
        aufrufe_get_vehicle_data.append((vid, state))
        return {
            "state": "online",
            "charge_state": {"charging_state": "Disconnected"},
            "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
            "vehicle_state": {
                "locked": True,
                "is_user_present": False,
                "sun_roof_state": "open",
                "sun_roof_percent_open": 20,
            },
        }

    monkeypatch.setattr(app, "get_vehicle_data", _fake_get_vehicle_data)

    daten = app._fetch_data_once("veh-sunroof-stale")

    assert aufrufe_get_vehicle_data == [("veh-sunroof-stale", "online")]
    assert daten["vehicle_state"]["sun_roof_state"] == "open"
    assert daten["_live"] is True


def test_oeffnungsstatus_pruefung_hat_toleranz_fuer_idle_takt(monkeypatch):
    jetzt = 1_779_314_100.0
    monkeypatch.setattr(app.time, "time", lambda: jetzt)
    daten = {
        "vehicle_state": {
            "timestamp": int((jetzt - 29.0) * 1000),
            "locked": True,
            "sun_roof_state": "closed",
            "sun_roof_percent_open": 0,
        }
    }

    assert app._soll_öffnungsstatus_live_prüfen(daten, None, 30) is True


def test_fetch_data_once_schiebedach_offen_ruft_live_abruf_auf(monkeypatch):
    aufrufe_get_vehicle_data = []

    _setze_neutrale_ladehilfen(monkeypatch)
    monkeypatch.setattr(app, "occupant_present", False)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "last_vehicle_state", {"veh-sunroof": "online"})
    monkeypatch.setattr(app, "get_vehicle_state", lambda vid: {"state": "online"})
    monkeypatch.setattr(
        app,
        "_load_cached",
        lambda vehicle_id: {
            "state": "online",
            "charge_state": {"charging_state": "Disconnected"},
            "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
            "vehicle_state": {
                "locked": True,
                "is_user_present": False,
                "sun_roof_state": "open",
                "sun_roof_percent_open": 12,
            },
        },
    )

    def _fake_get_vehicle_data(vid, state=None):
        aufrufe_get_vehicle_data.append((vid, state))
        return {"state": "online", "charge_state": {}, "drive_state": {}}

    monkeypatch.setattr(app, "get_vehicle_data", _fake_get_vehicle_data)

    daten = app._fetch_data_once("veh-sunroof")

    assert aufrufe_get_vehicle_data == [("veh-sunroof", "online")]
    assert daten["state"] == "online"
    assert daten["_live"] is True


def test_geschlossene_öffnungen_zählen_nicht_als_aktivität():
    daten = {
        "vehicle_state": {
            "df": "closed",
            "rt": 0,
            "fd_window": "0",
            "sun_roof_state": "closed",
            "sun_roof_percent_open": 0,
            "locked": True,
            "is_user_present": False,
        },
        "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
        "charge_state": {"charging_state": "Disconnected"},
    }

    assert app._hat_normale_fahrzeugaktivitaet(daten) is False


def test_fetch_data_once_default_nutzt_bekannten_einzelfahrzeug_state(monkeypatch):
    aufrufe_get_vehicle_data = []

    _setze_neutrale_ladehilfen(monkeypatch)
    monkeypatch.setattr(app, "_default_vehicle_id", None)
    monkeypatch.setattr(app, "occupant_present", False)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "last_vehicle_state", {"veh-real": "online"})
    monkeypatch.setattr(app, "get_vehicle_state", lambda vid: {"state": "online"})
    monkeypatch.setattr(
        app,
        "_load_cached",
        lambda vehicle_id: {
            "state": "online",
            "charge_state": {"charging_state": "Disconnected"},
            "drive_state": {"shift_state": None, "speed": 0, "power": 0},
            "vehicle_state": {"locked": True, "is_user_present": False},
            "source": "cache",
        },
    )

    def _fake_get_vehicle_data(vid, state=None):
        aufrufe_get_vehicle_data.append((vid, state))
        return {"state": "online", "charge_state": {}, "drive_state": {}}

    monkeypatch.setattr(app, "get_vehicle_data", _fake_get_vehicle_data)

    daten = app._fetch_data_once("default")

    assert aufrufe_get_vehicle_data == []
    assert daten["state"] == "online"
    assert daten["source"] == "cache"
    assert daten["_live"] is False


def test_fetch_data_once_online_aktiv_ruft_live_abruf_auf(monkeypatch):
    aufrufe_get_vehicle_data = []

    _setze_neutrale_ladehilfen(monkeypatch)
    monkeypatch.setattr(app, "occupant_present", False)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "last_vehicle_state", {"veh-active": "online"})
    monkeypatch.setattr(app, "get_vehicle_state", lambda vid: {"state": "online"})
    monkeypatch.setattr(
        app,
        "_load_cached",
        lambda vehicle_id: {
            "state": "online",
            "charge_state": {"charging_state": "Disconnected"},
            "drive_state": {"shift_state": "D", "speed": 0, "power": 0},
            "vehicle_state": {"locked": False, "is_user_present": False},
        },
    )

    def _fake_get_vehicle_data(vid, state=None):
        aufrufe_get_vehicle_data.append((vid, state))
        return {"state": "online", "charge_state": {}, "drive_state": {}}

    monkeypatch.setattr(app, "get_vehicle_data", _fake_get_vehicle_data)

    daten = app._fetch_data_once("veh-active")

    assert aufrufe_get_vehicle_data == [("veh-active", "online")]
    assert daten["state"] == "online"
    assert daten["_live"] is True


def test_fetch_loop_locked_ohne_insassen_nutzt_idle_intervall(monkeypatch):
    idle_aufrufe = []

    monkeypatch.setattr(
        app,
        "load_config",
        lambda: {"api_interval": 5, "api_interval_idle": 30},
    )
    monkeypatch.setattr(
        app,
        "_fetch_data_once",
        lambda vehicle_id: {
            "_live": False,
            "state": "online",
            "vehicle_state": {
                "locked": True,
                "is_user_present": False,
                "df": 0,
                "dr": 0,
                "pf": 0,
                "pr": 0,
                "ft": 0,
                "rt": 0,
                "fd_window": 0,
                "rd_window": 0,
                "fp_window": 0,
                "rp_window": 0,
            },
            "drive_state": {"shift_state": None, "speed": 0, "power": 0},
            "charge_state": {"charging_state": "Disconnected"},
        },
    )
    monkeypatch.setattr(app, "send_aprs", lambda data: None)
    monkeypatch.setattr(app.time, "time", lambda: 100.0)

    def _fake_sleep_idle(sekunden):
        idle_aufrufe.append(sekunden)
        raise RuntimeError("stop-loop")

    monkeypatch.setattr(app, "_sleep_idle", _fake_sleep_idle)
    monkeypatch.setattr(app.time, "sleep", lambda sekunden: None)
    monkeypatch.setattr(app, "occupant_present", False)

    with pytest.raises(RuntimeError, match="stop-loop"):
        app._fetch_loop("veh")

    assert idle_aufrufe == [30]


def test_fetch_loop_offline_nutzt_state_intervall_trotz_aktivitaetsdaten(monkeypatch):
    schlaf_aufrufe = []

    monkeypatch.setattr(
        app,
        "load_config",
        lambda: {"api_interval": 5, "api_interval_idle": 30},
    )
    monkeypatch.setattr(
        app,
        "_fetch_data_once",
        lambda vehicle_id: {
            "_live": False,
            "state": "offline",
            "vehicle_state": {
                "locked": False,
                "is_user_present": True,
                "sun_roof_state": "open",
                "sun_roof_percent_open": 12,
            },
            "drive_state": {"shift_state": "D", "speed": 0, "power": 0},
            "charge_state": {"charging_state": "Disconnected"},
        },
    )
    monkeypatch.setattr(app, "send_aprs", lambda data: None)
    monkeypatch.setattr(app.time, "time", lambda: 100.0)
    monkeypatch.setattr(app, "occupant_present", False)

    def _fake_sleep_idle(sekunden):
        raise AssertionError("Offline darf nicht ins Leerlaufintervall fallen")

    def _fake_sleep(sekunden):
        schlaf_aufrufe.append(sekunden)
        raise RuntimeError("stop-loop")

    monkeypatch.setattr(app, "_sleep_idle", _fake_sleep_idle)
    monkeypatch.setattr(app.time, "sleep", _fake_sleep)

    with pytest.raises(RuntimeError, match="stop-loop"):
        app._fetch_loop("veh")

    assert schlaf_aufrufe == [10]


def test_fetch_loop_unlocked_nutzt_normales_intervall(monkeypatch):
    schlaf_aufrufe = []

    monkeypatch.setattr(
        app,
        "load_config",
        lambda: {"api_interval": 5, "api_interval_idle": 30},
    )
    monkeypatch.setattr(
        app,
        "_fetch_data_once",
        lambda vehicle_id: {
            "_live": False,
            "state": "online",
            "vehicle_state": {"locked": False, "is_user_present": False},
            "drive_state": {"shift_state": None, "speed": 0, "power": 0},
            "charge_state": {"charging_state": "Disconnected"},
        },
    )
    monkeypatch.setattr(app, "send_aprs", lambda data: None)
    monkeypatch.setattr(app.time, "time", lambda: 100.0)
    monkeypatch.setattr(app, "occupant_present", False)
    monkeypatch.setattr(app, "_sleep_idle", lambda sekunden: None)

    def _fake_sleep(sekunden):
        schlaf_aufrufe.append(sekunden)
        raise RuntimeError("stop-loop")

    monkeypatch.setattr(app.time, "sleep", _fake_sleep)

    with pytest.raises(RuntimeError, match="stop-loop"):
        app._fetch_loop("veh")

    assert schlaf_aufrufe == [5]


def test_fetch_loop_schiebedach_offen_nutzt_normales_intervall(monkeypatch):
    schlaf_aufrufe = []

    monkeypatch.setattr(
        app,
        "load_config",
        lambda: {"api_interval": 5, "api_interval_idle": 30},
    )
    monkeypatch.setattr(
        app,
        "_fetch_data_once",
        lambda vehicle_id: {
            "_live": False,
            "state": "online",
            "vehicle_state": {
                "locked": True,
                "is_user_present": False,
                "sun_roof_state": "open",
                "sun_roof_percent_open": 12,
            },
            "drive_state": {"shift_state": "P", "speed": 0, "power": 0},
            "charge_state": {"charging_state": "Disconnected"},
        },
    )
    monkeypatch.setattr(app, "send_aprs", lambda data: None)
    monkeypatch.setattr(app.time, "time", lambda: 100.0)
    monkeypatch.setattr(app, "occupant_present", False)
    monkeypatch.setattr(app, "_sleep_idle", lambda sekunden: None)

    def _fake_sleep(sekunden):
        schlaf_aufrufe.append(sekunden)
        raise RuntimeError("stop-loop")

    monkeypatch.setattr(app.time, "sleep", _fake_sleep)

    with pytest.raises(RuntimeError, match="stop-loop"):
        app._fetch_loop("veh")

    assert schlaf_aufrufe == [5]
