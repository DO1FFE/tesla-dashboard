import base64
import json
import pathlib
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


def _routeline_protobuf(polyline):
    laenge = len(polyline)
    varint = bytearray()
    while True:
        byte = laenge & 0x7F
        laenge >>= 7
        if laenge:
            varint.append(byte | 0x80)
        else:
            varint.append(byte)
            break
    payload = b"\x0a" + bytes(varint) + polyline.encode("ascii")
    return base64.b64encode(payload).decode("ascii")


def _telemetrie_stream_details(vin="TESTVIN"):
    return [{
        "vin": vin,
        "synced": True,
        "source": "telemetry_stream",
    }]


def _bestaetigter_profilstatus(profil, zeitpunkt, **anpassungen):
    details = [{"vin": "TESTVIN", "synced": True}]
    if profil in {"live", "live_extended"}:
        details = _telemetrie_stream_details()
    status = {
        "current": profil,
        "target": profil,
        "target_since": zeitpunkt,
        "last_sent": zeitpunkt,
        "last_sent_profile": profil,
        "last_posted_at": zeitpunkt,
        "last_posted_profile": profil,
        "last_error": None,
        "config_synced": True,
        "config_key_paired": None,
        "config_sync_state": "synced",
        "config_sync_profile": profil,
        "config_sync_checked_at": zeitpunkt,
        "config_sync_updated_at": zeitpunkt,
        "config_sync_error": None,
        "config_sync_details": details,
        "live_stable_since": 0.0,
        "live_unstable_since": 0.0,
        "live_retry_active": False,
        "live_retry_started_at": 0.0,
        "live_retry_last_moving_at": 0.0,
        "live_retry_motion_active": False,
        "live_retry_confirmed_at": 0.0,
        "live_retry_attempts": 0,
        "live_reconnect_seen_at": 0.0,
        "live_recovery_bootstrap_active": False,
        "live_recovery_full_pending": False,
        "live_recovery_bootstrap_confirmed_at": 0.0,
        "charging_observed": None,
        "post_charge_live_since": 0.0,
        "post_charge_live_until": 0.0,
        "updated_at": zeitpunkt,
    }
    status.update(anpassungen)
    return status


@pytest.fixture(autouse=True)
def keine_echten_parking_logs(monkeypatch):
    """Verhindere echte Log-Einträge in Fleet-Telemetry-Tests."""

    monkeypatch.setattr(
        app,
        "_record_dashboard_parking_state",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(app, "log_vehicle_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_ladeinformationen_aktualisieren",
        lambda _cache_id, data, cached=None: data,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_status_speichern",
        lambda: None,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda _profil: None,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": app.FLEET_TELEMETRIE_PROFILE_STANDARD,
            "target": app.FLEET_TELEMETRIE_PROFILE_STANDARD,
            "target_since": 0.0,
            "last_sent": 0.0,
            "last_sent_profile": None,
            "last_posted_at": 0.0,
            "last_posted_profile": None,
            "last_error": None,
            "config_synced": None,
            "config_key_paired": None,
            "config_sync_state": "unknown",
            "config_sync_profile": None,
            "config_sync_checked_at": 0.0,
            "config_sync_updated_at": 0.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "live_retry_active": False,
            "live_retry_started_at": 0.0,
            "live_retry_last_moving_at": 0.0,
            "live_retry_motion_active": False,
            "live_retry_confirmed_at": 0.0,
            "live_retry_attempts": 0,
            "live_reconnect_seen_at": 0.0,
            "live_recovery_bootstrap_active": False,
            "live_recovery_full_pending": False,
            "live_recovery_bootstrap_confirmed_at": 0.0,
            "charging_observed": None,
            "post_charge_live_since": 0.0,
            "post_charge_live_until": 0.0,
            "updated_at": 0.0,
        },
    )
    monkeypatch.setattr(app, "_fleet_telemetry_profile_reconnect_seen_at", {})
    monkeypatch.setattr(app, "_fleet_telemetry_parkabgleich_letzte_abfrage", {})


def test_fleet_telemetrie_mqtt_aktualisiert_dashboard_cache(monkeypatch):
    gespeicherte_daten = {}

    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
        "id_s": "veh-1",
        "vehicle_id": "legacy-veh-1",
        "display_name": "Testauto",
    }])
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: {})
    monkeypatch.setattr(app, "reverse_geocode", lambda lat, lon, vehicle_id=None: {})
    monkeypatch.setattr(
        app,
        "_save_cached",
        lambda vehicle_id, data: gespeicherte_daten.setdefault(vehicle_id, data),
    )
    monkeypatch.setattr(app, "latest_data", {})

    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/Location",
        b'{"latitude": 51.0, "longitude": 7.0}',
        {"topic_base": "tesla"},
    )
    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/BatteryLevel",
        b"88",
        {"topic_base": "tesla"},
    )
    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/DetailedChargeState",
        b'"DetailedChargeStateCharging"',
        {"topic_base": "tesla"},
    )

    daten = app.latest_data["veh-1"]
    assert daten["display_name"] == "Testauto"
    assert daten["drive_state"]["latitude"] == 51.0
    assert daten["drive_state"]["longitude"] == 7.0
    assert daten["charge_state"]["battery_level"] == 88
    assert daten["charge_state"]["usable_battery_level"] == 88
    assert daten["charge_state"]["charging_state"] == "Charging"
    assert daten["_live"] is True
    assert gespeicherte_daten["veh-1"]["fleet_telemetry_updated_at"]


def test_fleet_telemetrie_stoesst_aprs_aus_live_daten_an(monkeypatch):
    aprs_daten = []

    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: {})
    monkeypatch.setattr(app, "_save_cached", lambda vehicle_id, data: None)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "subscribers", {})
    monkeypatch.setattr(
        app,
        "_aprs_spaeter_senden",
        lambda data: aprs_daten.append(data),
    )

    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/Location",
        b'{"latitude": 51.0, "longitude": 7.0}',
        {"topic_base": "tesla"},
    )

    assert len(aprs_daten) == 1
    assert aprs_daten[0]["drive_state"]["latitude"] == 51.0
    assert aprs_daten[0]["drive_state"]["longitude"] == 7.0


def test_fleet_telemetrie_positionswaechter_erkennt_nur_aktive_fahrt(monkeypatch):
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_POSITION_MAX_ALTER_SECONDS",
        15.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_POSITION_STREAM_MAX_ALTER_SECONDS",
        15.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_POSITION_MIN_GESCHWINDIGKEIT_MPH",
        0.5,
    )
    daten = {
        "state": "online",
        "drive_state": {"shift_state": "D", "speed": 30},
        "fleet_telemetry_received_at": 1_999_999_999_000,
        "fleet_telemetry_field_received_at": {
            "Location": 1_999_999_980_000,
            "VehicleSpeed": 1_999_999_999_000,
        },
    }

    assert app._fleet_telemetrie_position_soll_aktualisiert_werden(
        daten,
        jetzt_ms=2_000_000_000_000,
    )

    daten["fleet_telemetry_position_fallback_at"] = 1_999_999_999_000
    assert not app._fleet_telemetrie_position_soll_aktualisiert_werden(
        daten,
        jetzt_ms=2_000_000_000_000,
    )
    daten.pop("fleet_telemetry_position_fallback_at")
    daten["drive_state"]["speed"] = 0
    assert not app._fleet_telemetrie_position_soll_aktualisiert_werden(
        daten,
        jetzt_ms=2_000_000_000_000,
    )
    daten["drive_state"]["speed"] = 30
    daten["state"] = "offline"
    assert not app._fleet_telemetrie_position_soll_aktualisiert_werden(
        daten,
        jetzt_ms=2_000_000_000_000,
    )
    daten["state"] = "online"
    daten["fleet_telemetry_field_received_at"][
        "VehicleSpeed"
    ] = 1_999_999_900_000
    assert not app._fleet_telemetrie_position_soll_aktualisiert_werden(
        daten,
        jetzt_ms=2_000_000_000_000,
    )


@pytest.mark.parametrize(
    "speed_empfangen",
    [
        1_999_999_999_000,
        1_999_999_820_000,
    ],
)
def test_fleet_telemetrie_positionswaechter_fragt_an_ampel_nicht_ab(
    monkeypatch,
    speed_empfangen,
):
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_POSITION_MAX_ALTER_SECONDS",
        15.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_POSITION_STREAM_MAX_ALTER_SECONDS",
        15.0,
    )
    daten = {
        "state": "online",
        "drive_state": {"shift_state": "D", "speed": 0},
        "fleet_telemetry_received_at": 1_999_999_999_000,
        "fleet_telemetry_field_received_at": {
            "Location": 1_999_999_820_000,
            "VehicleSpeed": speed_empfangen,
        },
    }

    assert not app._fleet_telemetrie_position_soll_aktualisiert_werden(
        daten,
        jetzt_ms=2_000_000_000_000,
    )


def test_fleet_telemetrie_parkabgleich_startet_nur_nach_p(monkeypatch):
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PARKABGLEICH_VERZOEGERUNG_SECONDS",
        10.0,
    )
    daten = {
        "state": "online",
        "drive_state": {"shift_state": "P", "speed": 0},
        "fleet_telemetry_field_received_at": {"Gear": 1_999_999_980_000},
    }

    assert app._fleet_telemetrie_parkabgleich_soll_aktualisiert_werden(
        daten,
        jetzt_ms=2_000_000_000_000,
    )

    daten["drive_state"]["shift_state"] = "D"
    assert not app._fleet_telemetrie_parkabgleich_soll_aktualisiert_werden(
        daten,
        jetzt_ms=2_000_000_000_000,
    )
    daten["drive_state"]["shift_state"] = "P"
    daten["fleet_telemetry_park_reconciled_at"] = 1_999_999_990_000
    assert not app._fleet_telemetrie_parkabgleich_soll_aktualisiert_werden(
        daten,
        jetzt_ms=2_000_000_000_000,
    )


def test_fleet_telemetrie_ladeabgleich_erkennt_frischen_hv_ladestrom(
    monkeypatch,
):
    jetzt_ms = 2_000_000_000_000
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PARKABGLEICH_VERZOEGERUNG_SECONDS",
        10.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_LADEABGLEICH_MAX_ALTER_SECONDS",
        20.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_LADEABGLEICH_MIN_LEISTUNG_KW",
        1.0,
    )
    daten = {
        "state": "online",
        "drive_state": {"shift_state": "P", "speed": 0},
        "charge_state": {
            "charging_state": "Disconnected",
            "charger_power": 0,
        },
        "fleet_telemetry_raw": {
            "PackCurrent": 67.9,
            "PackVoltage": 402.5,
        },
        "fleet_telemetry_field_received_at": {
            "Gear": jetzt_ms - 120_000,
            "PackCurrent": jetzt_ms - 500,
            "PackVoltage": jetzt_ms - 500,
            "ChargeState": jetzt_ms - 120_000,
            "DetailedChargeState": jetzt_ms - 120_000,
        },
    }

    assert app._fleet_telemetrie_ladeabgleich_soll_aktualisiert_werden(
        daten,
        jetzt_ms,
    )

    daten["drive_state"]["shift_state"] = "D"
    assert not app._fleet_telemetrie_ladeabgleich_soll_aktualisiert_werden(
        daten,
        jetzt_ms,
    )
    daten["drive_state"]["shift_state"] = "P"
    daten["fleet_telemetry_raw"]["PackCurrent"] = -8
    assert not app._fleet_telemetrie_ladeabgleich_soll_aktualisiert_werden(
        daten,
        jetzt_ms,
    )
    daten["fleet_telemetry_raw"]["PackCurrent"] = 67.9
    daten["fleet_telemetry_field_received_at"]["ChargeState"] = jetzt_ms - 5_000
    assert not app._fleet_telemetrie_ladeabgleich_soll_aktualisiert_werden(
        daten,
        jetzt_ms,
    )


def test_fleet_telemetrie_ladeabgleich_hat_sperrfrist(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetry_ladeabgleich_letzte_abfrage", {})
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_LADEABGLEICH_WIEDERHOLUNG_SECONDS",
        60.0,
    )

    assert app._fleet_telemetrie_ladeabgleich_reservieren("TESTVIN", 100.0)
    assert not app._fleet_telemetrie_ladeabgleich_reservieren(
        "TESTVIN",
        159.9,
    )
    assert app._fleet_telemetrie_ladeabgleich_reservieren("TESTVIN", 160.0)


def test_fleet_telemetrie_parkabgleich_korrigiert_veraltete_abschaltwerte(
    monkeypatch,
):
    gesendet = []
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_dashboard_daten_anreichern",
        lambda _, data: data,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_aktualisieren",
        lambda _, data: data,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_parkstatus_aufzeichnen",
        lambda *args: None,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(
        app,
        "_subscriber_daten_senden",
        lambda cache_id, data: gesendet.append((cache_id, data)),
    )
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "online",
            "drive_state": {
                "shift_state": "P",
                "speed": 0,
                "latitude": 51.45,
                "longitude": 7.03,
            },
            "vehicle_state": {
                "is_user_present": True,
                "locked": False,
                "center_display_state": "On",
                "brake_pedal": True,
                "pedal_position": 12,
            },
            "climate_state": {"is_climate_on": True, "fan_status": 4},
            "charge_state": {
                "charging_state": "Disconnected",
                "charger_power": 9,
            },
        },
    })
    parkdaten = {
        "state": "online",
        "drive_state": {
            "shift_state": None,
            "speed": None,
            "latitude": None,
            "longitude": None,
        },
        "vehicle_state": {"is_user_present": False, "locked": True},
        "climate_state": {"is_climate_on": False, "fan_status": 0},
        "charge_state": {
            "charging_state": "Disconnected",
            "charger_power": 0,
        },
    }

    assert app._fleet_telemetrie_parkdaten_uebernehmen(
        "TESTVIN",
        parkdaten,
        2_000_000_000_000,
    )

    daten = app.latest_data["veh-1"]
    assert daten["drive_state"]["shift_state"] == "P"
    assert daten["drive_state"]["latitude"] == 51.45
    assert daten["vehicle_state"]["is_user_present"] is False
    assert daten["vehicle_state"]["locked"] is True
    assert daten["vehicle_state"]["center_display_state"] == "Off"
    assert daten["vehicle_state"]["brake_pedal"] is False
    assert daten["vehicle_state"]["pedal_position"] == 0
    assert daten["climate_state"]["is_climate_on"] is False
    assert daten["climate_state"]["fan_status"] == 0
    assert daten["charge_state"]["charger_power"] == 0
    assert daten["fleet_telemetry_park_reconciled_at"] == 2_000_000_000_000
    assert gesendet[-1][0] == "veh-1"


def test_fleet_telemetrie_parkabgleich_ruft_vollstaendige_daten_ab(monkeypatch):
    class Antwort:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": {"state": "online", "vehicle_state": {}}}

    abfragen = []

    def fake_get(url, **kwargs):
        abfragen.append((url, kwargs))
        return Antwort()

    monkeypatch.setattr(app, "_fleet_telemetrie_oauth_token", lambda: "token")
    monkeypatch.setattr(app.requests, "get", fake_get)
    monkeypatch.setattr(
        app,
        "TESLA_FLEET_VEHICLE_COMMAND_URL",
        "https://127.0.0.1:4443",
    )

    daten = app._fleet_telemetrie_parkdaten_abrufen("TESTVIN")

    assert daten["state"] == "online"
    assert abfragen[0][0].endswith("/api/1/vehicles/TESTVIN/vehicle_data")
    assert "params" not in abfragen[0][1]
    assert abfragen[0][1]["headers"] == {"Authorization": "Bearer token"}


def test_fleet_telemetrie_positionsabfrage_hat_sperrfrist(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetry_position_letzte_abfrage", {})
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_POSITION_WIEDERHOLUNG_SECONDS",
        30.0,
    )

    assert app._fleet_telemetrie_position_abfrage_reservieren("TESTVIN", 100.0)
    assert not app._fleet_telemetrie_position_abfrage_reservieren(
        "TESTVIN",
        129.9,
    )
    assert app._fleet_telemetrie_position_abfrage_reservieren("TESTVIN", 130.0)


def test_fleet_telemetrie_streamwiederherstellung_nur_bei_aktiven_daten(
    monkeypatch,
):
    jetzt_ms = 2_000_000_000_000
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_STREAM_WIEDERHERSTELLUNG_NACH_SECONDS",
        20.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_STREAM_WIEDERHERSTELLUNG_WIEDERHOLUNG_SECONDS",
        30.0,
    )
    daten = {
        "fleet_telemetry_received_at": jetzt_ms - 21_000,
        "drive_state": {"shift_state": "D", "speed": 30, "power": 5},
        "charge_state": {"charging_state": "Disconnected"},
        "climate_state": {"is_climate_on": True},
    }

    assert app._fleet_telemetrie_stream_wiederherstellung_soll_aktualisiert_werden(
        daten,
        jetzt_ms,
    )

    daten["drive_state"] = {"shift_state": "D", "speed": 0, "power": 0}
    assert not app._fleet_telemetrie_stream_wiederherstellung_soll_aktualisiert_werden(
        daten,
        jetzt_ms,
    )

    daten["drive_state"] = {"shift_state": "D", "speed": 2, "power": 0}
    assert not app._fleet_telemetrie_stream_wiederherstellung_soll_aktualisiert_werden(
        daten,
        jetzt_ms,
    )

    daten["drive_state"] = {"shift_state": "P", "speed": 0, "power": 0}
    assert app._fleet_telemetrie_stream_wiederherstellung_soll_aktualisiert_werden(
        daten,
        jetzt_ms,
    )

    daten["fleet_vehicle_data_received_at"] = jetzt_ms - 10_000
    assert not app._fleet_telemetrie_stream_wiederherstellung_soll_aktualisiert_werden(
        daten,
        jetzt_ms,
    )


def test_fleet_telemetrie_streamwiederherstellung_hat_sperrfrist(monkeypatch):
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_stream_wiederherstellung_letzte_abfrage",
        {},
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_STREAM_WIEDERHERSTELLUNG_WIEDERHOLUNG_SECONDS",
        30.0,
    )

    assert app._fleet_telemetrie_stream_wiederherstellung_reservieren(
        "TESTVIN",
        100.0,
    )
    assert not app._fleet_telemetrie_stream_wiederherstellung_reservieren(
        "TESTVIN",
        129.9,
    )
    assert app._fleet_telemetrie_stream_wiederherstellung_reservieren(
        "TESTVIN",
        130.0,
    )


def test_fleet_telemetrie_stummer_stream_startet_live_profilreparatur(
    monkeypatch,
):
    status = app._fleet_telemetrie_profile_status_standard()
    status.update({
        "current": "live",
        "target": "live",
        "last_posted_profile": "live",
        "config_synced": True,
        "config_sync_state": "synced",
        "config_sync_profile": "live",
    })
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_STREAM_WIEDERHERSTELLUNG_NACH_SECONDS",
        20.0,
    )
    monkeypatch.setattr(app, "_fleet_telemetry_profile_status", status)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_status_speichern",
        lambda: None,
    )
    daten = {
        "fleet_telemetry_received_at": 1_970_000,
        "fleet_vehicle_data_received_at": 1_999_000,
        "drive_state": {"shift_state": "D", "speed": 0},
    }

    assert not app._fleet_telemetrie_streamprofil_wiederherstellung_anfordern(
        daten,
        2000.0,
    )

    daten["drive_state"]["speed"] = 30

    assert app._fleet_telemetrie_streamprofil_wiederherstellung_anfordern(
        daten,
        2000.0,
    )

    assert status["live_retry_active"] is True
    assert status["live_retry_motion_active"] is True
    assert status["live_retry_last_moving_at"] == 2000.0
    assert status["config_synced"] is False
    assert status["config_sync_state"] == "active"


def test_fleet_telemetrie_fahrzeugzustand_nutzt_nicht_weckenden_endpunkt(
    monkeypatch,
):
    class Antwort:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": {"state": "online"}}

    abfragen = []

    def fake_get(url, **kwargs):
        abfragen.append((url, kwargs))
        return Antwort()

    monkeypatch.setattr(app, "_fleet_telemetrie_oauth_token", lambda: "token")
    monkeypatch.setattr(app.requests, "get", fake_get)
    monkeypatch.setattr(
        app,
        "TESLA_FLEET_VEHICLE_COMMAND_URL",
        "https://127.0.0.1:4443",
    )

    assert app._fleet_telemetrie_fahrzeugzustand_abrufen("TESTVIN") == "online"
    assert abfragen[0][0].endswith("/api/1/vehicles/TESTVIN")
    assert "params" not in abfragen[0][1]


def test_fleet_telemetrie_fallback_korrigiert_festgefahrene_fahrt(monkeypatch):
    gesendet = []
    gespeichert = []
    alt = {
        "state": "online",
        "drive_state": {
            "shift_state": "D",
            "speed": 70,
            "power": 18,
            "latitude": 51.0,
            "longitude": 7.0,
            "active_route_active": True,
            "active_route_destination": "Altes Ziel",
        },
        "vehicle_state": {
            "fd_window": 1,
            "locked": False,
            "brake_pedal": True,
            "lights_turn_signal": "Left",
        },
        "climate_state": {"fan_status": 4},
        "charge_state": {"dcdc_enable": True},
        "fleet_telemetry_raw": {
            "FdWindow": "Open",
            "HvacFanSpeed": 4,
            "DCDCEnable": True,
        },
    }
    aktuell = {
        "state": "online",
        "drive_state": {
            "shift_state": "P",
            "speed": None,
            "power": None,
            "latitude": 51.5,
            "longitude": 7.5,
            "timestamp": 2_000_000_000_000,
        },
        "vehicle_state": {
            "fd_window": 0,
            "locked": True,
            "timestamp": 2_000_000_000_000,
        },
        "climate_state": {
            "fan_status": 0,
            "is_climate_on": False,
            "timestamp": 2_000_000_000_000,
        },
        "charge_state": {
            "charging_state": "Disconnected",
            "timestamp": 2_000_000_000_000,
        },
    }
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(app, "latest_data", {"veh-1": alt})
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_dashboard_daten_anreichern",
        lambda _cache_id, data: data,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_aktualisieren",
        lambda _cache_id, data: data,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_parkstatus_aufzeichnen",
        lambda *args: None,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda cache_id, _data: gespeichert.append(cache_id),
    )
    monkeypatch.setattr(
        app,
        "_subscriber_daten_senden",
        lambda cache_id, _data: gesendet.append(cache_id),
    )
    monkeypatch.setattr(app, "_aprs_spaeter_senden", lambda _data: None)

    assert app._fleet_telemetrie_fallbackdaten_uebernehmen(
        "TESTVIN",
        aktuell,
        2_000_000_001_000,
    )

    daten = app.latest_data["veh-1"]
    assert daten["drive_state"]["shift_state"] == "P"
    assert daten["drive_state"]["speed"] == 0
    assert daten["drive_state"]["power"] == 0
    assert daten["drive_state"]["latitude"] == 51.5
    assert daten["drive_state"]["active_route_active"] is False
    assert "active_route_destination" not in daten["drive_state"]
    assert daten["vehicle_state"]["fd_window"] == 0
    assert "brake_pedal" not in daten["vehicle_state"]
    assert "lights_turn_signal" not in daten["vehicle_state"]
    assert daten["climate_state"]["fan_status"] == 0
    assert daten["charge_state"]["dcdc_enable"] is True
    assert "FdWindow" not in daten["fleet_telemetry_raw"]
    assert "HvacFanSpeed" not in daten["fleet_telemetry_raw"]
    assert daten["fleet_telemetry_raw"]["DCDCEnable"] is True
    assert daten["fleet_vehicle_data_source"] == "stream_recovery"
    assert daten["fleet_vehicle_data_received_at"] == 2_000_000_001_000
    assert gespeichert == ["veh-1"]
    assert gesendet == ["veh-1"]


def test_fleet_telemetrie_positionsabfrage_nutzt_nur_location_data(monkeypatch):
    class Antwort:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "response": {
                    "drive_state": {
                        "latitude": 51.45,
                        "longitude": 7.09,
                        "heading": 84,
                    },
                },
            }

    abfragen = []

    def fake_get(url, **kwargs):
        abfragen.append((url, kwargs))
        return Antwort()

    monkeypatch.setattr(app, "_fleet_telemetrie_oauth_token", lambda: "token")
    monkeypatch.setattr(app.requests, "get", fake_get)
    monkeypatch.setattr(
        app,
        "TESLA_FLEET_VEHICLE_COMMAND_URL",
        "https://127.0.0.1:4443",
    )

    drive = app._fleet_telemetrie_position_abrufen("TESTVIN")

    assert drive["latitude"] == 51.45
    assert drive["longitude"] == 7.09
    assert abfragen[0][0].endswith("/api/1/vehicles/TESTVIN/vehicle_data")
    assert abfragen[0][1]["params"] == {"endpoints": "location_data"}
    assert abfragen[0][1]["headers"] == {"Authorization": "Bearer token"}


def test_fleet_telemetrie_positionsabfrage_aktualisiert_alle_caches(monkeypatch):
    basis = {
        "state": "online",
        "drive_state": {
            "latitude": 51.0,
            "longitude": 7.0,
            "heading": 10,
            "speed": 30,
            "shift_state": "D",
            "timestamp": 1_999_990_000_000,
        },
        "fleet_telemetry_raw": {
            "Location": {"latitude": 51.0, "longitude": 7.0},
        },
        "fleet_telemetry_field_received_at": {
            "Location": 1_999_980_000_000,
        },
    }
    caches = {
        "default": json.loads(json.dumps(basis)),
        "veh-1": json.loads(json.dumps(basis)),
    }
    gesendet = []
    gespeichert = []
    aprs = []

    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_ids",
        lambda _vin: ["default", "veh-1"],
    )
    monkeypatch.setattr(app, "latest_data", caches)
    monkeypatch.setattr(app, "_load_cached", lambda _cache_id: None)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_dashboard_daten_anreichern",
        lambda _cache_id, data: data,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_aktualisieren",
        lambda _cache_id, data: data,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda cache_id, _data: gespeichert.append(cache_id),
    )
    monkeypatch.setattr(
        app,
        "_subscriber_daten_senden",
        lambda cache_id, _data: gesendet.append(cache_id),
    )
    monkeypatch.setattr(app, "_aprs_spaeter_senden", lambda data: aprs.append(data))

    assert app._fleet_telemetrie_position_uebernehmen(
        "TESTVIN",
        {
            "latitude": 51.45,
            "longitude": 7.09,
            "heading": 84,
            "gps_as_of": 2_000_000_000,
            "timestamp": 2_000_000_100_000,
        },
        abgerufen_at_ms=2_000_000_200_000,
    )

    assert gespeichert == ["default", "veh-1"]
    assert gesendet == ["default", "veh-1"]
    assert len(aprs) == 2
    for daten in caches.values():
        drive = daten["drive_state"]
        assert drive["latitude"] == 51.45
        assert drive["longitude"] == 7.09
        assert drive["heading"] == 84
        assert drive["gps_as_of"] == 2_000_000_000_000
        assert drive["timestamp"] == 2_000_000_100_000
        assert daten["fleet_telemetry_raw"]["Location"] == {
            "latitude": 51.45,
            "longitude": 7.09,
        }
        assert (
            daten["fleet_telemetry_position_fallback_at"]
            == 2_000_000_200_000
        )
        assert daten["fleet_telemetry_position_source"] == "vehicle_data"
        assert (
            daten["fleet_telemetry_field_received_at"]["Location"]
            == 1_999_980_000_000
        )


def test_fleet_telemetrie_streamwiederherstellung_uebernimmt_position_zuerst(
    monkeypatch,
):
    aufrufe = []
    position = {
        "latitude": 51.45,
        "longitude": 7.09,
    }

    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_fahrzeugzustand_abrufen",
        lambda vin: aufrufe.append(("state", vin)) or "online",
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_position_abrufen",
        lambda vin: aufrufe.append(("position", vin)) or position,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_position_uebernehmen",
        lambda vin, daten: aufrufe.append(("position übernehmen", vin, daten))
        or True,
    )

    def vollständige_daten(_vin):
        aufrufe.append(("vehicle_data", _vin))
        raise RuntimeError("Zeitüberschreitung")

    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_parkdaten_abrufen",
        vollständige_daten,
    )

    assert app._fleet_telemetrie_stream_wiederherstellen("TESTVIN")
    assert aufrufe == [
        ("state", "TESTVIN"),
        ("position", "TESTVIN"),
        ("position übernehmen", "TESTVIN", position),
        ("vehicle_data", "TESTVIN"),
    ]


def test_fleet_telemetrie_streamwiederherstellung_gleicht_trotz_positionsfehler_ab(
    monkeypatch,
):
    aufrufe = []
    fahrzeugdaten = {
        "state": "online",
        "drive_state": {"shift_state": "P"},
    }

    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_fahrzeugzustand_abrufen",
        lambda _vin: "online",
    )

    def position_abrufen(_vin):
        aufrufe.append("position")
        raise RuntimeError("nicht verfügbar")

    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_position_abrufen",
        position_abrufen,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_parkdaten_abrufen",
        lambda _vin: aufrufe.append("vehicle_data") or fahrzeugdaten,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_fallbackdaten_uebernehmen",
        lambda vin, daten: aufrufe.append((vin, daten)) or True,
    )

    assert app._fleet_telemetrie_stream_wiederherstellen("TESTVIN")
    assert aufrufe == [
        "position",
        "vehicle_data",
        ("TESTVIN", fahrzeugdaten),
    ]


def test_fleet_telemetrie_mqtt_zeichnet_parkstatus_auf(monkeypatch):
    parking_aufrufe = []

    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
        "id_s": "veh-1",
        "vehicle_id": "legacy-veh-1",
        "display_name": "Testauto",
    }])
    monkeypatch.setattr(app, "_default_vehicle_id", None)
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: {})
    monkeypatch.setattr(app, "_save_cached", lambda vehicle_id, data: None)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(
        app,
        "_record_dashboard_parking_state",
        lambda vehicle_id, data: parking_aufrufe.append((vehicle_id, data)),
    )

    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/BatteryLevel",
        b"84",
        {"topic_base": "tesla"},
    )

    assert {vehicle_id for vehicle_id, _data in parking_aufrufe} == {"veh-1"}


def test_fleet_telemetrie_mqtt_sendet_empfangszeit_bei_unveraenderten_rohwerten(monkeypatch):
    gespeicherte_daten = []

    class Sammler:
        def __init__(self):
            self.daten = []

        def put(self, daten):
            self.daten.append(daten)

    sammler = Sammler()
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: {})
    monkeypatch.setattr(
        app,
        "_save_cached",
        lambda vehicle_id, data: gespeicherte_daten.append((vehicle_id, data)),
    )
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "subscribers", {"veh-1": [sammler]})

    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/LightsHighBeams",
        b"false",
        {"topic_base": "tesla"},
        1000,
    )
    erster_zeitstempel = app.latest_data["veh-1"]["fleet_telemetry_updated_at"]
    assert app.latest_data["veh-1"]["fleet_telemetry_received_at"] == 1000

    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/LightsHighBeams",
        b"false",
        {"topic_base": "tesla"},
        2000,
    )
    assert app.latest_data["veh-1"]["fleet_telemetry_updated_at"] == erster_zeitstempel
    assert app.latest_data["veh-1"]["fleet_telemetry_received_at"] == 2000
    assert len(gespeicherte_daten) == 1
    assert len(sammler.daten) == 2
    assert sammler.daten[-1]["fleet_telemetry_received_at"] == 2000

    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/LightsHighBeams",
        b"true",
        {"topic_base": "tesla"},
        3000,
    )
    assert app.latest_data["veh-1"]["vehicle_state"]["lights_high_beams"] is True
    assert app.latest_data["veh-1"]["fleet_telemetry_received_at"] == 3000
    assert len(gespeicherte_daten) == 2
    assert len(sammler.daten) == 3


def test_fleet_telemetrie_batch_merkt_empfangszeit_aller_felder(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: {})
    monkeypatch.setattr(app, "_save_cached", lambda vehicle_id, data: None)
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)
    monkeypatch.setattr(app, "_aprs_spaeter_senden", lambda *args: None)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(
        app,
        "latest_data",
        {
            "veh-1": {
                "vin": "TESTVIN",
                "fleet_telemetry_raw": {
                    "VehicleSpeed": 12,
                    "DriverSeatOccupied": False,
                },
                "drive_state": {"speed": 12},
                "vehicle_state": {"is_user_present": False},
            },
        },
    )

    assert app._fleet_telemetrie_v_felder_aktualisieren(
        "TESTVIN",
        [
            ("VehicleSpeed", 12, 2000),
            ("DriverSeatOccupied", False, 2001),
        ],
    )

    daten = app.latest_data["veh-1"]
    assert daten["fleet_telemetry_received_at"] == 2001
    assert daten["fleet_telemetry_last_received_field"] == "DriverSeatOccupied"
    assert daten["fleet_telemetry_field_received_at"]["VehicleSpeed"] == 2000
    assert daten["fleet_telemetry_field_received_at"]["DriverSeatOccupied"] == 2001


def test_fleet_telemetrie_connectivity_wertet_disconnected_als_offline(monkeypatch):
    gespeicherte_daten = []
    connected_at = "2026-06-14T14:00:00Z"
    disconnected_at = "2026-06-14T14:47:59Z"
    connected_ms = int(
        datetime(2026, 6, 14, 14, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
    )
    disconnected_ms = int(
        datetime(2026, 6, 14, 14, 47, 59, tzinfo=timezone.utc).timestamp() * 1000
    )

    class Sammler:
        def __init__(self):
            self.daten = []

        def put(self, daten):
            self.daten.append(daten)

    sammler = Sammler()
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: {})
    monkeypatch.setattr(
        app,
        "_save_cached",
        lambda vehicle_id, data: gespeicherte_daten.append((vehicle_id, data)),
    )
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "subscribers", {"veh-1": [sammler]})

    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/connectivity",
        f'{{"Status": "CONNECTED", "CreatedAt": "{connected_at}"}}'.encode("utf-8"),
        {"topic_base": "tesla"},
    )
    assert app.latest_data["veh-1"]["state"] == "online"
    assert app.latest_data["veh-1"]["state_since_ms"] == connected_ms

    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/connectivity",
        f'{{"Status": "DISCONNECTED", "CreatedAt": "{disconnected_at}"}}'.encode("utf-8"),
        {"topic_base": "tesla"},
    )
    assert app.latest_data["veh-1"]["state"] == "offline"
    assert app.latest_data["veh-1"]["state_since_ms"] == disconnected_ms
    assert app.latest_data["veh-1"]["state_since_at"] == disconnected_at
    assert (
        app.latest_data["veh-1"]["fleet_telemetry_connectivity"]["Status"]
        == "DISCONNECTED"
    )
    assert gespeicherte_daten[-1][1]["state"] == "offline"
    assert gespeicherte_daten[-1][1]["state_since_ms"] == disconnected_ms
    assert sammler.daten[-1]["state"] == "offline"
    assert sammler.daten[-1]["state_since_ms"] == disconnected_ms


def test_fleet_telemetrie_disconnected_startet_parkprofil_countdown(monkeypatch):
    angefordert = []
    disconnected_ms = 1_800_000_000_000

    monkeypatch.setattr(app.time, "time", lambda: 1_800_000_000.0)
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktiviert", lambda: True)
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    app._fleet_telemetry_profile_status.update({
        "current": "live",
        "target": "live",
        "target_since": 1_799_999_900.0,
        "last_sent": 1_799_999_990.0,
        "last_sent_profile": "live",
        "last_posted_profile": "live",
        "config_synced": True,
        "config_sync_state": "synced",
        "config_sync_profile": "live",
        "config_sync_details": _telemetrie_stream_details(),
        "live_retry_active": True,
        "live_retry_motion_active": True,
    })
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "online",
            "drive_state": {"shift_state": "R", "speed": 5},
            "vehicle_state": {"is_user_present": True},
        },
    })
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)

    assert app._fleet_telemetrie_verbindung_aktualisieren(
        "TESTVIN",
        {"Status": "DISCONNECTED"},
        disconnected_ms,
    )

    status = app._fleet_telemetry_profile_status
    daten = app.latest_data["veh-1"]
    assert angefordert == []
    assert status["target"] == "parked"
    assert status["target_since"] == 1_800_000_000.0
    assert status["live_retry_active"] is False
    assert status["live_retry_motion_active"] is False
    assert daten["telemetry_profile"] == "live"
    assert daten["telemetry_profile_target"] == "parked"


def test_fleet_telemetrie_ignoriert_retained_fahrzeugfelder(monkeypatch):
    monkeypatch.setattr(app, "latest_data", {})

    assert not app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/VehicleSpeed",
        b"42",
        {"topic_base": "tesla"},
        timestamp_ms=2_000_000,
        retained=True,
    )

    assert app.latest_data == {}


def test_fleet_telemetrie_retained_connectivity_nur_offline_mit_quellzeit(
    monkeypatch,
):
    disconnected_at = "2026-07-23T06:44:40Z"
    disconnected_ms = int(
        datetime(2026, 7, 23, 6, 44, 40, tzinfo=timezone.utc).timestamp()
        * 1000
    )
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: {})
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "online",
            "state_since_ms": 1_000_000,
        },
    })

    assert not app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/connectivity",
        b'{"Status": "CONNECTED", "CreatedAt": "2026-07-23T06:40:00Z"}',
        {"topic_base": "tesla"},
        timestamp_ms=2_000_000,
        retained=True,
    )
    assert app.latest_data["veh-1"]["state"] == "online"

    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/connectivity",
        (
            f'{{"Status": "DISCONNECTED", "CreatedAt": "{disconnected_at}"}}'
        ).encode("utf-8"),
        {"topic_base": "tesla"},
        timestamp_ms=2_000_000,
        retained=True,
    )

    assert app.latest_data["veh-1"]["state"] == "offline"
    assert app.latest_data["veh-1"]["state_checked_at"] == disconnected_ms
    assert app.latest_data["veh-1"]["state_since_ms"] == disconnected_ms


def test_fleet_telemetrie_neuverbindung_beobachtet_live_ohne_sofort_post(
    monkeypatch,
):
    angefordert = []
    monkeypatch.setattr(app.time, "time", lambda: 2100.0)
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktiviert", lambda: True)
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    app._fleet_telemetry_profile_status.update({
        "current": "live",
        "target": "live",
        "last_sent": 2080.0,
        "last_sent_profile": "live",
        "config_synced": True,
        "config_sync_state": "synced",
        "config_sync_profile": "live",
        "config_sync_details": _telemetrie_stream_details(),
    })
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "offline",
            "fleet_telemetry_connectivity": {
                "Status": "DISCONNECTED",
                "ConnectionId": "alt",
            },
        },
    })
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)

    assert app._fleet_telemetrie_verbindung_aktualisieren(
        "TESTVIN",
        {"Status": "CONNECTED", "ConnectionId": "neu"},
        2_100_000,
    )

    assert angefordert == []
    assert app._fleet_telemetry_profile_status["last_sent"] == 2080.0
    assert app._fleet_telemetry_profile_status["last_sent_profile"] == "live"
    assert app._fleet_telemetry_profile_status["config_sync_state"] == "synced"
    assert app._fleet_telemetry_profile_status["live_reconnect_seen_at"] == 2100.0
    assert app.latest_data["veh-1"]["telemetry_config_sync_state"] == "synced"


def test_fleet_connectivity_protokolliert_zustand_einmal_kanonisch(monkeypatch):
    protokoll = []
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_fahrzeuge",
        lambda: [{"vin": "TESTVIN", "id_s": "veh-1"}],
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_ids",
        lambda vin: ["veh-1", "alias-1", "default"],
    )
    monkeypatch.setattr(
        app,
        "latest_data",
        {
            "veh-1": {"state": "offline"},
            "alias-1": {"state": "offline"},
            "default": {"state": "offline"},
        },
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)
    monkeypatch.setattr(
        app,
        "log_vehicle_state",
        lambda vehicle_id, state: protokoll.append((vehicle_id, state)),
    )

    assert app._fleet_telemetrie_verbindung_aktualisieren(
        "TESTVIN",
        {"Status": "CONNECTED", "ConnectionID": "neu"},
        2_100_000,
    )

    assert protokoll == [("veh-1", "online")]


def test_fleet_connectivity_protokolliert_keinen_veralteten_alias(monkeypatch):
    protokoll = []
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_fahrzeuge",
        lambda: [{"vin": "TESTVIN", "id_s": "veh-1"}],
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_ids",
        lambda vin: ["veh-1", "default"],
    )
    monkeypatch.setattr(
        app,
        "latest_data",
        {
            "veh-1": {
                "state": "online",
                "fleet_telemetry_connectivity": {
                    "Status": "CONNECTED",
                    "ConnectionID": "neu",
                },
            },
            "default": {
                "state": "online",
                "fleet_telemetry_connectivity": {
                    "Status": "CONNECTED",
                    "ConnectionID": "alt",
                },
            },
        },
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)
    monkeypatch.setattr(
        app,
        "log_vehicle_state",
        lambda vehicle_id, state: protokoll.append((vehicle_id, state)),
    )

    assert app._fleet_telemetrie_verbindung_aktualisieren(
        "TESTVIN",
        {"Status": "DISCONNECTED", "ConnectionID": "alt"},
        2_100_000,
    )

    assert app.latest_data["veh-1"]["state"] == "online"
    assert protokoll == []


def test_fleet_telemetrie_doppelte_verbindung_sendet_live_nicht(monkeypatch):
    angefordert = []
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktiviert", lambda: True)
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    app._fleet_telemetry_profile_status.update({
        "current": "live",
        "target": "live",
    })
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "online",
            "fleet_telemetry_connectivity": {
                "Status": "CONNECTED",
                "ConnectionId": "gleich",
            },
        },
    })
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)

    assert app._fleet_telemetrie_verbindung_aktualisieren(
        "TESTVIN",
        {"Status": "CONNECTED", "ConnectionId": "gleich"},
        2_100_000,
    )

    assert angefordert == []


def test_fleet_telemetrie_ignoriert_spaeten_abbruch_alter_verbindung(
    monkeypatch,
):
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "online",
            "fleet_telemetry_connectivity": {
                "Status": "CONNECTED",
                "ConnectionId": "neu",
            },
        },
    })

    assert not app._fleet_telemetrie_verbindung_aktualisieren(
        "TESTVIN",
        {"Status": "DISCONNECTED", "ConnectionId": "alt"},
        2_100_000,
    )

    daten = app.latest_data["veh-1"]
    assert daten["state"] == "online"
    assert daten["fleet_telemetry_connectivity"]["ConnectionId"] == "neu"


def test_fleet_telemetrie_neuverbindung_laesst_parkprofil_unveraendert(monkeypatch):
    angefordert = []
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktiviert", lambda: True)
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    app._fleet_telemetry_profile_status.update({
        "current": "parked",
        "target": "parked",
    })
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "offline",
            "fleet_telemetry_connectivity": {
                "Status": "DISCONNECTED",
                "ConnectionID": "alt",
            },
        },
    })
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)

    assert app._fleet_telemetrie_verbindung_aktualisieren(
        "TESTVIN",
        {"Status": "CONNECTED", "ConnectionID": "neu"},
        2_100_000,
    )

    assert angefordert == []
    assert app._fleet_telemetry_profile_status["current"] == "parked"


def test_fleet_telemetrie_neuverbindung_drosselt_live_neuversand(monkeypatch):
    angefordert = []
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktiviert", lambda: True)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_RECONNECT_COOLDOWN_SECONDS",
        10.0,
    )
    app._fleet_telemetry_profile_status.update({
        "current": "live",
        "target": "live",
    })

    assert app._fleet_telemetrie_profile_nach_neuverbindung_vermerken(
        "TESTVIN",
        2100.0,
    )
    assert not app._fleet_telemetrie_profile_nach_neuverbindung_vermerken(
        "TESTVIN",
        2105.0,
    )

    assert angefordert == []
    status = app._fleet_telemetry_profile_status
    assert status["live_reconnect_seen_at"] == 2100.0
    assert app._fleet_telemetrie_profile_neuverbindung_pendelt_sich_ein(
        status,
        2129.9,
    )
    assert not app._fleet_telemetrie_profile_neuverbindung_pendelt_sich_ein(
        status,
        2130.0,
    )


def test_fleet_telemetrie_erwartete_live_plus_neuverbindung_stuft_nicht_zurueck(
    monkeypatch,
):
    angefordert = []
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktiviert", lambda: True)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_ERWARTETE_NEUVERBINDUNG_SECONDS",
        30.0,
    )
    app._fleet_telemetry_profile_status.update({
        "current": "live",
        "target": "live",
        "last_sent": 2095.0,
        "last_sent_profile": "live_extended",
        "config_synced": False,
        "config_sync_state": "pending",
        "config_sync_profile": "live_extended",
    })

    assert app._fleet_telemetrie_profile_nach_neuverbindung_vermerken(
        "TESTVIN",
        2100.0,
    )

    assert angefordert == []
    assert app._fleet_telemetry_profile_status["live_reconnect_seen_at"] == 2100.0
    assert app._fleet_telemetry_profile_status["last_sent_profile"] == (
        "live_extended"
    )


def test_fleet_telemetrie_mqtt_normalisiert_oeffnungen(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
        "id_s": "veh-1",
    }])
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: {})
    monkeypatch.setattr(app, "_save_cached", lambda vehicle_id, data: None)
    monkeypatch.setattr(app, "latest_data", {})

    app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/DoorState",
        (
            b'{"DriverFront": true, "PassengerFront": false, '
            b'"DriverRear": false, "PassengerRear": false, '
            b'"TrunkFront": false, "TrunkRear": true}'
        ),
        {"topic_base": "tesla"},
    )
    app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/FdWindow",
        b'"WindowStateClosed"',
        {"topic_base": "tesla"},
    )
    app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/RpWindow",
        b'"WindowStatePartiallyOpen"',
        {"topic_base": "tesla"},
    )

    vehicle_state = app.latest_data["veh-1"]["vehicle_state"]
    assert vehicle_state["df"] == 1
    assert vehicle_state["pf"] == 0
    assert vehicle_state["rt"] == 1
    assert vehicle_state["fd_window"] == 0
    assert vehicle_state["rp_window"] == 1


def test_fleet_telemetrie_mqtt_stellt_bereinigtes_fenster_wieder_her(monkeypatch):
    gespeicherte_daten = {}

    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
        "id_s": "veh-1",
    }])
    monkeypatch.setattr(
        app,
        "_load_cached",
        lambda vehicle_id: {
            "fleet_telemetry_raw": {
                "FdWindow": "WindowStatePartiallyOpen",
            },
            "vehicle_state": {
                "fd_window": 0,
            },
        },
    )
    monkeypatch.setattr(
        app,
        "_save_cached",
        lambda vehicle_id, data: gespeicherte_daten.setdefault(vehicle_id, data),
    )
    monkeypatch.setattr(app, "latest_data", {})

    app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/FdWindow",
        b'"WindowStatePartiallyOpen"',
        {"topic_base": "tesla"},
    )

    vehicle_state = app.latest_data["veh-1"]["vehicle_state"]
    assert vehicle_state["fd_window"] == 1


def test_fleet_telemetrie_basisdaten_ueberschreibt_alias_id(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
        "id_s": "primaer",
        "vehicle_id": "alias",
        "display_name": "Testauto",
    }])

    daten = app._fleet_telemetrie_basisdaten(
        {"id_s": "alias"},
        "TESTVIN",
        "alias",
        1234567890,
    )

    assert daten["id_s"] == "primaer"


def test_fleet_telemetrie_priorisiert_batterieseitige_ladeenergie():
    daten = {}

    app._fleet_telemetrie_setze_feld(
        daten,
        "ACChargingEnergyIn",
        11.2022222222,
        1_000,
    )
    assert daten["charge_state"]["charge_energy_added"] == 11.2022222222

    app._fleet_telemetrie_setze_feld(
        daten,
        "DCChargingEnergyIn",
        10.9188363036,
        2_000,
    )
    assert daten["charge_state"]["charge_energy_added"] == 10.9188363036

    app._fleet_telemetrie_setze_feld(
        daten,
        "ACChargingEnergyIn",
        11.3,
        3_000,
    )
    assert daten["charge_state"]["charge_energy_added"] == 10.9188363036


def test_fleet_telemetrie_mqtt_mappt_dashboard_zusatzfelder(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
        "id_s": "veh-1",
    }])
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: {})
    monkeypatch.setattr(app, "_save_cached", lambda vehicle_id, data: None)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "reverse_geocode", lambda lat, lon, vehicle_id=None: {})

    nachrichten = {
        "DestinationName": b'"Ziel"',
        "DestinationLocation": b'{"latitude": 51.1, "longitude": 7.1}',
        "ExpectedEnergyPercentAtTripArrival": b"42",
        "MilesToArrival": b"12.5",
        "MinutesToArrival": b"18",
        "RouteTrafficMinutesDelay": b"3",
        "RouteLine": b'"abcdef"',
        "GpsState": b'"GpsStateActive"',
        "DCChargingEnergyIn": b"7.5",
        "DCChargingPower": b"11",
        "DCDCEnable": b"true",
        "ChargeState": b'"Standby"',
        "PackVoltage": b"400",
        "PackCurrent": b"-12.5",
        "ChargeRateMilePerHour": b"24",
        "ChargingCableType": b'"ChargingCableTypeIEC"',
        "TimeToFullCharge": b"1.5",
        "ClimateKeeperMode": b'"ClimateKeeperModeStateParty"',
        "CabinOverheatProtectionMode": b'"CabinOverheatProtectionModeStateOn"',
        "CabinOverheatProtectionTemperatureLimit": b'"ClimateOverheatProtectionTempLimitHigh"',
        "DefrostMode": b'"DefrostModeStateOn"',
        "RearDefrostEnabled": b"true",
        "WiperHeatEnabled": b"true",
        "HvacLeftTemperatureRequest": b"19.0",
        "HvacRightTemperatureRequest": b"20.5",
        "HvacSteeringWheelHeatLevel": b"2",
        "SeatHeaterLeft": b"3",
        "DriverSeatOccupied": b"true",
        "BrakePedal": b"true",
        "BrakePedalPos": b"3.4",
        "PedalPosition": b"12.5",
        "CenterDisplay": b'"DisplayStateOn"',
        "SpeedLimitMode": b'"SpeedLimitModeStateOn"',
        "CurrentLimitMph": b"56",
        "LightsHazardsActive": b"false",
        "LightsTurnSignal": b'"TurnSignalStateLeft"',
        "LightsHighBeams": b"true",
        "SoftwareUpdateVersion": b'"2026.20.1"',
        "SoftwareUpdateDownloadPercentComplete": b"35",
        "SoftwareUpdateExpectedDurationMinutes": b"45",
        "TpmsPressureFl": b"2.9",
        "TpmsSoftWarnings": b'"TireLocationFrontLeft"',
        "MediaNowPlayingTitle": b'"Song"',
        "MediaPlaybackStatus": b'"MediaStatusPlaying"',
    }
    for feld, payload in nachrichten.items():
        assert app._fleet_telemetrie_mqtt_message(
            f"tesla/TESTVIN/v/{feld}",
            payload,
            {"topic_base": "tesla"},
        )

    daten = app.latest_data["veh-1"]
    assert daten["drive_state"]["active_route_destination"] == "Ziel"
    assert daten["drive_state"]["active_route_latitude"] == 51.1
    assert daten["drive_state"]["active_route_energy_at_arrival"] == 42
    assert daten["drive_state"]["active_route_miles_to_arrival"] == 12.5
    assert daten["drive_state"]["active_route_line"] == "abcdef"
    assert daten["drive_state"]["active_route_active"] is True
    assert daten["drive_state"]["gps_state"] == "GpsStateActive"
    assert daten["charge_state"]["charge_energy_added"] == 7.5
    assert daten["charge_state"]["charger_power"] == 11
    assert daten["charge_state"]["charging_state"] == "Disconnected"
    assert daten["charge_state"]["dcdc_enable"] is True
    assert daten["charge_state"]["pack_voltage"] == 400
    assert daten["charge_state"]["pack_current"] == -12.5
    assert daten["charge_state"]["pack_power"] == -5.0
    assert daten["drive_state"]["power"] == 5.0
    assert daten["charge_state"]["charge_rate"] == 24
    assert daten["charge_state"]["conn_charge_cable"] == "IEC"
    assert daten["charge_state"]["minutes_to_full_charge"] == 90
    assert daten["climate_state"]["climate_keeper_mode"] == "camp"
    assert daten["climate_state"]["cabin_overheat_protection"] == "On"
    assert daten["climate_state"]["cop_activation_temperature"] == "High"
    assert daten["climate_state"]["is_front_defroster_on"] is True
    assert daten["climate_state"]["is_rear_defroster_on"] is True
    assert daten["climate_state"]["side_mirror_heaters"] is True
    assert daten["climate_state"]["wiper_blade_heater"] is True
    assert daten["climate_state"]["driver_temp_setting"] == 19.0
    assert daten["climate_state"]["passenger_temp_setting"] == 20.5
    assert daten["climate_state"]["steering_wheel_heater"] is True
    assert daten["climate_state"]["seat_heater_left"] == 3
    assert daten["vehicle_state"]["is_user_present"] is True
    assert daten["vehicle_state"]["brake_pedal"] is True
    assert daten["vehicle_state"]["brake_pedal_pos"] == 3.4
    assert daten["vehicle_state"]["pedal_position"] == 12.5
    assert daten["vehicle_state"]["center_display_state"] == "On"
    assert daten["vehicle_state"]["speed_limit_mode"]["active"] is True
    assert daten["vehicle_state"]["speed_limit_mode"]["current_limit_mph"] == 56
    assert daten["vehicle_state"]["lights_hazards_active"] is False
    assert daten["vehicle_state"]["lights_turn_signal"] == "Left"
    assert daten["vehicle_state"]["lights_high_beams"] is True
    assert daten["vehicle_state"]["software_update"]["version"] == "2026.20.1"
    assert daten["vehicle_state"]["software_update"]["download_perc"] == 35
    assert daten["vehicle_state"]["software_update"]["expected_duration_sec"] == 2700
    assert daten["vehicle_state"]["tpms_pressure_fl"] == 2.9
    assert daten["vehicle_state"]["tpms_soft_warning_fl"] is True
    assert daten["vehicle_state"]["media_info"]["now_playing_title"] == "Song"
    assert daten["vehicle_state"]["media_info"]["media_playback_status"] == "Playing"


def test_fleet_telemetrie_mqtt_batch_default_ist_200_und_stream_latest_only():
    inhalt = pathlib.Path("app.py").read_text(encoding="utf-8")

    assert "FLEET_TELEMETRY_MQTT_BATCH_MAX = max(\n    200," in inhalt
    assert 'os.getenv("TESLA_FLEET_TELEMETRY_MQTT_BATCH_MAX", "200")' in inhalt
    assert "FLEET_TELEMETRY_STREAM_QUEUE_MAX = max(\n    1," in inhalt
    assert 'os.getenv("TESLA_FLEET_TELEMETRY_STREAM_QUEUE_MAX", "1")' in inhalt
    assert "FLEET_TELEMETRY_STREAM_KEEPALIVE_SECONDS = max(" in inhalt
    assert 'os.getenv("TESLA_FLEET_TELEMETRY_STREAM_KEEPALIVE_SECONDS", "0.5")' in inhalt
    assert "FLEET_TELEMETRY_STREAM_MIN_INTERVAL_SECONDS = max(" in inhalt
    assert (
        'os.getenv("TESLA_FLEET_TELEMETRY_STREAM_MIN_INTERVAL_SECONDS", "0.25")'
        in inhalt
    )
    assert "q = eventlet_queue.Queue(maxsize=FLEET_TELEMETRY_STREAM_QUEUE_MAX)" in inhalt


def test_stream_sendet_ungepuffert_und_unkomprimiert(monkeypatch):
    monkeypatch.setattr(app, "_start_thread", lambda vehicle_id: None)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "subscribers", {})

    response = app.app.test_client().get(
        "/stream/veh-1",
        buffered=False,
        headers={"Accept-Encoding": "gzip"},
    )

    try:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["Content-Type"]
        assert response.headers["Cache-Control"] == "no-cache, no-transform"
        assert response.headers["Connection"] == "keep-alive"
        assert response.headers["Content-Encoding"] == "identity"
        assert response.headers["X-Accel-Buffering"] == "no"
        assert next(response.response).decode("utf-8") == ": verbunden\n\n"
    finally:
        response.close()


def test_stream_sendet_sichtbaren_heartbeat(monkeypatch):
    monkeypatch.setattr(app, "_start_thread", lambda vehicle_id: None)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "subscribers", {})
    monkeypatch.setattr(app, "FLEET_TELEMETRY_STREAM_KEEPALIVE_SECONDS", 0.01)

    response = app.app.test_client().get("/stream/veh-1", buffered=False)

    try:
        assert next(response.response).decode("utf-8") == ": verbunden\n\n"
        heartbeat = next(response.response).decode("utf-8")
        assert heartbeat.startswith("event: stream\ndata: ")
        daten = json.loads(heartbeat.split("data: ", 1)[1].strip())
        assert isinstance(daten["stream_heartbeat_at"], int)
    finally:
        response.close()


def test_stream_liefert_subscriber_snapshot_direkt_aus(monkeypatch):
    monkeypatch.setattr(app, "_start_thread", lambda vehicle_id: None)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "subscribers", {})

    response = app.app.test_client().get("/stream/veh-1", buffered=False)

    try:
        assert next(response.response).decode("utf-8") == ": verbunden\n\n"
        assert "veh-1" in app.subscribers

        app._subscriber_daten_senden("veh-1", {
            "fleet_telemetry_received_at": 1234,
            "drive_state": {"speed": 1},
            "vehicle_state": {},
            "charge_state": {},
            "climate_state": {},
        })

        payload = next(response.response).decode("utf-8")
        assert payload.startswith("data: ")
        daten = json.loads(payload.removeprefix("data: ").strip())
        assert daten["fleet_telemetry_received_at"] == 1234
        assert daten["drive_state"]["speed"] == 1
        assert isinstance(daten["stream_sent_at"], int)
    finally:
        response.close()


def test_stream_entfernt_reine_telemetrie_diagnose(monkeypatch):
    monkeypatch.setattr(app, "_start_thread", lambda vehicle_id: None)
    monkeypatch.setattr(app, "subscribers", {})
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "fleet_telemetry_received_at": 1234,
            "fleet_telemetry_raw": {"VehicleSpeed": 12},
            "fleet_telemetry_field_received_at": {"VehicleSpeed": 1234},
            "fleet_telemetry_field_previous_received_at": {"VehicleSpeed": 1000},
            "fleet_telemetry_field_interval_ms": {"VehicleSpeed": 234},
            "fleet_telemetry_last_field": "VehicleSpeed",
            "fleet_telemetry_last_received_field": "VehicleSpeed",
            "drive_state": {"speed": 12},
        },
    })

    response = app.app.test_client().get("/stream/veh-1", buffered=False)

    try:
        assert next(response.response).decode("utf-8") == ": verbunden\n\n"
        payload = next(response.response).decode("utf-8")
        daten = json.loads(payload.removeprefix("data: ").strip())
        assert daten["fleet_telemetry_received_at"] == 1234
        assert daten["drive_state"]["speed"] == 12
        assert isinstance(daten["stream_sent_at"], int)
        for feld in app.FLEET_TELEMETRY_STREAM_DIAGNOSE_FELDER:
            assert feld not in daten
    finally:
        response.close()


def test_streamstart_fordert_kein_telemetrieprofil_an(monkeypatch):
    angefordert = []
    initial = {"drive_state": {}, "path": []}
    monkeypatch.setattr(app, "_start_thread", lambda vehicle_id: None)
    monkeypatch.setattr(app, "latest_data", {"veh-1": initial})
    monkeypatch.setattr(app, "subscribers", {})
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_aktualisieren",
        lambda cache_id, data: angefordert.append((cache_id, data)) or data,
    )

    response = app.app.test_client().get("/stream/veh-1", buffered=False)

    try:
        assert next(response.response).decode("utf-8") == ": verbunden\n\n"
        assert next(response.response).decode("utf-8").startswith("data: ")
        assert angefordert == []
    finally:
        response.close()


def test_subscriber_stream_bekommt_stabile_snapshots(monkeypatch):
    ziel_queue = app.queue.Queue(maxsize=app.FLEET_TELEMETRY_STREAM_QUEUE_MAX)
    daten = {
        "drive_state": {"speed": 1},
        "path": [[51.0, 7.0]],
    }
    monkeypatch.setattr(app, "subscribers", {"veh-1": [ziel_queue]})

    app._subscriber_daten_senden("veh-1", daten)
    daten["drive_state"]["speed"] = 2
    daten["path"].append([51.1, 7.1])

    snapshot = ziel_queue.get_nowait()
    assert snapshot["drive_state"]["speed"] == 1
    assert snapshot["path"] == [[51.0, 7.0]]


def test_subscriber_stream_ersetzt_rueckstand_durch_neuesten_snapshot(monkeypatch):
    ziel_queue = app.queue.Queue(maxsize=1)
    monkeypatch.setattr(app, "subscribers", {"veh-1": [ziel_queue]})

    app._subscriber_daten_senden("veh-1", {"drive_state": {"speed": 1}})
    app._subscriber_daten_senden("veh-1", {"drive_state": {"speed": 2}})

    snapshot = ziel_queue.get_nowait()
    assert snapshot["drive_state"]["speed"] == 2
    assert ziel_queue.empty()


def test_fahrtpfad_nutzt_serverzeit_für_zehn_minuten(monkeypatch):
    parkbeginn = 1_700_000_000_000
    pfad = [[51.0, 7.0], [51.1, 7.1]]
    cache = {"path": pfad}
    daten = {
        "drive_state": {
            "shift_state": "P",
            "timestamp": parkbeginn + 1000,
        },
        "path": pfad,
    }
    monkeypatch.setattr(app, "trip_path", pfad)
    monkeypatch.setattr(app, "current_trip_file", "/tmp/trip.csv")
    monkeypatch.setattr(app, "current_trip_date", "20260725")
    monkeypatch.setattr(app, "trip_path_generation", 7)
    monkeypatch.setattr(app, "drive_pause_ms", parkbeginn)
    monkeypatch.setattr(app, "latest_data", {"veh-1": cache})
    monkeypatch.setattr(
        app.time,
        "time",
        lambda: (
            parkbeginn + app.FAHRTPFAD_NACH_PARKEN_MS
        ) / 1000,
    )

    app.track_drive_path(daten)

    assert app.trip_path == []
    assert daten["path"] == []
    assert cache["path"] == []
    assert app.current_trip_file is None
    assert app.current_trip_date is None
    assert app.trip_path_generation == 8
    assert daten["path_generation"] == 8
    assert cache["path_generation"] == 8


def test_parkzeit_ersetzt_unplausiblen_epoch_wert(monkeypatch):
    parkbeginn = 1_788_038_801_311
    monkeypatch.setattr(app, "park_start_ms", 2_000_000)
    monkeypatch.setattr(app, "last_shift_state", None)
    monkeypatch.setattr(app.time, "time", lambda: (parkbeginn + 60_000) / 1000)

    app.track_park_time(
        {"drive_state": {"shift_state": "P", "timestamp": parkbeginn}}
    )

    assert app.park_start_ms == parkbeginn
    assert app._load_parktime() == parkbeginn


def test_dashboard_gibt_keine_unplausible_parkzeit_aus(monkeypatch):
    monkeypatch.setattr(app, "park_start_ms", 2_000_000)
    daten = {"park_start": 2_000_000}

    app._parkdaten_anreichern(daten)

    assert app.park_start_ms is None
    assert daten["park_start"] is None
    assert daten["park_duration"] is None


def test_dashboard_stellt_parkzeit_waehrend_fahrt_nicht_wieder_her(
    monkeypatch,
):
    alter_parkbeginn = 1_788_038_801_311
    monkeypatch.setattr(app, "park_start_ms", None)
    daten = {
        "park_start": alter_parkbeginn,
        "drive_state": {"shift_state": "D", "speed": 25},
    }

    app._parkdaten_anreichern(daten)

    assert app.park_start_ms is None
    assert daten["park_start"] is None
    assert daten["park_duration"] is None
    assert not pathlib.Path(app.PARKTIME_FILE).exists()


def test_fahrtpfad_wird_waehrend_fahrt_nicht_nach_parkzeit_geloescht(
    monkeypatch,
):
    jetzt_ms = 1_788_100_000_000
    alter_parkbeginn = jetzt_ms - app.FAHRTPFAD_NACH_PARKEN_MS - 60_000
    pfad = [[51.0, 7.0], [51.1, 7.1]]
    daten = {
        "drive_state": {"shift_state": "D", "speed": 30},
        "park_start": alter_parkbeginn,
        "path": pfad,
    }
    monkeypatch.setattr(app, "trip_path", pfad)
    monkeypatch.setattr(app, "drive_pause_ms", None)
    monkeypatch.setattr(app, "park_start_ms", alter_parkbeginn)
    monkeypatch.setattr(app, "trip_path_generation", 12)

    geändert = app._fahrtpfad_nach_parkzeit_bereinigen(daten, jetzt_ms)

    assert geändert is False
    assert app.trip_path == pfad
    assert daten["path"] == pfad
    assert app.trip_path_generation == 12


def test_fahrtpfad_worker_bereinigt_ohne_telemetrie_oder_browser(monkeypatch):
    parkbeginn = 1_788_100_000_000
    pfad = [[51.0, 7.0], [51.1, 7.1]]
    fahrzeug = {
        "drive_state": {"shift_state": "P", "speed": 0},
        "fleet_telemetry_updated_at": parkbeginn,
        "park_start": parkbeginn,
        "path": pfad,
    }
    standard = {
        "drive_state": {"shift_state": "P", "speed": 0},
        "fleet_telemetry_updated_at": parkbeginn + 1000,
        "park_start": parkbeginn,
        "path": pfad,
    }
    gespeichert = []
    gesendet = []
    monkeypatch.setattr(app, "trip_path", pfad)
    monkeypatch.setattr(app, "current_trip_file", "/tmp/trip.csv")
    monkeypatch.setattr(app, "current_trip_date", "20260830")
    monkeypatch.setattr(app, "trip_path_generation", 20)
    monkeypatch.setattr(app, "drive_pause_ms", parkbeginn)
    monkeypatch.setattr(
        app,
        "latest_data",
        {"veh-1": fahrzeug, "default": standard},
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda cache_id, data: gespeichert.append((cache_id, list(data["path"]))),
    )
    monkeypatch.setattr(
        app,
        "_subscriber_daten_senden",
        lambda cache_id, data: gesendet.append((cache_id, list(data["path"]))),
    )

    geändert = app._fleet_telemetrie_fahrtpfad_bereinigungs_tick(
        parkbeginn + app.FAHRTPFAD_NACH_PARKEN_MS
    )

    assert geändert is True
    assert app.trip_path == []
    assert app.current_trip_file is None
    assert app.current_trip_date is None
    assert app.trip_path_generation == 21
    assert fahrzeug["path"] == []
    assert standard["path"] == []
    assert gespeichert == [("veh-1", []), ("default", [])]
    assert gesendet == [("veh-1", []), ("default", [])]


def test_fahrtpfad_worker_loescht_nicht_bei_frischer_fahrbewegung(monkeypatch):
    jetzt_ms = 1_788_100_700_000
    parkbeginn = jetzt_ms - app.FAHRTPFAD_NACH_PARKEN_MS
    pfad = [[51.0, 7.0], [51.1, 7.1]]
    geparkt = {
        "drive_state": {"shift_state": "P", "speed": 0},
        "fleet_telemetry_updated_at": jetzt_ms - 5000,
        "park_start": parkbeginn,
        "path": pfad,
    }
    fahrend = {
        "drive_state": {"shift_state": "D", "speed": 20},
        "fleet_telemetry_updated_at": jetzt_ms,
        "park_start": parkbeginn,
        "path": pfad,
    }
    monkeypatch.setattr(app, "trip_path", pfad)
    monkeypatch.setattr(app, "trip_path_generation", 30)
    monkeypatch.setattr(app, "drive_pause_ms", parkbeginn)
    monkeypatch.setattr(
        app,
        "latest_data",
        {"default": geparkt, "veh-1": fahrend},
    )

    geändert = app._fleet_telemetrie_fahrtpfad_bereinigungs_tick(jetzt_ms)

    assert geändert is False
    assert app.trip_path == pfad
    assert app.trip_path_generation == 30


def test_fahrtpfad_worker_prueft_auch_ohne_neue_ereignisse(monkeypatch):
    aufrufe = []
    aktiv = iter((True, False))
    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: next(aktiv))
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_fahrtpfad_bereinigungs_tick",
        lambda: aufrufe.append("tick"),
    )
    monkeypatch.setattr(
        app.time,
        "sleep",
        lambda sekunden: aufrufe.append(sekunden),
    )

    app._fleet_telemetrie_fahrtpfad_worker_loop()

    assert aufrufe == ["tick", app.FLEET_TELEMETRY_TRIP_PATH_CLEANUP_SECONDS]


def test_fahrtpfad_wird_nach_neustart_aus_tagesdatei_geladen(
    monkeypatch,
    tmp_path,
):
    timestamp = 1_788_092_900_000
    datum = datetime.fromtimestamp(timestamp / 1000, app.LOCAL_TZ).strftime(
        "%Y%m%d"
    )
    verzeichnis = tmp_path / "trips"
    verzeichnis.mkdir()
    datei = verzeichnis / f"trip_{datum}.csv"
    datei.write_text(
        "1788092000000,51.0,7.0,20,4,90,D\n"
        "1788092100000,51.1,7.1,0,0,90,P\n"
        "1788092800000,51.2,7.2,5,2,90,R\n"
        "1788092900000,51.3,7.3,25,8,90,D\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(app, "trip_dir", lambda _vid: str(verzeichnis))
    monkeypatch.setattr(app, "trip_path", [])
    monkeypatch.setattr(app, "current_trip_file", None)
    monkeypatch.setattr(app, "current_trip_date", None)
    monkeypatch.setattr(app, "drive_pause_ms", None)
    daten = {
        "id_s": "veh-1",
        "drive_state": {
            "shift_state": "D",
            "timestamp": timestamp,
            "latitude": 51.4,
            "longitude": 7.4,
            "speed": 30,
        },
    }

    app.track_drive_path(daten)

    assert app.trip_path == [[51.2, 7.2], [51.3, 7.3], [51.4, 7.4]]
    assert app.current_trip_file == str(datei)
    assert app.current_trip_date == datum


def test_stream_setzt_fahrtpfad_ohne_neue_telemetrie_zurück(monkeypatch):
    parkbeginn = 1_700_000_000_000
    jetzt = [parkbeginn + app.FAHRTPFAD_NACH_PARKEN_MS - 1000]
    pfad = [[51.0, 7.0], [51.1, 7.1]]
    daten = {
        "drive_state": {
            "shift_state": "P",
            "timestamp": parkbeginn,
        },
        "park_start": parkbeginn,
        "path": pfad,
    }
    monkeypatch.setattr(app, "_start_thread", lambda vehicle_id: None)
    monkeypatch.setattr(app, "trip_path", pfad)
    monkeypatch.setattr(app, "current_trip_file", "/tmp/trip.csv")
    monkeypatch.setattr(app, "current_trip_date", "20260725")
    monkeypatch.setattr(app, "trip_path_generation", 11)
    monkeypatch.setattr(app, "drive_pause_ms", None)
    monkeypatch.setattr(app, "park_start_ms", parkbeginn)
    monkeypatch.setattr(app, "latest_data", {"veh-1": daten})
    monkeypatch.setattr(app, "subscribers", {})
    monkeypatch.setattr(app.time, "time", lambda: jetzt[0] / 1000)

    response = app.app.test_client().get("/stream/veh-1", buffered=False)

    try:
        assert next(response.response).decode("utf-8") == ": verbunden\n\n"
        initial = json.loads(
            next(response.response).decode("utf-8").removeprefix("data: ")
        )
        assert initial["path"] == pfad

        jetzt[0] = parkbeginn + app.FAHRTPFAD_NACH_PARKEN_MS
        reset = json.loads(
            next(response.response).decode("utf-8").removeprefix("data: ")
        )

        assert reset["path_reset"] is True
        assert reset["path"] == []
        assert reset["path_generation"] == 12
        assert app.trip_path == []
    finally:
        response.close()


def test_stream_erkennt_neuen_fahrtpfad_auch_bei_gleicher_punktzahl(
    monkeypatch,
):
    alter_pfad = [[51.0, 7.0], [51.1, 7.1]]
    neuer_pfad = [[52.0, 8.0], [52.1, 8.1]]
    initial = {
        "drive_state": {"shift_state": "D"},
        "path": alter_pfad,
        "path_generation": 4,
    }
    monkeypatch.setattr(app, "_start_thread", lambda vehicle_id: None)
    monkeypatch.setattr(
        app,
        "_fahrtpfad_nach_parkzeit_bereinigen",
        lambda _daten: False,
    )
    monkeypatch.setattr(app, "latest_data", {"veh-1": initial})
    monkeypatch.setattr(app, "subscribers", {})

    response = app.app.test_client().get("/stream/veh-1", buffered=False)

    try:
        assert next(response.response).decode("utf-8") == ": verbunden\n\n"
        erstes_payload = json.loads(
            next(response.response).decode("utf-8").removeprefix("data: ")
        )
        assert erstes_payload["path"] == alter_pfad

        app._subscriber_daten_senden(
            "veh-1",
            {
                "drive_state": {"shift_state": "D"},
                "path": neuer_pfad,
                "path_generation": 5,
            },
        )
        neuer_streamstand = json.loads(
            next(response.response).decode("utf-8").removeprefix("data: ")
        )

        assert neuer_streamstand["path_reset"] is True
        assert neuer_streamstand["path"] == neuer_pfad
        assert neuer_streamstand["path_generation"] == 5
        assert "path_delta" not in neuer_streamstand
    finally:
        response.close()


def test_fleet_telemetrie_adressauflösung_blockiert_livepfad_nicht(monkeypatch):
    geplant = []
    monkeypatch.setattr(app, "address_cache", {})
    monkeypatch.setattr(app, "track_park_time", lambda data: None)
    monkeypatch.setattr(app, "park_duration_string", lambda _start: "")
    monkeypatch.setattr(app, "track_drive_path", lambda data: None)
    monkeypatch.setattr(app, "trip_path", [])
    monkeypatch.setattr(
        app,
        "reverse_geocode",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Reverse-Geocode darf den Live-Pfad nicht blockieren")
        ),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_adresse_spaeter_aktualisieren",
        lambda cache_id, lat, lon: geplant.append((cache_id, lat, lon)),
    )
    daten = {
        "drive_state": {"latitude": 51.0, "longitude": 7.0},
        "charge_state": {},
        "vehicle_state": {},
        "climate_state": {},
    }

    app._fleet_telemetrie_dashboard_daten_anreichern("veh-1", daten)

    assert geplant == [("veh-1", 51.0, 7.0)]


def test_fleet_telemetrie_adress_worker_sendet_spaetes_update(monkeypatch):
    ziel_queue = app.queue.Queue(maxsize=1)
    monkeypatch.setattr(app, "address_cache", {})
    monkeypatch.setattr(app, "subscribers", {"veh-1": [ziel_queue]})
    monkeypatch.setattr(
        app,
        "latest_data",
        {"veh-1": {"drive_state": {"latitude": 51.0, "longitude": 7.0}}},
    )

    assert app._fleet_telemetrie_adresse_uebernehmen(
        "veh-1",
        51.0,
        7.0,
        {"address": "Teststraße 1, 45143 Essen"},
    )

    snapshot = ziel_queue.get_nowait()
    assert snapshot["location_address"] == "Teststraße 1, 45143 Essen"
    assert app.address_cache["veh-1"]["address"] == "Teststraße 1, 45143 Essen"


def test_fleet_telemetrie_verwirft_ungueltige_navigationskoordinaten():
    daten = {
        "drive_state": {
            "active_route_latitude": 51.1,
            "active_route_longitude": 7.1,
        }
    }

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "DestinationLocation",
        {"latitude": 0, "longitude": 7.1},
        1234,
    )

    drive = daten["drive_state"]
    assert "active_route_latitude" not in drive
    assert "active_route_longitude" not in drive
    assert drive["timestamp"] == 1234


def test_fleet_telemetrie_verwirft_nicht_endliche_navigationskoordinaten():
    daten = {"drive_state": {}}

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "DestinationLocation",
        {"latitude": float("nan"), "longitude": 7.1},
        1234,
    )

    drive = daten["drive_state"]
    assert "active_route_latitude" not in drive
    assert "active_route_longitude" not in drive


def test_fleet_telemetrie_navigation_beendet_loescht_kartendaten():
    daten = {
        "fleet_telemetry_raw": {
            "DestinationName": "Ziel",
            "RouteLine": "abcdef",
        },
        "drive_state": {
            "active_route_active": True,
            "active_route_destination": "Ziel",
            "active_route_latitude": 51.1,
            "active_route_longitude": 7.1,
            "active_route_energy_at_arrival": 42,
            "active_route_miles_to_arrival": 12.5,
            "active_route_minutes_to_arrival": 18,
            "active_route_traffic_minutes_delay": 3,
            "active_route_line": "abcdef",
        }
    }

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "DestinationName",
        None,
        1234,
    )

    drive = daten["drive_state"]
    for feld in app.FLEET_TELEMETRIE_NAVIGATIONSFELDER:
        assert feld not in drive
    assert drive["active_route_active"] is False
    assert drive["active_route_ended_at"] == 1234
    assert "DestinationName" not in daten["fleet_telemetry_raw"]
    assert "RouteLine" not in daten["fleet_telemetry_raw"]


def test_fleet_telemetrie_alte_routeline_nach_navigationsende_ignoriert():
    daten = {
        "drive_state": {
            "active_route_active": False,
            "active_route_ended_at": 1234,
        }
    }

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "RouteLine",
        "abcdef",
        1240,
    )

    drive = daten["drive_state"]
    assert "active_route_line" not in drive
    assert drive["active_route_active"] is False


def test_fleet_telemetrie_zieht_frische_routeline_nach():
    daten = {
        "fleet_telemetry_raw": {"RouteLine": "abcdef"},
        "fleet_telemetry_field_received_at": {"RouteLine": 1200},
        "drive_state": {
            "active_route_active": False,
            "active_route_ended_at": 1000,
        },
    }

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "DestinationName",
        "Ziel",
        1210,
    )

    drive = daten["drive_state"]
    assert drive["active_route_active"] is True
    assert drive["active_route_destination"] == "Ziel"
    assert drive["active_route_line"] == "abcdef"


def test_fleet_telemetrie_zieht_alte_routeline_nicht_nach():
    daten = {
        "fleet_telemetry_raw": {"RouteLine": "abcdef"},
        "fleet_telemetry_field_received_at": {"RouteLine": 1200},
        "drive_state": {},
    }

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "DestinationName",
        "Ziel",
        1200 + app.FLEET_TELEMETRIE_NAVIGATION_ROUTE_LINE_MAX_ALTER_MS + 1,
    )

    drive = daten["drive_state"]
    assert drive["active_route_active"] is True
    assert drive["active_route_destination"] == "Ziel"
    assert "active_route_line" not in drive


def test_fleet_telemetrie_zieht_auch_passende_alte_routeline_nicht_nach():
    polyline = "_}hfaB_{fjL~oR_pR~oR_pR"
    daten = {
        "fleet_telemetry_raw": {"RouteLine": _routeline_protobuf(polyline)},
        "fleet_telemetry_field_received_at": {"RouteLine": 1200},
        "drive_state": {
            "latitude": 51.49,
            "longitude": 7.01,
            "active_route_active": False,
        },
    }
    timestamp = 1200 + app.FLEET_TELEMETRIE_NAVIGATION_ROUTE_LINE_MAX_ALTER_MS + 1

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "DestinationLocation",
        {"latitude": 51.48, "longitude": 7.02},
        timestamp,
    )

    drive = daten["drive_state"]
    assert drive["active_route_active"] is False
    assert "active_route_line" not in drive


def test_fleet_telemetrie_zieht_fremde_alte_routeline_nicht_nach():
    polyline = "_}hfaB_{fjL~oR_pR~oR_pR"
    daten = {
        "fleet_telemetry_raw": {"RouteLine": _routeline_protobuf(polyline)},
        "fleet_telemetry_field_received_at": {"RouteLine": 1200},
        "drive_state": {
            "latitude": 51.8,
            "longitude": 7.8,
            "active_route_active": False,
        },
    }
    timestamp = 1200 + app.FLEET_TELEMETRIE_NAVIGATION_ROUTE_LINE_MAX_ALTER_MS + 1

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "DestinationLocation",
        {"latitude": 51.9, "longitude": 7.9},
        timestamp,
    )

    drive = daten["drive_state"]
    assert drive["active_route_active"] is False
    assert "active_route_line" not in drive


def test_fleet_telemetrie_letzte_zielkoordinate_aktiviert_navigation_nicht(
    monkeypatch,
):
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(app, "_load_cached", lambda cache_id: {})
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)
    monkeypatch.setattr(app, "_aprs_spaeter_senden", lambda *args: None)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_aktualisieren",
        lambda cache_id, data: data,
    )
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "online",
            "vin": "TESTVIN",
            "drive_state": {
                "active_route_active": False,
                "active_route_ended_at": 1900,
            },
        },
    })

    assert app._fleet_telemetrie_v_felder_aktualisieren(
        "TESTVIN",
        [
            ("MilesToArrival", None, 2000),
            ("ExpectedEnergyPercentAtTripArrival", 90, 2000),
            ("DestinationName", None, 2000),
            ("MinutesToArrival", None, 2000),
            ("DestinationLocation", {
                "latitude": 51.455719,
                "longitude": 7.033862,
            }, 2000),
        ],
    )

    daten = app.latest_data["veh-1"]
    drive = daten["drive_state"]
    assert drive["active_route_active"] is False
    assert drive["active_route_ended_at"] == 2000
    assert "active_route_latitude" not in drive
    assert "active_route_longitude" not in drive
    assert "DestinationLocation" not in daten["fleet_telemetry_raw"]


def test_fleet_telemetrie_nullwerte_am_ziel_beenden_navigation(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(app, "_load_cached", lambda cache_id: {})
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)
    monkeypatch.setattr(app, "_aprs_spaeter_senden", lambda *args: None)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_aktualisieren",
        lambda cache_id, data: data,
    )
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "online",
            "vin": "TESTVIN",
            "fleet_telemetry_raw": {
                "DestinationName": "Altes Ziel",
                "DestinationLocation": {
                    "latitude": 51.455404,
                    "longitude": 6.997049,
                },
                "MilesToArrival": 0.1,
                "MinutesToArrival": 1,
            },
            "drive_state": {
                "shift_state": "D",
                "active_route_active": True,
                "active_route_destination": "Altes Ziel",
                "active_route_latitude": 51.455404,
                "active_route_longitude": 6.997049,
                "active_route_miles_to_arrival": 0.1,
                "active_route_minutes_to_arrival": 1,
            },
        },
    })

    assert app._fleet_telemetrie_v_felder_aktualisieren(
        "TESTVIN",
        [
            ("DestinationName", None, 2000),
            ("DestinationLocation", {
                "latitude": 51.455404,
                "longitude": 6.997049,
            }, 2000),
            ("ExpectedEnergyPercentAtTripArrival", 87, 2000),
            ("MilesToArrival", 0, 2000),
            ("MinutesToArrival", 0, 2000),
            ("RouteTrafficMinutesDelay", 0, 2000),
        ],
    )

    daten = app.latest_data["veh-1"]
    drive = daten["drive_state"]
    assert drive["active_route_active"] is False
    assert drive["active_route_ended_at"] == 2000
    assert "active_route_latitude" not in drive
    assert "active_route_longitude" not in drive
    assert not any(
        feld in daten["fleet_telemetry_raw"]
        for feld in app.FLEET_TELEMETRIE_NAVIGATIONS_ROHFELDER
    )


def test_fleet_telemetrie_entpackt_base64_protobuf_routeline():
    polyline = "{wrcaBczhlLr@fZbWc@TcOF{Sd@"
    routeline = _routeline_protobuf(polyline)
    daten = {
        "drive_state": {
            "active_route_active": True,
            "active_route_destination": "Ziel",
        },
    }

    assert app._fleet_telemetrie_routeline_normalisieren(routeline) == polyline
    assert app._fleet_telemetrie_routeline_normalisieren(polyline) == polyline
    assert app._fleet_telemetrie_setze_feld(
        daten,
        "RouteLine",
        routeline,
        1234,
    )

    drive = daten["drive_state"]
    assert drive["active_route_line"] == polyline
    assert drive["active_route_active"] is True


def test_fleet_telemetrie_entpackt_offizielle_base64_polyline():
    polyline = "_}hfaB_{fjL~oR_pR~oR_pR"
    routeline = base64.b64encode(polyline.encode("ascii")).decode("ascii")

    assert app._fleet_telemetrie_routeline_normalisieren(routeline) == polyline
    assert app._fleet_telemetrie_polyline_dekodieren(polyline) == [
        (51.5, 7.0),
        (51.49, 7.01),
        (51.48, 7.02),
    ]


def test_fleet_telemetrie_routeline_teilnachricht_behaelt_vollstaendige_route():
    polyline = "_}hfaB_{fjL~oR_pR~oR_pR"
    teilnachricht = "EgUNwp6MQRIHDeFzjEEQARIFDQo3fEESBw3B1HhBEAE="
    daten = {
        "fleet_telemetry_raw": {"RouteLine": polyline},
        "drive_state": {
            "active_route_active": True,
            "active_route_destination": "Ziel",
            "active_route_line": polyline,
        },
    }

    assert app._fleet_telemetrie_routeline_ist_teilnachricht(teilnachricht)
    assert app._fleet_telemetrie_setze_feld(
        daten,
        "RouteLine",
        teilnachricht,
        2000,
    )

    assert daten["drive_state"]["active_route_line"] == polyline
    assert daten["fleet_telemetry_raw"]["RouteLine"] == polyline


def test_fleet_telemetrie_passende_route_wird_nach_kurzer_pause_wiederverwendet():
    polyline = "_}hfaB_{fjL~oR_pR~oR_pR"
    teilnachricht = "EgUNwp6MQRIHDeFzjEEQARIFDQo3fEESBw3B1HhBEAE="
    daten = {
        "drive_state": {
            "latitude": 51.49,
            "longitude": 7.01,
            "active_route_active": True,
            "active_route_destination": "Ziel",
            "active_route_latitude": 51.48,
            "active_route_longitude": 7.02,
        },
    }

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "RouteLine",
        _routeline_protobuf(polyline),
        1000,
    )
    assert app._fleet_telemetrie_setze_feld(
        daten,
        "DestinationName",
        None,
        1100,
    )
    assert app._fleet_telemetrie_setze_feld(
        daten,
        "DestinationLocation",
        {"latitude": 51.48, "longitude": 7.02},
        1200,
    )
    assert app._fleet_telemetrie_setze_feld(
        daten,
        "DestinationName",
        "Ziel",
        1200,
    )
    assert app._fleet_telemetrie_setze_feld(
        daten,
        "RouteLine",
        teilnachricht,
        1300,
    )

    drive = daten["drive_state"]
    assert drive["active_route_active"] is True
    assert drive["active_route_line"] == polyline
    assert daten["fleet_telemetry_raw"]["RouteLine"] == polyline


def test_fleet_telemetrie_fremde_route_wird_nicht_wiederverwendet():
    polyline = "_}hfaB_{fjL~oR_pR~oR_pR"
    teilnachricht = "EgUNwp6MQRIHDeFzjEEQARIFDQo3fEESBw3B1HhBEAE="
    daten = {
        "fleet_telemetry_raw": {
            app.FLEET_TELEMETRIE_NAVIGATION_ROUTE_CACHE_ROHFELD: {
                "polyline": polyline,
                "destination": "Altes Ziel",
                "latitude": 51.48,
                "longitude": 7.02,
                "received_at": 1000,
            },
        },
        "drive_state": {
            "latitude": 51.49,
            "longitude": 7.01,
            "active_route_active": True,
            "active_route_destination": "Neues Ziel",
            "active_route_latitude": 51.58,
            "active_route_longitude": 7.12,
        },
    }

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "RouteLine",
        teilnachricht,
        1300,
    )

    assert "active_route_line" not in daten["drive_state"]


def test_fleet_telemetrie_raeumlich_fremde_route_wird_nicht_wiederverwendet():
    polyline = "_}hfaB_{fjL~oR_pR~oR_pR"
    teilnachricht = "EgUNwp6MQRIHDeFzjEEQARIFDQo3fEESBw3B1HhBEAE="
    daten = {
        "fleet_telemetry_raw": {
            app.FLEET_TELEMETRIE_NAVIGATION_ROUTE_CACHE_ROHFELD: {
                "polyline": polyline,
                "destination": "Ziel",
                "latitude": 51.48,
                "longitude": 7.02,
                "received_at": 1000,
            },
        },
        "drive_state": {
            "latitude": 52.5,
            "longitude": 8.0,
            "active_route_active": True,
            "active_route_destination": "Ziel",
            "active_route_latitude": 51.48,
            "active_route_longitude": 7.02,
        },
    }

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "RouteLine",
        teilnachricht,
        1300,
    )

    assert "active_route_line" not in daten["drive_state"]


def test_fleet_telemetrie_bereinigt_alte_navigation_aus_cache():
    daten = {
        "timestamp": 1200,
        "drive_state": {
            "timestamp": 1234,
            "active_route_line": "abcdef",
            "active_route_latitude": 51.1,
            "active_route_longitude": 7.1,
        },
    }

    assert app._fleet_telemetrie_navigation_cache_bereinigen(daten)

    drive = daten["drive_state"]
    assert "active_route_line" not in drive
    assert "active_route_latitude" not in drive
    assert "active_route_longitude" not in drive
    assert drive["active_route_active"] is False
    assert drive["active_route_ended_at"] == 1234


def test_fleet_telemetrie_gang_p_beendet_navigation_und_rohcache():
    daten = {
        "fleet_telemetry_raw": {
            "DestinationLocation": {"latitude": 51.1, "longitude": 7.1},
            "DestinationName": "Ziel",
            "RouteLine": "abcdef",
        },
        "drive_state": {
            "active_route_active": True,
            "active_route_destination": "Ziel",
            "active_route_latitude": 51.1,
            "active_route_longitude": 7.1,
            "active_route_line": "abcdef",
        },
    }

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "Gear",
        "ShiftStateP",
        2000,
    )

    drive = daten["drive_state"]
    assert drive["shift_state"] == "P"
    assert drive["active_route_active"] is False
    assert drive["active_route_ended_at"] == 2000
    assert "active_route_destination" not in drive
    assert "active_route_line" not in drive
    assert daten["fleet_telemetry_raw"] == {"Gear": "ShiftStateP"}


def test_fleet_telemetrie_gang_p_gewinnt_im_gleichen_datenpaket(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(app, "_load_cached", lambda cache_id: {})
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)
    monkeypatch.setattr(app, "_aprs_spaeter_senden", lambda *args: None)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "online",
            "vin": "TESTVIN",
            "fleet_telemetry_raw": {"Gear": "ShiftStateD"},
            "drive_state": {
                "shift_state": "D",
                "active_route_active": True,
                "active_route_destination": "Altes Ziel",
                "active_route_line": "abcdef",
            },
        },
    })

    assert app._fleet_telemetrie_v_felder_aktualisieren(
        "TESTVIN",
        [
            ("Gear", "ShiftStateP", 2000),
            ("DestinationName", "Neues Ziel", 2000),
            ("RouteLine", "ghijkl", 2000),
        ],
    )

    daten = app.latest_data["veh-1"]
    drive = daten["drive_state"]
    assert drive["shift_state"] == "P"
    assert drive["active_route_active"] is False
    assert "active_route_destination" not in drive
    assert "active_route_line" not in drive
    assert "DestinationName" not in daten["fleet_telemetry_raw"]
    assert "RouteLine" not in daten["fleet_telemetry_raw"]


def test_fleet_telemetrie_unveraendertes_p_beendet_neue_navigation_nicht(
    monkeypatch,
):
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(app, "_load_cached", lambda cache_id: {})
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)
    monkeypatch.setattr(app, "_aprs_spaeter_senden", lambda *args: None)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "online",
            "vin": "TESTVIN",
            "fleet_telemetry_raw": {
                "DestinationName": "Neues Ziel",
                "Gear": "ShiftStateP",
                "RouteLine": "abcdef",
            },
            "drive_state": {
                "shift_state": "P",
                "active_route_active": True,
                "active_route_destination": "Neues Ziel",
                "active_route_line": "abcdef",
            },
        },
    })

    assert app._fleet_telemetrie_v_felder_aktualisieren(
        "TESTVIN",
        [("Gear", "ShiftStateP", 3000)],
    )

    drive = app.latest_data["veh-1"]["drive_state"]
    assert drive["shift_state"] == "P"
    assert drive["active_route_active"] is True
    assert drive["active_route_destination"] == "Neues Ziel"
    assert drive["active_route_line"] == "abcdef"


def test_fleet_telemetrie_neues_ziel_verwirft_vorherige_routenlinie():
    daten = {
        "fleet_telemetry_raw": {
            "RouteLine": "abcdef",
        },
        "fleet_telemetry_field_received_at": {"RouteLine": 1999},
        "drive_state": {
            "active_route_active": True,
            "active_route_destination": "Altes Ziel",
            "active_route_latitude": 51.1,
            "active_route_longitude": 7.1,
            "active_route_line": "abcdef",
        },
    }

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "DestinationLocation",
        {"latitude": 51.2, "longitude": 7.2},
        2000,
    )

    drive = daten["drive_state"]
    assert drive["active_route_active"] is True
    assert drive["active_route_latitude"] == 51.2
    assert drive["active_route_longitude"] == 7.2
    assert "active_route_line" not in drive
    assert "RouteLine" not in daten["fleet_telemetry_raw"]


def test_fleet_telemetrie_neues_ziel_behaelt_gleichzeitig_empfangene_route():
    daten = {
        "fleet_telemetry_raw": {
            "RouteLine": "neue-route",
        },
        "fleet_telemetry_field_received_at": {"RouteLine": 2000},
        "drive_state": {
            "active_route_active": True,
            "active_route_destination": "Altes Ziel",
            "active_route_latitude": 51.1,
            "active_route_longitude": 7.1,
            "active_route_line": "neue-route",
        },
    }

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "DestinationLocation",
        {"latitude": 51.2, "longitude": 7.2},
        2000,
    )

    drive = daten["drive_state"]
    assert drive["active_route_active"] is True
    assert drive["active_route_latitude"] == 51.2
    assert drive["active_route_longitude"] == 7.2
    assert drive["active_route_line"] == "neue-route"
    assert daten["fleet_telemetry_raw"]["RouteLine"] == "neue-route"


def test_fleet_telemetrie_beendet_navigation_nach_längerem_offline(monkeypatch):
    monkeypatch.setattr(app.time, "time", lambda: 1_800_000_301.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_PARK_DELAY_SECONDS",
        120.0,
    )
    daten = {
        "state": "offline",
        "state_since_ms": 1_800_000_000_000,
        "timestamp": 1_800_000_000_000,
        "fleet_telemetry_raw": {
            "DestinationName": "Ziel",
            "RouteLine": "abcdef",
        },
        "drive_state": {
            "active_route_active": True,
            "active_route_destination": "Ziel",
            "active_route_line": "abcdef",
        },
    }

    app._fleet_telemetrie_navigation_cache_bereinigen(daten)

    drive = daten["drive_state"]
    assert drive["active_route_active"] is False
    assert "active_route_destination" not in drive
    assert "active_route_line" not in drive
    assert daten["fleet_telemetry_raw"] == {}


def test_fleet_telemetrie_reichert_tpms_und_spiegel_aus_rohdaten_an():
    daten = {
        "fleet_telemetry_raw": {
            "TpmsPressureFl": 2.95,
            "TpmsLastSeenPressureTimeFl": 1781412111,
            "RearDefrostEnabled": True,
        },
        "vehicle_state": {},
        "climate_state": {
            "is_rear_defroster_on": False,
            "side_mirror_heaters": False,
        },
    }

    app._fleet_telemetrie_rohdaten_anreichern(daten)

    assert daten["vehicle_state"]["tpms_pressure_fl"] == 2.95
    assert daten["vehicle_state"]["tpms_last_seen_pressure_time_fl"] == 1781412111000
    assert daten["climate_state"]["is_rear_defroster_on"] is True
    assert daten["climate_state"]["side_mirror_heaters"] is True


def test_fleet_telemetrie_reichert_ungültige_scheibenheizung_als_unbekannt_an():
    daten = {
        "fleet_telemetry_raw": {
            "RearDefrostEnabled": {"invalid": True},
        },
        "climate_state": {
            "is_rear_defroster_on": True,
            "side_mirror_heaters": True,
        },
    }

    app._fleet_telemetrie_rohdaten_anreichern(daten)

    assert daten["climate_state"]["is_rear_defroster_on"] is None
    assert daten["climate_state"]["side_mirror_heaters"] is None


def test_fleet_telemetrie_reichert_lüfterstufe_null_aus_rohdaten_an():
    daten = {
        "fleet_telemetry_raw": {
            "HvacFanSpeed": 0,
        },
        "climate_state": {
            "is_climate_on": False,
            "fan_status": None,
        },
    }

    app._fleet_telemetrie_rohdaten_anreichern(daten)

    assert daten["climate_state"]["fan_status"] == 0


def test_api_liefert_lüfterstufe_null_aus_geladenem_cache(monkeypatch):
    daten = {
        "fleet_telemetry_raw": {
            "HvacFanSpeed": 0,
        },
        "climate_state": {
            "is_climate_on": False,
            "fan_status": None,
        },
    }
    monkeypatch.setattr(app, "_start_thread", lambda vehicle_id: None)
    monkeypatch.setattr(app, "latest_data", {"default": daten})

    response = app.app.test_client().get("/api/data")

    assert response.status_code == 200
    assert response.get_json()["climate_state"]["fan_status"] == 0


def test_stream_liefert_lüfterstufe_null_aus_geladenem_cache():
    daten = {
        "fleet_telemetry_raw": {
            "HvacFanSpeed": 0,
        },
        "climate_state": {
            "is_climate_on": False,
            "fan_status": None,
        },
    }

    payload = app._subscriber_stream_payload(daten)

    assert payload["climate_state"]["fan_status"] == 0
    assert daten["climate_state"]["fan_status"] is None


def test_fleet_telemetrie_reichert_tpms_sollwerte_aus_schwester_cache_an(monkeypatch):
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_ids",
        lambda vin: ["default", "veh-1"],
    )
    monkeypatch.setattr(
        app,
        "latest_data",
        {
            "default": {
                "vin": "VIN1",
                "vehicle_state": {
                    "tpms_rcp_front_value": 3.1,
                    "tpms_rcp_rear_value": 3.2,
                },
            },
        },
    )
    daten = {
        "vin": "VIN1",
        "id_s": "veh-1",
        "vehicle_state": {
            "tpms_pressure_fl": 3.0,
            "tpms_pressure_rl": 3.05,
        },
    }

    app._fleet_telemetrie_tpms_sollwerte_ergänzen("veh-1", daten)

    assert daten["vehicle_state"]["tpms_rcp_front_value"] == 3.1
    assert daten["vehicle_state"]["tpms_rcp_rear_value"] == 3.2


def test_fleet_telemetrie_erhaelt_tpms_druck_bei_ungueltigem_update(monkeypatch):
    gespeicherte_daten = []

    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["veh-1"])
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: {})
    monkeypatch.setattr(
        app,
        "_save_cached",
        lambda vehicle_id, data: gespeicherte_daten.append((vehicle_id, data)),
    )
    monkeypatch.setattr(app, "subscribers", {})
    monkeypatch.setattr(
        app,
        "latest_data",
        {
            "veh-1": {
                "fleet_telemetry_raw": {"TpmsPressureFl": 2.9},
                "vehicle_state": {"tpms_pressure_fl": 2.9},
            }
        },
    )

    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/TpmsPressureFl",
        b"null",
        {"topic_base": "tesla"},
    )

    daten = app.latest_data["veh-1"]
    assert daten["vehicle_state"]["tpms_pressure_fl"] == 2.9
    assert daten["fleet_telemetry_raw"]["TpmsPressureFl"] == 2.9
    assert gespeicherte_daten[-1][1]["vehicle_state"]["tpms_pressure_fl"] == 2.9


@pytest.mark.parametrize(
    ("wert", "stufe", "aktiv"),
    [
        (0, 0, False),
        (2, 2, True),
        ("HvacSteeringWheelHeatLevelOff", 0, False),
        ("HvacSteeringWheelHeatLevelLow", 1, True),
        ("HvacSteeringWheelHeatLevelMedium", 2, True),
        ("HvacSteeringWheelHeatLevelHigh", 3, True),
        ("On", 1, True),
    ],
)
def test_fleet_telemetrie_normalisiert_lenkradheizung(wert, stufe, aktiv):
    daten = {}

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "HvacSteeringWheelHeatLevel",
        wert,
        1781412111000,
    )

    assert daten["climate_state"]["steering_wheel_heat_level"] == stufe
    assert daten["climate_state"]["steering_wheel_heater"] is aktiv


def test_fleet_telemetrie_reichert_lenkradheizung_aus_rohdaten_an():
    daten = {
        "fleet_telemetry_raw": {
            "HvacSteeringWheelHeatLevel": "HvacSteeringWheelHeatLevelHigh",
            "HvacSteeringWheelHeatAuto": True,
        },
        "climate_state": {},
    }

    app._fleet_telemetrie_rohdaten_anreichern(daten)

    assert daten["climate_state"]["steering_wheel_heat_level"] == 3
    assert daten["climate_state"]["steering_wheel_heater"] is True
    assert daten["climate_state"]["auto_steering_wheel_heat"] is True


def test_fleet_telemetrie_batterieheizung_null_bleibt_unbekannt():
    daten = {}

    assert app._fleet_telemetrie_setze_feld(
        daten,
        "BatteryHeaterOn",
        None,
        1781412111000,
    )

    assert daten["charge_state"]["battery_heater_on"] is None
    assert daten["climate_state"]["battery_heater"] is None


def test_fleet_telemetrie_reichert_unbekannte_batterieheizung_aus_rohdaten_an():
    daten = {
        "fleet_telemetry_raw": {
            "BatteryHeaterOn": None,
        },
        "charge_state": {"battery_heater_on": False},
        "climate_state": {"battery_heater": False},
    }

    app._fleet_telemetrie_rohdaten_anreichern(daten)

    assert daten["charge_state"]["battery_heater_on"] is None
    assert daten["climate_state"]["battery_heater"] is None


def test_fetch_data_once_nutzt_telemetrie_cache_ohne_owner_api(monkeypatch):
    aufrufe = []
    parking_aufrufe = []
    cache = {
        "state": "online",
        "fleet_telemetry_updated_at": int(app.time.time() * 1000),
        "id_s": "veh-1",
        "charge_state": {"battery_level": 90},
        "drive_state": {},
        "vehicle_state": {},
        "climate_state": {},
    }

    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: True)
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: dict(cache))
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(
        app,
        "get_vehicle_state",
        lambda vehicle_id=None: aufrufe.append("state"),
    )
    monkeypatch.setattr(
        app,
        "get_vehicle_data",
        lambda vehicle_id=None, state=None: aufrufe.append("data"),
    )
    monkeypatch.setattr(
        app,
        "_record_dashboard_parking_state",
        lambda vehicle_id, data: parking_aufrufe.append((vehicle_id, data)),
    )

    daten = app._fetch_data_once("default")

    assert daten["charge_state"]["battery_level"] == 90
    assert daten["_live"] is True
    assert aufrufe == []
    assert parking_aufrufe == [("veh-1", daten)]


def test_fetch_data_once_telemetrie_only_ohne_cache_ruft_keine_owner_api(monkeypatch):
    aufrufe = []

    monkeypatch.setattr(app, "_nur_fleet_telemetrie_datenquelle", lambda: True)
    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: False)
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: None)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "subscribers", {})
    monkeypatch.setattr(
        app,
        "get_vehicle_state",
        lambda vehicle_id=None: aufrufe.append("state"),
    )
    monkeypatch.setattr(
        app,
        "get_vehicle_data",
        lambda vehicle_id=None, state=None: aufrufe.append("data"),
    )

    daten = app._fetch_data_once("veh-1")

    assert daten["_live"] is False
    assert daten["api_error"] == "Noch keine Fleet-Telemetry-Daten empfangen"
    assert aufrufe == []


def test_get_vehicle_data_telemetrie_only_nutzt_nur_telemetrie_cache(monkeypatch):
    aufrufe = []
    telemetry_cache = {
        "state": "online",
        "fleet_telemetry_updated_at": int(app.time.time() * 1000),
        "_live": True,
    }

    monkeypatch.setattr(app, "_nur_fleet_telemetrie_datenquelle", lambda: True)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_fuer_dashboard",
        lambda cache_id: dict(telemetry_cache),
    )
    monkeypatch.setattr(app, "get_tesla", lambda: aufrufe.append("tesla"))

    daten = app.get_vehicle_data("veh-1", state="online")

    assert daten["_live"] is True
    assert aufrufe == []


def test_get_vehicle_list_telemetrie_only_ohne_fallback(monkeypatch):
    aufrufe = []

    monkeypatch.setattr(app, "_nur_fleet_telemetrie_datenquelle", lambda: True)
    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [])
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: None)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "get_tesla", lambda: aufrufe.append("tesla"))

    assert app.get_vehicle_list() == []
    assert aufrufe == []


def test_telemetrie_cache_entfernt_owner_api_supercharger(monkeypatch):
    cache = {
        "state": "online",
        "fleet_telemetry_updated_at": int(app.time.time() * 1000),
        "nearby_superchargers": [{"name": "Alt"}],
        "access_type": "OWNER",
    }

    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: True)

    daten = app._fleet_telemetrie_cache_fuer_dashboard("veh-1", cache)

    assert "nearby_superchargers" not in daten
    assert "access_type" not in daten


def test_telemetrie_cache_markiert_veraltete_daten_als_offline(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: True)
    monkeypatch.setattr(app, "TESLA_FLEET_TELEMETRY_STALE_SECONDS", 300.0)
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)

    update_ms = int((2000.0 - 301.0) * 1000)
    cache = {
        "state": "online",
        "fleet_telemetry_updated_at": update_ms,
        "charge_state": {},
        "drive_state": {},
    }

    daten = app._fleet_telemetrie_cache_fuer_dashboard("veh-1", cache)

    assert daten["state"] == "offline"
    assert daten["_live"] is False
    assert daten["api_error"] == "Noch keine aktuellen Fleet-Telemetry-Daten empfangen"
    assert daten["state_checked_at"] == 2_000_000
    assert daten["state_since_ms"] == update_ms + 300_000


def test_telemetrie_cache_speichert_bereinigte_offline_navigation(monkeypatch):
    gespeichert = []
    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: True)
    monkeypatch.setattr(app, "TESLA_FLEET_TELEMETRY_STALE_SECONDS", 300.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_PARK_DELAY_SECONDS",
        120.0,
    )
    monkeypatch.setattr(app.time, "time", lambda: 1_800_000_301.0)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda cache_id, data: gespeichert.append((cache_id, data)),
    )
    cache = {
        "state": "offline",
        "state_since_ms": 1_800_000_000_000,
        "fleet_telemetry_updated_at": 1_800_000_000_000,
        "fleet_telemetry_raw": {
            "DestinationName": "Altes Ziel",
            "RouteLine": "abcdef",
        },
        "drive_state": {
            "active_route_active": True,
            "active_route_destination": "Altes Ziel",
            "active_route_line": "abcdef",
        },
    }

    daten = app._fleet_telemetrie_cache_fuer_dashboard("veh-1", cache)

    drive = daten["drive_state"]
    assert drive["active_route_active"] is False
    assert "active_route_destination" not in drive
    assert "active_route_line" not in drive
    assert daten["fleet_telemetry_raw"] == {}
    assert app.latest_data["veh-1"] is daten
    assert gespeichert == [("veh-1", daten)]


def test_telemetrie_cache_akzeptiert_frischen_rest_fallback(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: True)
    monkeypatch.setattr(app, "TESLA_FLEET_TELEMETRY_STALE_SECONDS", 300.0)
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    monkeypatch.setattr(app, "latest_data", {})
    cache = {
        "state": "online",
        "fleet_telemetry_updated_at": 1_000_000,
        "fleet_vehicle_data_received_at": 1_999_000,
        "charge_state": {},
        "drive_state": {"shift_state": "P", "speed": 0},
    }

    daten = app._fleet_telemetrie_cache_fuer_dashboard("veh-1", cache)

    assert daten["state"] == "online"
    assert daten["_live"] is True
    assert "api_error" not in daten


def test_telemetrie_cache_entfernt_owner_api_schiebedachstatus(monkeypatch):
    cache = {
        "state": "online",
        "fleet_telemetry_updated_at": int(app.time.time() * 1000),
        "fleet_telemetry_raw": {
            "SunroofInstalled": "SunroofInstalledStateGen2Installed",
        },
        "vehicle_state": {
            "sun_roof_state": "open",
            "sun_roof_percent_open": 20,
        },
    }

    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: True)

    daten = app._fleet_telemetrie_cache_fuer_dashboard("veh-1", cache)

    vehicle_state = daten["vehicle_state"]
    assert "sun_roof_state" not in vehicle_state
    assert "sun_roof_percent_open" not in vehicle_state
    assert vehicle_state["sun_roof_status_available"] is False


def test_fleet_telemetrie_mqtt_mappt_schiebedachstatus_falls_verfuegbar(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
        "id_s": "veh-1",
    }])
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: {})
    monkeypatch.setattr(app, "_save_cached", lambda vehicle_id, data: None)
    monkeypatch.setattr(app, "latest_data", {})

    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/SunroofPercentOpen",
        b"30",
        {"topic_base": "tesla"},
    )

    vehicle_state = app.latest_data["veh-1"]["vehicle_state"]
    assert vehicle_state["sun_roof_percent_open"] == 30
    assert vehicle_state["sun_roof_status_available"] is True


def test_api_config_deaktiviert_owner_api_supercharger_im_telemetrie_only(monkeypatch):
    monkeypatch.setattr(app, "_nur_fleet_telemetrie_datenquelle", lambda: True)
    monkeypatch.setattr(
        app,
        "load_config",
        lambda vehicle_id=None: {
            "supercharger-list": True,
            "tessie_api_token": "alt",
        },
    )

    response = app.app.test_client().get("/api/config")
    daten = response.get_json()

    assert response.status_code == 200
    assert daten["supercharger-list"] is False
    assert "tessie_api_token" not in daten


def test_news_events_telemetrie_only_ohne_tesla_api(monkeypatch):
    aufrufe = []

    monkeypatch.setattr(app, "_nur_fleet_telemetrie_datenquelle", lambda: True)
    monkeypatch.setattr(app, "get_tesla", lambda: aufrufe.append("tesla"))

    assert app.get_news_events_info() == ""
    assert aufrufe == []


def test_fetch_data_once_sendet_telemetrie_cache_nicht_an_stream(monkeypatch):
    class Sammler:
        def __init__(self):
            self.daten = []

        def put(self, daten):
            self.daten.append(daten)

    sammler = Sammler()
    cache = {
        "state": "online",
        "fleet_telemetry_updated_at": int(app.time.time() * 1000),
        "charge_state": {"battery_level": 90},
        "drive_state": {},
        "vehicle_state": {},
        "climate_state": {},
    }

    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: True)
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: dict(cache))
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "subscribers", {"default": [sammler]})
    monkeypatch.setattr(app, "_record_dashboard_parking_state", lambda *args: None)

    daten = app._fetch_data_once("default")

    assert daten["charge_state"]["battery_level"] == 90
    assert sammler.daten == []


def test_start_thread_startet_bei_fleet_telemetrie_keinen_polling_thread(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: True)
    monkeypatch.setattr(app, "threads", {})

    app._start_thread("veh-1")

    assert app.threads == {}


def test_fahrzeugliste_nutzt_fleet_telemetrie_ohne_owner_api(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: True)
    monkeypatch.setattr(app, "_default_vehicle_id", None)
    monkeypatch.setattr(app, "get_tesla", lambda: None)
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: None)
    monkeypatch.setattr(app, "latest_data", {})
    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
        "id_s": "veh-1",
        "vehicle_id": "legacy-veh-1",
        "display_name": "Testauto",
    }])

    fahrzeuge = app.get_vehicle_list()

    assert fahrzeuge == [{"id": "veh-1", "display_name": "Testauto"}]
    assert app._default_vehicle_id == "veh-1"


def test_fahrzeugliste_nutzt_telemetrie_cache_als_fallback(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: True)
    monkeypatch.setattr(app, "_default_vehicle_id", None)
    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [])
    monkeypatch.setattr(
        app,
        "_load_cached",
        lambda vehicle_id: {
            "id_s": "veh-cache",
            "display_name": "Cacheauto",
        } if vehicle_id == "default" else None,
    )
    monkeypatch.setattr(app, "latest_data", {})

    fahrzeuge = app.get_vehicle_list()

    assert fahrzeuge == [{"id": "veh-cache", "display_name": "Cacheauto"}]


def test_fahrzeugliste_dedupliziert_fleet_alias_ids(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: True)
    monkeypatch.setattr(app, "_default_vehicle_id", None)
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: None)
    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
        "id_s": "fleet-id",
        "vehicle_id": "legacy-id",
        "display_name": "Testauto",
    }])
    monkeypatch.setattr(
        app,
        "latest_data",
        {
            "legacy-id": {
                "id_s": "legacy-id",
                "display_name": "Testauto",
            }
        },
    )

    fahrzeuge = app.get_vehicle_list()

    assert fahrzeuge == [{"id": "fleet-id", "display_name": "Testauto"}]


def test_fahrzeugliste_ignoriert_fremde_latest_data_cache_keys(monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: True)
    monkeypatch.setattr(app, "_default_vehicle_id", None)
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: None)
    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
        "id_s": "fleet-id",
        "display_name": "Testauto",
    }])
    monkeypatch.setattr(
        app,
        "latest_data",
        {
            "wp-config.env": {"state": None},
            "fleet-id": {"id_s": "fleet-id", "display_name": "Testauto"},
        },
    )

    fahrzeuge = app.get_vehicle_list()

    assert fahrzeuge == [{"id": "fleet-id", "display_name": "Testauto"}]


def test_api_data_unbekanntes_fahrzeug_erzeugt_keinen_cache_ordner(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(app, "_default_vehicle_id", None)
    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
        "id_s": "fleet-id",
    }])
    monkeypatch.setattr(app, "latest_data", {})

    response = app.app.test_client().get("/api/data/wp-config.env")

    assert response.status_code == 404
    assert response.get_json()["error"] == "Unbekanntes Fahrzeug"
    assert not (tmp_path / "wp-config.env").exists()


def test_fleet_telemetrie_profile_erkennt_zielzustand():
    assert app._fleet_telemetrie_profile_ziel({
        "charge_state": {"charging_state": "Charging"},
        "drive_state": {"shift_state": "P"},
    }) == "charging"

    assert app._fleet_telemetrie_profile_ziel({
        "charge_state": {"charging_state": "Charging"},
        "drive_state": {"shift_state": "P"},
        "vehicle_state": {"is_user_present": True},
    }) == "charging"

    assert app._fleet_telemetrie_profile_ziel({
        "charge_state": {"charging_state": "Charging"},
        "drive_state": {"shift_state": "D", "speed": 0},
        "vehicle_state": {"is_user_present": True},
    }) == "live"

    assert app._fleet_telemetrie_profile_ziel({
        "charge_state": {"charging_state": "Charging"},
        "drive_state": {"shift_state": "P", "speed": 8},
        "vehicle_state": {"is_user_present": True},
    }) == "live"

    assert app._fleet_telemetrie_profile_ziel({
        "drive_state": {"shift_state": "D", "speed": 0},
        "vehicle_state": {"is_user_present": False},
    }) == "live"

    assert app._fleet_telemetrie_profile_ziel({
        "drive_state": {"shift_state": "P", "speed": 0},
        "vehicle_state": {"locked": True, "is_user_present": False},
        "climate_state": {"is_climate_on": False},
    }) == "parked"


def test_fleet_telemetrie_profile_verlaesst_charging_nach_ladeende():
    assert app._fleet_telemetrie_profile_ziel({
        "charge_state": {
            "charging_state": "Complete",
            "charge_port_latch": "Engaged",
            "fast_charger_present": True,
            "charger_power": 13,
        },
        "drive_state": {"shift_state": "P", "speed": 0},
        "vehicle_state": {"is_user_present": False},
        "climate_state": {"is_climate_on": False},
    }) == "parked"

    assert app._fleet_telemetrie_profile_ziel({
        "charge_state": {
            "charging_state": "Stopped",
            "charge_port_latch": "Connected",
            "fast_charger_present": True,
        },
        "drive_state": {"shift_state": "P", "speed": 0},
        "vehicle_state": {"is_user_present": False},
        "climate_state": {"is_climate_on": False},
    }) == "parked"


def test_fleet_telemetrie_neue_ladeleistung_ueberstimmt_alten_ladestatus():
    daten = {
        "charge_state": {
            "charging_state": "Disconnected",
            "charger_power": 29,
        },
        "fleet_telemetry_field_received_at": {
            "ChargeState": 1_000_000,
            "DetailedChargeState": 1_000_000,
            "DCChargingPower": 2_000_000,
        },
    }

    assert app._fleet_telemetrie_profile_ladezustand(daten) is True

    daten["fleet_telemetry_field_received_at"]["ChargeState"] = 3_000_000
    assert app._fleet_telemetrie_profile_ladezustand(daten) is False


def test_fleet_telemetrie_profile_nutzt_nach_ladeende_zuerst_live(monkeypatch):
    angefordert = []
    jetzt = [2000.0]

    monkeypatch.setattr(app.time, "time", lambda: jetzt[0])
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_PARK_DELAY_SECONDS",
        120.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "charging",
            1900.0,
            charging_observed=True,
        ),
    )
    daten = {
        "vin": "TESTVIN",
        "charge_state": {"charging_state": "Complete"},
        "drive_state": {"shift_state": "P", "speed": 0},
        "vehicle_state": {"locked": True, "is_user_present": False},
        "climate_state": {"is_climate_on": False},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    status = app._fleet_telemetry_profile_status
    assert angefordert == ["live"]
    assert status["target"] == "live"
    assert status["config_sync_profile"] == "live"
    assert status["post_charge_live_since"] == 2000.0
    assert status["post_charge_live_until"] == 2120.0

    status.update({
        "current": "live",
        "last_sent_profile": "live",
        "last_posted_at": 2000.0,
        "last_posted_profile": "live",
        "config_synced": True,
        "config_sync_state": "synced",
        "config_sync_profile": "live",
        "config_sync_details": _telemetrie_stream_details(),
    })
    jetzt[0] = 2010.0
    daten["drive_state"] = {"shift_state": "D", "speed": 5}

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert status["target"] == "live"
    assert status["post_charge_live_since"] == 0.0
    assert status["post_charge_live_until"] == 0.0


def test_fleet_telemetrie_profile_beendet_ladebruecke_ohne_fahrt(monkeypatch):
    angefordert = []
    jetzt = [2119.0]

    monkeypatch.setattr(app.time, "time", lambda: jetzt[0])
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_PARK_DELAY_SECONDS",
        120.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            2000.0,
            charging_observed=False,
            post_charge_live_since=2000.0,
            post_charge_live_until=2120.0,
            live_stable_since=2000.0,
        ),
    )
    daten = {
        "vin": "TESTVIN",
        "fleet_telemetry_received_at": 2_119_000,
        "fleet_telemetry_field_received_at": {
            "Location": 2_119_000,
            "PackCurrent": 2_119_000,
            "PackVoltage": 2_119_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "Location": 1000,
            "PackCurrent": 1000,
            "PackVoltage": 1000,
        },
        "charge_state": {"charging_state": "Complete"},
        "drive_state": {"shift_state": "P", "speed": 0},
        "vehicle_state": {"locked": True, "is_user_present": False},
        "climate_state": {"is_climate_on": False},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert app._fleet_telemetry_profile_status["target"] == "live"

    jetzt[0] = 2120.0
    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    status = app._fleet_telemetry_profile_status
    assert angefordert == ["parked"]
    assert status["target"] == "parked"
    assert status["target_since"] == 2000.0
    assert status["post_charge_live_since"] == 0.0
    assert status["post_charge_live_until"] == 0.0


def test_fleet_telemetrie_profile_korrigiert_physisches_charging(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            1900.0,
            last_posted_profile="charging",
            charging_observed=False,
        ),
    )
    daten = {
        "vin": "TESTVIN",
        "fleet_telemetry_received_at": 1_999_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 1_999_000,
            "Location": 1_970_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 10_000,
            "Location": 30_000,
        },
        "charge_state": {"charging_state": "Disconnected"},
        "drive_state": {"shift_state": "D", "speed": 20},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    status = app._fleet_telemetry_profile_status
    assert angefordert == ["live"]
    assert status["config_synced"] is False
    assert status["config_sync_state"] == "pending"
    assert status["config_sync_profile"] == "live"

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == ["live"]


def test_fleet_telemetrie_profile_ignoriert_verbundenen_browser(monkeypatch):
    monkeypatch.setattr(app, "subscribers", {"veh-1": [object()]})

    assert app._fleet_telemetrie_profile_ziel({
        "charge_state": {"charging_state": "Charging"},
        "drive_state": {"shift_state": "P", "speed": 0},
        "vehicle_state": {"is_user_present": False},
    }) == "charging"

    assert app._fleet_telemetrie_profile_ziel({
        "drive_state": {"shift_state": "P", "speed": 0},
        "vehicle_state": {"is_user_present": False},
        "climate_state": {"is_climate_on": False},
    }) == "parked"


def test_fleet_telemetrie_profile_config_filtert_parkwerte():
    basis = {
        "vins": ["TESTVIN"],
        "config": {
            "fields": {
                "ACChargingPower": {"interval_seconds": 60},
                "InsideTemp": {"interval_seconds": 1, "minimum_delta": 0.1},
                "Location": {"interval_seconds": 1, "minimum_delta": 0},
                "MediaNowPlayingTitle": {"interval_seconds": 30},
                "BatteryHeaterOn": {"interval_seconds": 60},
                "BatteryLevel": {"interval_seconds": 1, "minimum_delta": 0.1},
                "BrakePedal": {"interval_seconds": 10},
                "BrakePedalPos": {"interval_seconds": 10},
                "ChargeState": {"interval_seconds": 1},
                "DCChargingPower": {"interval_seconds": 60},
                "DestinationLocation": {"interval_seconds": 60},
                "DestinationName": {"interval_seconds": 60},
                "DoorState": {"interval_seconds": 60},
                "ExpectedEnergyPercentAtTripArrival": {"interval_seconds": 60},
                "FdWindow": {"interval_seconds": 60},
                "FpWindow": {"interval_seconds": 60},
                "HvacFanSpeed": {"interval_seconds": 60},
                "HvacFanStatus": {"interval_seconds": 60},
                "HvacLeftTemperatureRequest": {"interval_seconds": 60},
                "HvacRightTemperatureRequest": {"interval_seconds": 60},
                "LightsHazardsActive": {"interval_seconds": 10},
                "LightsHighBeams": {"interval_seconds": 10},
                "LightsTurnSignal": {"interval_seconds": 10},
                "MilesToArrival": {"interval_seconds": 60},
                "MinutesToArrival": {"interval_seconds": 60},
                "ModuleTempMax": {
                    "interval_seconds": 1,
                    "minimum_delta": 0.1,
                },
                "ModuleTempMin": {
                    "interval_seconds": 1,
                    "minimum_delta": 0.1,
                },
                "PackCurrent": {"interval_seconds": 1, "minimum_delta": 0.1},
                "RouteLine": {"interval_seconds": 1},
                "RouteTrafficMinutesDelay": {"interval_seconds": 60},
                "RdWindow": {"interval_seconds": 60},
                "RearDefrostEnabled": {"interval_seconds": 60},
                "RpWindow": {"interval_seconds": 60},
                "SeatHeaterLeft": {"interval_seconds": 60},
                "SeatHeaterRearCenter": {"interval_seconds": 60},
                "SeatHeaterRearLeft": {"interval_seconds": 60},
                "SeatHeaterRearRight": {"interval_seconds": 60},
                "SeatHeaterRight": {"interval_seconds": 60},
                "VehicleSpeed": {"interval_seconds": 1, "minimum_delta": 0.1},
                "VehicleName": {"interval_seconds": 1},
            },
        },
    }

    live = app._fleet_telemetrie_profile_config_erstellen(basis, "live")
    live_fields = live["config"]["fields"]

    assert live["config"]["delivery_policy"] == "latest"
    assert live_fields["Location"]["interval_seconds"] == 1
    assert "minimum_delta" not in live_fields["Location"]
    assert set(live_fields["Location"]["include_fields"]) == (
        app.FLEET_TELEMETRIE_PROFILE_LIVE_BEWEGUNGS_INKLUSIVFELDER
    )
    assert live_fields["VehicleSpeed"]["interval_seconds"] == 1
    assert "minimum_delta" not in live_fields["VehicleSpeed"]
    assert live_fields["PackCurrent"]["interval_seconds"] == 1
    assert "minimum_delta" not in live_fields["PackCurrent"]
    assert live_fields["BatteryLevel"]["interval_seconds"] == 5
    assert "minimum_delta" not in live_fields["BatteryLevel"]
    assert live_fields["ACChargingPower"]["interval_seconds"] == 10
    assert live_fields["BatteryHeaterOn"]["interval_seconds"] == 10
    assert live_fields["BrakePedal"]["interval_seconds"] == 1
    assert live_fields["BrakePedalPos"]["interval_seconds"] == 1
    assert live_fields["ChargeState"]["interval_seconds"] == 10
    assert live_fields["DestinationLocation"]["interval_seconds"] == 1
    assert live_fields["DestinationName"]["interval_seconds"] == 30
    assert live_fields["DCChargingPower"]["interval_seconds"] == 10
    assert live_fields["ExpectedEnergyPercentAtTripArrival"]["interval_seconds"] == 5
    assert live_fields["FdWindow"]["interval_seconds"] == 10
    assert live_fields["FpWindow"]["interval_seconds"] == 10
    assert live_fields["HvacFanSpeed"]["interval_seconds"] == 30
    assert live_fields["HvacFanStatus"]["interval_seconds"] == 30
    assert live_fields["HvacLeftTemperatureRequest"]["interval_seconds"] == 1
    assert live_fields["HvacRightTemperatureRequest"]["interval_seconds"] == 1
    assert live_fields["LightsHazardsActive"]["interval_seconds"] == 1
    assert live_fields["LightsHighBeams"]["interval_seconds"] == 1
    assert live_fields["LightsTurnSignal"]["interval_seconds"] == 1
    assert live_fields["InsideTemp"]["interval_seconds"] == 10
    assert "minimum_delta" not in live_fields["InsideTemp"]
    assert live_fields["MilesToArrival"]["interval_seconds"] == 5
    assert live_fields["MinutesToArrival"]["interval_seconds"] == 5
    assert live_fields["Odometer"]["interval_seconds"] == 10
    assert set(live_fields["Odometer"]["include_fields"]) == (
        app.FLEET_TELEMETRIE_PROFILE_LIVE_NAVIGATIONS_INKLUSIVFELDER
    )
    assert live_fields["ModuleTempMax"]["interval_seconds"] == 60
    assert live_fields["ModuleTempMin"]["interval_seconds"] == 60
    assert "minimum_delta" not in live_fields["ModuleTempMax"]
    assert "minimum_delta" not in live_fields["ModuleTempMin"]
    assert live_fields["RouteLine"]["interval_seconds"] == 10
    assert "RouteLine" in live_fields["DestinationLocation"]["include_fields"]
    assert "RouteLine" in live_fields["DestinationName"]["include_fields"]
    assert live_fields["RouteTrafficMinutesDelay"]["interval_seconds"] == 5
    assert live_fields["RdWindow"]["interval_seconds"] == 10
    assert live_fields["RearDefrostEnabled"]["interval_seconds"] == 10
    assert live_fields["RpWindow"]["interval_seconds"] == 10
    assert live_fields["SeatHeaterLeft"]["interval_seconds"] == 10
    assert live_fields["SeatHeaterRearCenter"]["interval_seconds"] == 10
    assert live_fields["SeatHeaterRearLeft"]["interval_seconds"] == 10
    assert live_fields["SeatHeaterRearRight"]["interval_seconds"] == 10
    assert live_fields["SeatHeaterRight"]["interval_seconds"] == 10
    assert "MediaNowPlayingTitle" not in live_fields
    assert live_fields["DCDCEnable"]["interval_seconds"] == 30
    assert "minimum_delta" not in live_fields["DCDCEnable"]
    assert "VehicleName" not in live_fields
    assert all(
        "minimum_delta" not in feld_config
        for feld_config in live_fields.values()
    )

    wiederherstellung = app._fleet_telemetrie_profile_config_erstellen(
        basis,
        "live",
        wiederherstellung=True,
    )
    wiederherstellungsfelder = wiederherstellung["config"]["fields"]

    assert set(wiederherstellungsfelder) == (
        set(live_fields)
        & app.FLEET_TELEMETRIE_PROFILE_LIVE_WIEDERHERSTELLUNGSFELDER
    )
    assert wiederherstellungsfelder["VehicleSpeed"]["interval_seconds"] == 1
    assert wiederherstellungsfelder["Location"]["interval_seconds"] == 1
    assert wiederherstellungsfelder["DoorState"]["interval_seconds"] == 10
    assert wiederherstellungsfelder["FdWindow"]["interval_seconds"] == 10
    assert wiederherstellungsfelder["FpWindow"]["interval_seconds"] == 10
    assert wiederherstellungsfelder["RdWindow"]["interval_seconds"] == 10
    assert wiederherstellungsfelder["RouteLine"]["interval_seconds"] == 10
    assert wiederherstellungsfelder["RpWindow"]["interval_seconds"] == 10
    assert set(wiederherstellungsfelder["Location"]["include_fields"]) == (
        app.FLEET_TELEMETRIE_PROFILE_LIVE_BEWEGUNGS_INKLUSIVFELDER
        & app.FLEET_TELEMETRIE_PROFILE_LIVE_WIEDERHERSTELLUNGSFELDER
    )
    assert (
        "RouteLine"
        not in wiederherstellungsfelder["Location"]["include_fields"]
    )
    assert set(wiederherstellungsfelder["Odometer"]["include_fields"]) == (
        app.FLEET_TELEMETRIE_PROFILE_LIVE_NAVIGATIONS_INKLUSIVFELDER
    )
    assert (
        "RouteLine"
        in wiederherstellungsfelder["DestinationLocation"]["include_fields"]
    )
    assert (
        "RouteLine"
        in wiederherstellungsfelder["DestinationName"]["include_fields"]
    )
    assert wiederherstellungsfelder["PackCurrent"]["interval_seconds"] == 1
    assert wiederherstellungsfelder["ACChargingPower"]["interval_seconds"] == 10
    assert wiederherstellungsfelder["DCChargingPower"]["interval_seconds"] == 10
    assert wiederherstellungsfelder["DCDCEnable"]["interval_seconds"] == 30

    erweitert = app._fleet_telemetrie_profile_config_erstellen(
        basis,
        "live_extended",
    )
    erweitert_fields = erweitert["config"]["fields"]

    assert erweitert_fields["VehicleSpeed"]["interval_seconds"] == 1
    assert set(erweitert_fields["Location"]["include_fields"]) == (
        app.FLEET_TELEMETRIE_PROFILE_LIVE_BEWEGUNGS_INKLUSIVFELDER
    )
    assert erweitert_fields["DestinationLocation"]["interval_seconds"] == 1
    assert erweitert_fields["DestinationName"]["interval_seconds"] == 30
    assert erweitert_fields["HvacLeftTemperatureRequest"]["interval_seconds"] == 1
    assert erweitert_fields["HvacRightTemperatureRequest"]["interval_seconds"] == 1
    assert erweitert_fields["RouteLine"]["interval_seconds"] == 10
    assert "RouteLine" in erweitert_fields["Odometer"]["include_fields"]
    assert erweitert_fields["DCDCEnable"]["interval_seconds"] == 30
    assert erweitert_fields["BatteryHeaterOn"]["interval_seconds"] == 10
    assert erweitert_fields["ACChargingPower"]["interval_seconds"] == 10
    assert erweitert_fields["DCChargingPower"]["interval_seconds"] == 10
    assert erweitert_fields["MediaNowPlayingTitle"]["interval_seconds"] == 60
    assert erweitert_fields["ModuleTempMax"]["interval_seconds"] == 60
    assert erweitert_fields["ModuleTempMin"]["interval_seconds"] == 60
    assert erweitert_fields["FdWindow"]["interval_seconds"] == 10
    assert erweitert_fields["RearDefrostEnabled"]["interval_seconds"] == 10
    assert erweitert_fields["SeatHeaterRearRight"]["interval_seconds"] == 10
    assert erweitert_fields["VehicleName"]["interval_seconds"] == 60
    assert all(
        "minimum_delta" not in feld_config
        for feld_config in erweitert_fields.values()
    )

    gedrosselt = app._fleet_telemetrie_profile_config_erstellen(basis, "parked")
    fields = gedrosselt["config"]["fields"]

    assert basis["config"]["fields"]["Location"]["interval_seconds"] == 1
    assert "InsideTemp" not in fields
    assert "HvacLeftTemperatureRequest" not in fields
    assert "HvacRightTemperatureRequest" not in fields
    assert "Location" not in fields
    assert "MediaNowPlayingTitle" not in fields
    assert "RouteLine" not in fields
    assert all("include_fields" not in config for config in fields.values())
    assert fields["BatteryLevel"]["interval_seconds"] == 60
    assert "minimum_delta" not in fields["BatteryLevel"]
    assert fields["BatteryHeaterOn"]["interval_seconds"] == 60
    assert fields["DCDCEnable"]["interval_seconds"] == 60
    assert fields["ACChargingPower"]["interval_seconds"] == 10
    assert fields["DCChargingPower"]["interval_seconds"] == 10
    assert fields["ChargeState"]["interval_seconds"] == 10
    assert fields["FdWindow"]["interval_seconds"] == 10
    assert fields["RearDefrostEnabled"]["interval_seconds"] == 10
    assert fields["SeatHeaterRearRight"]["interval_seconds"] == 10
    assert fields["VehicleSpeed"]["interval_seconds"] == 10
    assert "minimum_delta" not in fields["VehicleSpeed"]
    assert all(
        "minimum_delta" not in feld_config
        for feld_config in fields.values()
    )

    charging = app._fleet_telemetrie_profile_config_erstellen(basis, "charging")
    charging_fields = charging["config"]["fields"]

    assert charging["config"]["delivery_policy"] == "latest"
    assert charging_fields["DCDCEnable"]["interval_seconds"] == 30
    assert charging_fields["BatteryLevel"]["interval_seconds"] == 10
    assert "minimum_delta" not in charging_fields["BatteryLevel"]
    assert charging_fields["BatteryHeaterOn"]["interval_seconds"] == 10
    assert charging_fields["ACChargingPower"]["interval_seconds"] == 10
    assert charging_fields["DCChargingPower"]["interval_seconds"] == 10
    assert charging_fields["FdWindow"]["interval_seconds"] == 10
    assert charging_fields["RearDefrostEnabled"]["interval_seconds"] == 10
    assert charging_fields["HvacLeftTemperatureRequest"]["interval_seconds"] == 10
    assert charging_fields["HvacRightTemperatureRequest"]["interval_seconds"] == 10
    assert charging_fields["SeatHeaterRearRight"]["interval_seconds"] == 10
    assert charging_fields["VehicleSpeed"]["interval_seconds"] == 10
    assert "minimum_delta" not in charging_fields["VehicleSpeed"]
    assert "DestinationLocation" not in charging_fields
    assert "DestinationName" not in charging_fields
    assert "MediaNowPlayingTitle" not in charging_fields
    assert "VehicleName" not in charging_fields
    assert all(
        "include_fields" not in config
        for config in charging_fields.values()
    )
    assert all(
        "minimum_delta" not in feld_config
        for feld_config in charging_fields.values()
    )


def test_fleet_telemetrie_live_reparatur_sendet_basis_dann_vollprofil(
    monkeypatch,
):
    gesendete_felder = []

    class Antwort:
        def raise_for_status(self):
            pass

    basis = {
        "vins": ["TESTVIN"],
        "config": {
            "hostname": "telemetry.example.test",
            "port": 443,
            "fields": {
                "DCDCEnable": {"interval_seconds": 30},
                "InsideTemp": {"interval_seconds": 10},
                "Location": {"interval_seconds": 1},
                "VehicleSpeed": {"interval_seconds": 1},
            },
        },
    }
    monkeypatch.setattr(app, "_fleet_telemetrie_oauth_token", lambda: "token")
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_request_laden",
        lambda: basis,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_config_speichern",
        lambda config: None,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_sync_pruefen",
        lambda *args: {
            "synced": False,
            "key_paired": None,
            "state": "pending",
            "details": [],
            "checked_at": 2000.0,
            "error": None,
        },
    )

    def senden(url, **kwargs):
        gesendete_felder.append(set(kwargs["json"]["config"]["fields"]))
        return Antwort()

    monkeypatch.setattr(app.requests, "post", senden)
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            1900.0,
            config_synced=False,
            config_sync_state="pending",
            config_sync_details=[],
            live_retry_active=True,
            live_retry_motion_active=True,
        ),
    )

    app._fleet_telemetrie_profile_anwenden("live")
    app._fleet_telemetrie_profile_anwenden("live")

    assert gesendete_felder == [
        {"DCDCEnable", "Location", "Odometer", "VehicleSpeed"},
        {
            "DCDCEnable",
            "InsideTemp",
            "Location",
            "Odometer",
            "VehicleSpeed",
        },
    ]
    status = app._fleet_telemetry_profile_status
    assert status["live_retry_attempts"] == 2
    assert status["live_recovery_bootstrap_active"] is False


def test_fleet_telemetrie_profile_sync_pruefung_liefert_fahrzeugstatus(monkeypatch):
    class Antwort:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "response": {
                    "synced": True,
                    "key_paired": True,
                    "limit_reached": False,
                },
            }

    abfragen = []

    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
    }])
    monkeypatch.setattr(app, "_fleet_telemetrie_oauth_token", lambda: "token-123")
    monkeypatch.setattr(
        app.requests,
        "get",
        lambda url, **kwargs: abfragen.append((url, kwargs)) or Antwort(),
    )

    ergebnis = app._fleet_telemetrie_profile_sync_pruefen()

    assert ergebnis["synced"] is True
    assert ergebnis["key_paired"] is True
    assert ergebnis["state"] == "synced"
    assert ergebnis["details"] == [{
        "vin": "TESTVIN",
        "synced": True,
        "key_paired": True,
        "limit_reached": False,
    }]
    assert abfragen[0][0].endswith(
        "/api/1/vehicles/TESTVIN/fleet_telemetry_config"
    )
    assert abfragen[0][1]["headers"]["Authorization"] == "Bearer token-123"


def test_fleet_telemetrie_profile_ignoriert_key_paired_false(monkeypatch):
    class Antwort:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "response": {
                    "synced": True,
                    "key_paired": False,
                    "limit_reached": False,
                },
            }

    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [{
        "vin": "TESTVIN",
    }])
    monkeypatch.setattr(app, "_fleet_telemetrie_oauth_token", lambda: "token-123")
    monkeypatch.setattr(app.requests, "get", lambda url, **kwargs: Antwort())

    ergebnis = app._fleet_telemetrie_profile_sync_pruefen()

    assert ergebnis["synced"] is True
    assert ergebnis["key_paired"] is None
    assert ergebnis["state"] == "synced"
    assert ergebnis["details"] == [{
        "vin": "TESTVIN",
        "synced": True,
        "limit_reached": False,
    }]

    app._fleet_telemetrie_profile_erfolg_setzen("parked", ergebnis)
    daten = {}

    app._fleet_telemetrie_profile_status_an_daten(daten)

    assert daten["telemetry_config_synced"] is True
    assert daten["telemetry_config_key_paired"] is None
    assert app._fleet_telemetry_profile_status["config_key_paired"] is None
    assert app._fleet_telemetry_profile_status["config_sync_details"] == [{
        "vin": "TESTVIN",
        "synced": True,
        "limit_reached": False,
    }]


def test_fleet_telemetrie_profile_status_enthaelt_syncdaten(monkeypatch):
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)

    app._fleet_telemetrie_profile_erfolg_setzen(
        "parked",
        {
            "synced": True,
            "key_paired": True,
            "state": "synced",
            "details": [{"vin": "TESTVIN", "synced": True}],
            "checked_at": 1999.0,
            "error": None,
        },
    )
    daten = {}

    app._fleet_telemetrie_profile_status_an_daten(daten)

    assert daten["telemetry_config_synced"] is True
    assert daten["telemetry_config_key_paired"] is True
    assert daten["telemetry_config_sync_state"] == "synced"
    assert daten["telemetry_config_sync_profile"] == "parked"
    assert daten["telemetry_config_sync_checked_at"] == 1999.0
    assert daten["telemetry_config_sync_error"] is None


def test_fleet_telemetrie_profile_pending_wird_bei_datenstrom_aktiv(monkeypatch):
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 1500.0,
            "last_sent": 1900.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": False,
            "config_key_paired": False,
            "config_sync_state": "pending",
            "config_sync_profile": "live",
            "config_sync_checked_at": 1950.0,
            "config_sync_updated_at": 1950.0,
            "config_sync_error": None,
            "config_sync_details": [{
                "vin": "TESTVIN",
                "synced": False,
                "key_paired": False,
            }],
            "updated_at": 1950.0,
        },
    )
    daten = {"fleet_telemetry_updated_at": 1999_000}

    app._fleet_telemetrie_profile_status_an_daten(daten)

    assert daten["telemetry_config_synced"] is False
    assert daten["telemetry_config_key_paired"] is None
    assert daten["telemetry_config_stream_active"] is True
    assert daten["telemetry_config_sync_state"] == "active"


def test_fleet_telemetrie_profile_stream_empfang_bestaetigt_legacy(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 1500.0,
            "last_sent": 1900.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": False,
            "config_key_paired": None,
            "config_sync_state": "pending",
            "config_sync_profile": "live",
            "config_sync_checked_at": 1950.0,
            "config_sync_updated_at": 1950.0,
            "config_sync_error": None,
            "config_sync_details": [{
                "vin": "TESTVIN",
                "synced": False,
                "key_paired": False,
            }],
            "updated_at": 1950.0,
        },
    )
    daten = {
        "vin": "TESTVIN",
        "fleet_telemetry_received_at": 1999_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 1999_000,
            "PackCurrent": 1999_000,
        },
        "fleet_telemetry_field_previous_received_at": {
            "VehicleSpeed": 1998_000,
            "PackCurrent": 1998_000,
        },
        "drive_state": {"shift_state": "P", "speed": 0},
        "climate_state": {"is_climate_on": True},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert daten["telemetry_config_synced"] is True
    assert daten["telemetry_config_sync_state"] == "synced"
    assert app._fleet_telemetry_profile_status["config_synced"] is True
    assert app._fleet_telemetry_profile_status["config_sync_state"] == "synced"
    assert app._fleet_telemetry_profile_status["config_sync_details"] == [{
        "vin": "TESTVIN",
        "synced": True,
        "source": "telemetry_stream",
    }]


def test_fleet_telemetrie_profile_live_bestaetigt_keinen_burst():
    status = {
        "last_sent": 1900.0,
    }
    daten = {
        "fleet_telemetry_received_at": 1999_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 1999_000,
            "PackCurrent": 1999_010,
        },
        "fleet_telemetry_field_previous_received_at": {
            "VehicleSpeed": 1998_990,
            "PackCurrent": 1999_000,
        },
    }

    assert app._fleet_telemetrie_profile_live_takt_bestaetigt(daten, status) is False


def test_fleet_telemetrie_profile_live_bestaetigt_fahrt_nur_mit_position():
    status = {
        "last_sent": 1900.0,
    }
    daten = {
        "fleet_telemetry_received_at": 1999_000,
        "fleet_telemetry_field_received_at": {
            "PackCurrent": 1999_000,
            "PackVoltage": 1999_000,
        },
        "fleet_telemetry_field_previous_received_at": {
            "PackCurrent": 1998_000,
            "PackVoltage": 1998_000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
    }

    assert app._fleet_telemetrie_profile_live_takt_bestaetigt(daten, status) is False

    daten["fleet_telemetry_field_received_at"]["Location"] = 1999_000
    daten["fleet_telemetry_field_previous_received_at"]["Location"] = 1998_000

    assert app._fleet_telemetrie_profile_live_takt_bestaetigt(daten, status) is True


def test_fleet_telemetrie_profile_sendet_bei_altem_10s_takt_live_erneut(
    monkeypatch,
):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 1920.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "charging",
            "target": "live",
            "target_since": 1900.0,
            "last_sent": 1900.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": False,
            "config_key_paired": None,
            "config_sync_state": "pending",
            "config_sync_profile": "live",
            "config_sync_checked_at": 1900.0,
            "config_sync_updated_at": 1900.0,
            "config_sync_error": None,
            "config_sync_details": [{
                "vin": "TESTVIN",
                "synced": False,
            }],
            "updated_at": 1900.0,
        },
    )
    daten = {
        "vin": "TESTVIN",
        "fleet_telemetry_received_at": 1919_000,
        "fleet_telemetry_field_received_at": {"VehicleSpeed": 1919_000},
        "fleet_telemetry_field_previous_received_at": {"VehicleSpeed": 1909_000},
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == ["live"]
    assert daten["telemetry_profile"] == "charging"
    assert daten["telemetry_profile_target"] == "live"
    assert daten["telemetry_config_synced"] is False
    assert daten["telemetry_config_stream_active"] is False
    assert daten["telemetry_config_sync_state"] == "pending"
    assert daten["telemetry_live_retry_active"] is True
    assert app._fleet_telemetry_profile_status["current"] == "charging"
    assert app._fleet_telemetry_profile_status["config_sync_state"] == "pending"


def test_fleet_telemetrie_profile_sendet_live_bei_10s_takt_erneut(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2300.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_SEND_COOLDOWN_SECONDS", 60.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 2000.0,
            "last_sent": 2100.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live",
            "config_sync_checked_at": 2101.0,
            "config_sync_updated_at": 2101.0,
            "config_sync_error": None,
            "config_sync_details": _telemetrie_stream_details(),
            "live_stable_since": 0.0,
            "live_unstable_since": 2290.0,
            "updated_at": 2101.0,
        },
    )
    daten = {
        "vin": "TESTVIN",
        "fleet_telemetry_received_at": 2_299_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_299_000,
            "PackCurrent": 2_299_000,
            "Location": 2_299_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 10_000,
            "PackCurrent": 10_000,
            "Location": 10_000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == ["live"]
    assert daten["telemetry_profile"] == "live"
    assert daten["telemetry_config_synced"] is False
    assert daten["telemetry_config_sync_state"] == "pending"
    assert app._fleet_telemetry_profile_status["current"] == "live"
    assert app._fleet_telemetry_profile_status["config_synced"] is False
    assert app._fleet_telemetry_profile_status["config_sync_state"] == "pending"


def test_fleet_telemetrie_profile_postet_nicht_in_neuverbindungsruhe(
    monkeypatch,
):
    angefordert = []
    monkeypatch.setattr(app.time, "time", lambda: 2300.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angefordert.append,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            2100.0,
            live_unstable_since=2290.0,
            live_reconnect_seen_at=2295.0,
        ),
    )
    daten = {
        "vin": "TESTVIN",
        "fleet_telemetry_received_at": 2_299_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_299_000,
            "PackCurrent": 2_299_000,
            "Location": 2_299_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 10_000,
            "PackCurrent": 10_000,
            "Location": 10_000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert app._fleet_telemetry_profile_status["last_sent"] == 2100.0
    assert app._fleet_telemetry_profile_status["live_reconnect_seen_at"] == 2295.0


def test_fleet_telemetrie_profile_sendet_live_dann_live_plus_und_wartet(
    monkeypatch,
):
    jetzt = [2014.9]
    gesendet = []

    monkeypatch.setattr(app.time, "time", lambda: jetzt[0])
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_NEUVERSAND_INTERVAL_SECONDS",
        5.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_NEUVERSAND_BEWEGUNGSNACHLAUF_SECONDS",
        300.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_REPARATUR_NEUVERBINDUNG_SECONDS",
        120.0,
    )
    monkeypatch.setattr(app, "latest_data", {})

    def profil_anwenden(profil):
        gesendet.append((profil, jetzt[0]))
        app._fleet_telemetrie_profile_versand_vermerken(profil, jetzt[0])
        return {
            "synced": True,
            "key_paired": None,
            "state": "synced",
            "details": [{"vin": "TESTVIN", "synced": True}],
            "checked_at": jetzt[0],
            "error": None,
        }

    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_anwenden",
        profil_anwenden,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_sync_pruefen",
        lambda: {
            "synced": False,
            "key_paired": None,
            "state": "pending",
            "details": [],
            "checked_at": jetzt[0],
            "error": None,
        },
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            2010.0,
            config_synced=False,
            config_sync_state="pending",
            config_sync_details=[],
            live_retry_active=True,
            live_retry_started_at=2010.0,
            live_retry_last_moving_at=2010.0,
            live_retry_motion_active=True,
        ),
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert gesendet == []

    jetzt[0] = 2015.0
    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert gesendet == [("live", 2015.0)]

    jetzt[0] = 2020.0
    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert gesendet == [("live", 2015.0), ("live_extended", 2020.0)]

    jetzt[0] = 2025.1
    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert gesendet == [("live", 2015.0), ("live_extended", 2020.0)]

    jetzt[0] = 2140.1
    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert gesendet == [
        ("live", 2015.0),
        ("live_extended", 2020.0),
        ("live", 2140.1),
    ]

    jetzt[0] = 2145.1
    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert gesendet == [
        ("live", 2015.0),
        ("live_extended", 2020.0),
        ("live", 2140.1),
    ]

    jetzt[0] = 2260.2
    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert gesendet == [
        ("live", 2015.0),
        ("live_extended", 2020.0),
        ("live", 2140.1),
        ("live_extended", 2260.2),
    ]


def test_fleet_telemetrie_profile_worker_laesst_live_stream_einpendeln(
    monkeypatch,
):
    pruefungen = []

    monkeypatch.setattr(app.time, "time", lambda: 2015.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_NEUVERSAND_INTERVAL_SECONDS",
        5.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_NEUVERSAND_EINPENDEL_SECONDS",
        20.0,
    )
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "fleet_telemetry_received_at": 2_011_000,
            "state_checked_at": 2_015_000,
        },
    })
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_sync_pruefen",
        lambda: pruefungen.append("sync") or {
            "synced": False,
            "key_paired": None,
            "state": "pending",
            "details": [],
            "checked_at": 2015.0,
            "error": None,
        },
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_anwenden",
        lambda profil: pytest.fail(
            f"Profil {profil} wurde während der Einpendelphase erneut gesendet"
        ),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            2010.0,
            config_synced=False,
            config_sync_state="pending",
            config_sync_details=[],
            live_retry_active=True,
            live_retry_started_at=2010.0,
            live_retry_last_moving_at=2015.0,
            live_retry_motion_active=True,
        ),
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert pruefungen == ["sync"]
    assert app._fleet_telemetry_profile_status["last_sent"] == 2010.0


def test_fleet_telemetrie_profile_rest_status_startet_keine_einpendelphase():
    status = _bestaetigter_profilstatus(
        "live",
        2010.0,
        live_retry_active=True,
    )
    daten = {
        "fleet_telemetry_received_at": 2_009_000,
        "state_checked_at": 2_015_000,
    }

    assert not app._fleet_telemetrie_profile_live_stream_pendelt_sich_ein(
        daten,
        status,
        2015.0,
    )


def test_fleet_telemetrie_profile_startet_live_reparatur_ohne_neues_paket(
    monkeypatch,
):
    gesendet = []

    monkeypatch.setattr(app.time, "time", lambda: 2015.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_NEUVERSAND_INTERVAL_SECONDS",
        5.0,
    )
    monkeypatch.setattr(app, "latest_data", {})

    def profil_anwenden(profil):
        gesendet.append(profil)
        app._fleet_telemetrie_profile_versand_vermerken(profil, 2015.0)
        return {
            "synced": True,
            "key_paired": None,
            "state": "synced",
            "details": [{"vin": "TESTVIN", "synced": True}],
            "checked_at": 2015.0,
            "error": None,
        }

    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_anwenden",
        profil_anwenden,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            2010.0,
            config_sync_details=[{"vin": "TESTVIN", "synced": True}],
            live_retry_motion_active=True,
            live_retry_last_moving_at=2015.0,
        ),
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    status = app._fleet_telemetry_profile_status
    assert gesendet == ["live"]
    assert status["target"] == "live"
    assert status["live_retry_active"] is True
    assert status["live_retry_attempts"] == 1


def test_fleet_telemetrie_profile_worker_erkennt_stillen_fahrtstream(
    monkeypatch,
):
    jetzt = [2004.0]
    angefordert = []
    daten = {
        "vin": "TESTVIN",
        "state": "online",
        "fleet_telemetry_received_at": 2_000_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_000_000,
            "PackCurrent": 2_000_000,
            "PackVoltage": 2_000_000,
            "Location": 2_000_000,
        },
        "fleet_telemetry_field_previous_received_at": {
            "VehicleSpeed": 1_999_000,
            "PackCurrent": 1_999_000,
            "PackVoltage": 1_999_000,
            "Location": 1_999_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "PackVoltage": 1000,
            "Location": 1000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    monkeypatch.setattr(app.time, "time", lambda: jetzt[0])
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktiviert", lambda: True)
    monkeypatch.setattr(app, "latest_data", {"veh-1": daten})
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angefordert.append,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live_extended",
            1900.0,
            target="live",
            target_since=1800.0,
            live_stable_since=1900.0,
            live_retry_motion_active=True,
            live_retry_last_moving_at=2000.0,
        ),
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert angefordert == []
    assert app._fleet_telemetry_profile_status["live_unstable_since"] == 2004.0

    jetzt[0] = 2009.0
    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    status = app._fleet_telemetry_profile_status
    assert angefordert == ["live"]
    assert status["live_retry_active"] is True
    assert status["config_sync_state"] == "pending"
    assert status["config_sync_profile"] == "live"


def test_fleet_telemetrie_profile_wartet_nach_wiederanlauf_vor_neuversand(
    monkeypatch,
):
    jetzt = [2302.0]
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: jetzt[0])
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_NEUVERSAND_INTERVAL_SECONDS",
        5.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_NEUVERSAND_EINPENDEL_SECONDS",
        20.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angefordert.append,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            2300.0,
            config_synced=False,
            config_sync_state="pending",
            config_sync_details=[],
            live_retry_active=True,
            live_retry_started_at=2290.0,
            live_retry_last_moving_at=2302.0,
            live_retry_motion_active=True,
        ),
    )
    daten = {
        "vin": "TESTVIN",
        "fleet_telemetry_received_at": 2_302_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_302_000,
            "Location": 2_302_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 30_000,
            "Location": 30_000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []

    jetzt[0] = 2305.0
    daten["fleet_telemetry_received_at"] = 2_305_000
    daten["fleet_telemetry_field_received_at"]["VehicleSpeed"] = 2_305_000
    daten["fleet_telemetry_field_received_at"]["Location"] = 2_305_000
    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []

    jetzt[0] = 2320.0
    daten["fleet_telemetry_received_at"] = 2_320_000
    daten["fleet_telemetry_field_received_at"]["VehicleSpeed"] = 2_320_000
    daten["fleet_telemetry_field_received_at"]["Location"] = 2_320_000
    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == ["live"]


def test_fleet_telemetrie_profile_erweitert_bestaetigtes_basisprofil(
    monkeypatch,
):
    jetzt = [2002.0]
    angefordert = []
    monkeypatch.setattr(app.time, "time", lambda: jetzt[0])
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angefordert.append,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            2000.0,
            config_synced=False,
            config_sync_state="pending",
            config_sync_details=[],
            live_retry_active=True,
            live_retry_started_at=1995.0,
            live_retry_last_moving_at=2001.0,
            live_retry_motion_active=True,
            live_retry_attempts=1,
            live_recovery_bootstrap_active=True,
        ),
    )
    daten = {
        "vin": "TESTVIN",
        "fleet_telemetry_received_at": 2_002_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_002_000,
            "PackCurrent": 2_002_000,
            "Location": 2_002_000,
        },
        "fleet_telemetry_field_previous_received_at": {
            "VehicleSpeed": 2_001_000,
            "PackCurrent": 2_001_000,
            "Location": 2_001_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "Location": 1000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)
    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    status = app._fleet_telemetry_profile_status
    assert angefordert == ["live"]
    assert status["live_retry_active"] is True
    assert status["live_recovery_bootstrap_active"] is False
    assert status["live_recovery_full_pending"] is True
    assert status["live_recovery_bootstrap_confirmed_at"] == 2002.0

    app._fleet_telemetrie_profile_versand_vermerken(
        "live",
        jetzt=2003.0,
        wiederherstellung=False,
    )
    jetzt[0] = 2005.0
    daten["fleet_telemetry_received_at"] = 2_005_000
    for feld in ("VehicleSpeed", "PackCurrent", "Location"):
        daten["fleet_telemetry_field_previous_received_at"][feld] = 2_004_000
        daten["fleet_telemetry_field_received_at"][feld] = 2_005_000

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert status["live_retry_active"] is False
    assert status["live_retry_confirmed_at"] == 2005.0
    assert status["live_recovery_full_pending"] is False


def test_fleet_telemetrie_profile_beendet_neuversand_bei_1s_takt(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2002.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angefordert.append,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            2000.0,
            config_synced=False,
            config_sync_state="pending",
            config_sync_details=[],
            live_retry_active=True,
            live_retry_started_at=1995.0,
            live_retry_last_moving_at=2001.0,
            live_retry_motion_active=True,
            live_retry_attempts=3,
        ),
    )
    daten = {
        "vin": "TESTVIN",
        "fleet_telemetry_received_at": 2_002_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_002_000,
            "PackCurrent": 2_002_000,
            "Location": 2_002_000,
        },
        "fleet_telemetry_field_previous_received_at": {
            "VehicleSpeed": 2_001_000,
            "PackCurrent": 2_001_000,
            "Location": 2_001_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "Location": 1000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert daten["telemetry_profile"] == "live"
    assert daten["telemetry_config_synced"] is True
    assert daten["telemetry_config_sync_state"] == "synced"
    assert daten["telemetry_live_retry_active"] is False
    assert daten["telemetry_live_retry_confirmed_at"] == 2002.0
    assert daten["telemetry_live_retry_attempts"] == 3


def test_fleet_telemetrie_profile_sendet_live_an_ampel_nicht_erneut(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2300.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 2000.0,
            "last_sent": 2100.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live",
            "config_sync_checked_at": 2101.0,
            "config_sync_updated_at": 2101.0,
            "config_sync_error": None,
            "config_sync_details": _telemetrie_stream_details(),
            "live_stable_since": 0.0,
            "updated_at": 2101.0,
        },
    )
    daten = {
        "fleet_telemetry_received_at": 2_299_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_299_000,
            "PackCurrent": 2_299_000,
            "Location": 2_299_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 10_000,
            "PackCurrent": 10_000,
            "Location": 10_000,
        },
        "drive_state": {"shift_state": "D", "speed": 0},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert daten["telemetry_profile"] == "live"
    assert daten["telemetry_config_synced"] is True
    assert daten["telemetry_config_sync_state"] == "synced"


def test_fleet_telemetrie_profile_wartet_beim_wiederanfahren_auf_position(
    monkeypatch,
):
    jetzt = [2300.0]
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: jetzt[0])
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angefordert.append,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live_extended",
            2100.0,
            target="live",
            live_stable_since=2200.0,
            live_unstable_since=2290.0,
        ),
    )
    daten = {
        "vin": "TESTVIN",
        "fleet_telemetry_received_at": 2_300_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_260_000,
            "PackCurrent": 2_260_000,
            "Location": 2_260_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 40_000,
            "PackCurrent": 40_000,
            "Location": 40_000,
        },
        "drive_state": {"shift_state": "D", "speed": 0},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert daten["telemetry_profile"] == "live_extended"
    assert app._fleet_telemetry_profile_status["live_unstable_since"] == 0.0

    jetzt[0] = 2301.0
    daten["fleet_telemetry_received_at"] = 2_301_000
    daten["fleet_telemetry_field_received_at"]["VehicleSpeed"] = 2_301_000
    daten["drive_state"]["speed"] = 12

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert daten["telemetry_profile"] == "live_extended"
    assert app._fleet_telemetry_profile_status["live_unstable_since"] == 2301.0

    jetzt[0] = 2302.0
    daten["fleet_telemetry_received_at"] = 2_302_000
    daten["fleet_telemetry_field_received_at"].update({
        "VehicleSpeed": 2_302_000,
        "PackCurrent": 2_302_000,
        "Location": 2_302_000,
    })
    daten["fleet_telemetry_field_interval_ms"].update({
        "VehicleSpeed": 1000,
        "PackCurrent": 1000,
        "Location": 42_000,
    })

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert daten["telemetry_profile"] == "live_extended"
    assert daten["telemetry_config_synced"] is True
    assert app._fleet_telemetry_profile_status["live_unstable_since"] == 0.0


def test_fleet_telemetrie_profile_wartet_vor_takt_neuversand(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2110.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 2000.0,
            "last_sent": 2100.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live",
            "config_sync_checked_at": 2101.0,
            "config_sync_updated_at": 2101.0,
            "config_sync_error": None,
            "config_sync_details": _telemetrie_stream_details(),
            "live_stable_since": 0.0,
            "updated_at": 2101.0,
        },
    )
    daten = {
        "fleet_telemetry_received_at": 2_109_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_109_000,
            "PackCurrent": 2_109_000,
            "Location": 2_109_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 10_000,
            "PackCurrent": 10_000,
            "Location": 10_000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert daten["telemetry_profile"] == "live"
    assert daten["telemetry_config_synced"] is True


def test_fleet_telemetrie_profile_bestaetigt_api_sync_nicht_bei_10s_takt(
    monkeypatch,
):
    jetzt = [2300.0]
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: jetzt[0])
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_NEUVERSAND_EINPENDEL_SECONDS",
        20.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "parked",
            "target": "live",
            "target_since": 2280.0,
            "last_sent": 2290.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live",
            "config_sync_checked_at": 2291.0,
            "config_sync_updated_at": 2291.0,
            "config_sync_error": None,
            "config_sync_details": [{
                "vin": "TESTVIN",
                "synced": True,
                "limit_reached": False,
            }],
            "live_stable_since": 0.0,
            "updated_at": 2291.0,
        },
    )
    daten = {
        "vin": "TESTVIN",
        "fleet_telemetry_received_at": 2_299_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_299_000,
        },
        "fleet_telemetry_field_previous_received_at": {
            "VehicleSpeed": 2_289_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 10_000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert daten["telemetry_live_retry_active"] is True

    jetzt[0] = 2310.0
    daten["fleet_telemetry_received_at"] = 2_309_000
    daten["fleet_telemetry_field_previous_received_at"][
        "VehicleSpeed"
    ] = 2_299_000
    daten["fleet_telemetry_field_received_at"]["VehicleSpeed"] = 2_309_000
    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == ["live"]
    assert daten["telemetry_profile"] == "parked"
    assert daten["telemetry_profile_target"] == "live"
    assert daten["telemetry_config_synced"] is False
    assert daten["telemetry_config_sync_state"] == "pending"
    assert daten["telemetry_live_retry_active"] is True
    assert app._fleet_telemetry_profile_status["current"] == "parked"
    assert app._fleet_telemetry_profile_status["config_sync_details"] == []


def test_fleet_telemetrie_profile_live_stabil_toleriert_parkende_luecke():
    daten = {
        "fleet_telemetry_field_received_at": {
            "PackCurrent": 2_000_000,
            "PackVoltage": 2_000_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "PackCurrent": 1500,
            "PackVoltage": 1000,
        },
    }

    assert app._fleet_telemetrie_profile_live_takt_stabil(daten, 2000.0) is True


def test_fleet_telemetrie_profile_live_stabil_toleriert_ampelstillstand():
    daten = {
        "fleet_telemetry_field_received_at": {
            "PackCurrent": 2_000_000,
            "PackVoltage": 2_000_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "PackCurrent": 1000,
            "PackVoltage": 1000,
        },
        "drive_state": {"shift_state": "D", "speed": 0},
    }

    assert app._fleet_telemetrie_profile_live_takt_stabil(daten, 2000.0) is True


def test_fleet_telemetrie_profile_live_stabil_verwirft_10s_takt():
    daten = {
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_000_000,
            "PackCurrent": 2_000_000,
            "PackVoltage": 2_000_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 10_000,
            "PackCurrent": 10_000,
            "PackVoltage": 10_000,
        },
    }

    assert app._fleet_telemetrie_profile_live_takt_stabil(daten, 2000.0) is False


def test_fleet_telemetrie_profile_live_stabil_verwirft_stillen_fahrtstream():
    daten = {
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_000_000,
            "PackCurrent": 2_000_000,
            "PackVoltage": 2_000_000,
            "Location": 2_000_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "PackVoltage": 1000,
            "Location": 1000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
    }

    assert app._fleet_telemetrie_profile_live_takt_stabil(daten, 2003.0)
    assert not app._fleet_telemetrie_profile_live_takt_stabil(daten, 2003.1)


def test_fleet_telemetrie_profile_bewegung_verlangt_frische_geschwindigkeit():
    daten = {
        "fleet_telemetry_field_received_at": {"VehicleSpeed": 2_000_000},
        "drive_state": {"shift_state": "D", "speed": 12},
    }

    assert app._fleet_telemetrie_profile_fahrzeug_bewegt_sich(daten, 2000.0)
    assert not app._fleet_telemetrie_profile_fahrzeug_bewegt_sich(daten, 2016.0)

    daten["drive_state"]["speed"] = 0

    assert not app._fleet_telemetrie_profile_fahrzeug_bewegt_sich(daten, 2000.0)

    daten["drive_state"]["speed"] = 2

    assert not app._fleet_telemetrie_profile_fahrzeug_bewegt_sich(daten, 2000.0)

    daten["drive_state"]["speed"] = 12
    daten["fleet_vehicle_data_received_at"] = 2_019_000

    assert app._fleet_telemetrie_profile_fahrzeug_bewegt_sich(daten, 2020.0)


def test_fleet_telemetrie_profile_live_stabil_verlangt_position_beim_fahren():
    daten = {
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_000_000,
            "PackCurrent": 2_000_000,
            "PackVoltage": 2_000_000,
            "Location": 1_997_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "PackVoltage": 1000,
            "Location": 60_000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
    }

    assert app._fleet_telemetrie_profile_live_takt_stabil(daten, 2000.0) is False

    daten["fleet_telemetry_field_interval_ms"]["Location"] = 1000

    assert app._fleet_telemetrie_profile_live_takt_stabil(daten, 2000.0) is True


def test_fleet_telemetrie_profile_live_stabil_erkennt_wiederanfahrt():
    daten = {
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_000_000,
            "PackCurrent": 2_000_000,
            "Location": 2_000_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "Location": 10_009,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
    }

    assert app._fleet_telemetrie_profile_live_takt_stabil(daten, 2000.0) is True
    assert app._fleet_telemetrie_profile_live_takt_stabil(daten, 2002.1) is False


def test_fleet_telemetrie_profile_live_stabil_toleriert_positionsjitter():
    daten = {
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_000_000,
            "PackCurrent": 2_000_000,
            "Location": 2_000_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "Location": 3004,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
    }

    assert app._fleet_telemetrie_profile_live_takt_stabil(daten, 2000.0) is True

    daten["fleet_telemetry_field_interval_ms"]["Location"] = 5001

    assert app._fleet_telemetrie_profile_live_takt_stabil(daten, 2002.1) is False


def test_fleet_telemetrie_profile_erweitert_stabiles_live(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2100.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_LIVE_EXTENDED_DELAY_SECONDS", 60.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 2000.0,
            "last_sent": 2000.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live",
            "config_sync_checked_at": 2001.0,
            "config_sync_updated_at": 2001.0,
            "config_sync_error": None,
            "config_sync_details": _telemetrie_stream_details(),
            "live_stable_since": 2000.0,
            "updated_at": 2001.0,
        },
    )
    daten = {
        "fleet_telemetry_received_at": 2_099_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_099_000,
            "PackCurrent": 2_099_000,
            "Location": 2_099_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "Location": 1000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == ["live_extended"]
    assert daten["telemetry_profile"] == "live"
    assert daten["telemetry_config_sync_profile"] == "live_extended"
    assert app._fleet_telemetry_profile_status["config_sync_state"] == "pending"


def test_fleet_telemetrie_profile_erweitert_auch_ohne_qr_pairing(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2100.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_EXTENDED_DELAY_SECONDS",
        60.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angefordert.append,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            2000.0,
            live_stable_since=2000.0,
        ),
    )
    daten = {
        "fleet_telemetry_received_at": 2_099_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_099_000,
            "PackCurrent": 2_099_000,
            "Location": 2_099_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "Location": 1000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
        "vehicle_config": {"supports_qr_pairing": False},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == ["live_extended"]
    assert daten["telemetry_profile"] == "live"
    assert daten["telemetry_config_sync_profile"] == "live_extended"


def test_fleet_telemetrie_profile_behaelt_live_plus_ohne_qr_pairing(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2100.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angefordert.append,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live_extended",
            2000.0,
            target="live",
            live_stable_since=2000.0,
        ),
    )
    daten = {
        "fleet_telemetry_received_at": 2_099_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_099_000,
            "PackCurrent": 2_099_000,
            "Location": 2_099_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "Location": 1000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
        "vehicle_config": {"supports_qr_pairing": False},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert daten["telemetry_profile"] == "live_extended"
    assert daten["telemetry_config_sync_profile"] == "live_extended"


def test_fleet_telemetrie_profile_ignoriert_abbruch_nach_live_plus_post(
    monkeypatch,
):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2100.5)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angefordert.append,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            2000.0,
            target="live",
            last_sent=2100.0,
            last_sent_profile="live_extended",
            last_posted_at=2100.1,
            last_posted_profile="live_extended",
            config_synced=False,
            config_sync_state="pending",
            config_sync_profile="live_extended",
            live_stable_since=2000.0,
        ),
    )
    daten = {
        "state": "offline",
        "state_since_ms": 2_100_400,
        "drive_state": {"shift_state": "R", "speed": 3.6},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    status = app._fleet_telemetry_profile_status
    assert angefordert == []
    assert status["target"] == "live"
    assert status["live_stable_since"] == 2000.0
    assert status["last_sent_profile"] == "live_extended"
    assert daten["telemetry_profile_target"] == "live"


def test_fleet_telemetrie_profile_ignoriert_abbruch_nach_erstem_live_post(
    monkeypatch,
):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2100.5)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angefordert.append,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "parked",
            2000.0,
            target="live",
            target_since=2100.0,
            last_sent=2100.0,
            last_sent_profile="live",
            last_posted_at=2100.1,
            last_posted_profile="live",
            config_synced=False,
            config_sync_state="pending",
            config_sync_profile="live",
        ),
    )
    daten = {
        "state": "offline",
        "state_since_ms": 2_100_400,
        "drive_state": {"shift_state": "P", "speed": 0},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    status = app._fleet_telemetry_profile_status
    assert angefordert == []
    assert status["target"] == "live"
    assert status["last_sent_profile"] == "live"
    assert daten["telemetry_profile_target"] == "live"


def test_fleet_telemetrie_profile_wertet_spaeten_abbruch_als_offline(
    monkeypatch,
):
    monkeypatch.setattr(app.time, "time", lambda: 2200.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_ERWARTETE_NEUVERBINDUNG_SECONDS",
        30.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live_extended",
            2000.0,
            target="live",
            last_posted_at=2100.0,
            last_posted_profile="live_extended",
            live_stable_since=2000.0,
        ),
    )
    daten = {
        "state": "offline",
        "state_since_ms": 2_199_000,
        "drive_state": {"shift_state": "D", "speed": 20},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    status = app._fleet_telemetry_profile_status
    assert status["target"] == "parked"
    assert status["live_stable_since"] == 0.0
    assert daten["telemetry_profile_target"] == "parked"


def test_fleet_telemetrie_profile_erweitert_wartet_auf_stabilitaet(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2100.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_EXTENDED_DELAY_SECONDS",
        60.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 2000.0,
            "last_sent": 2000.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live",
            "config_sync_checked_at": 2001.0,
            "config_sync_updated_at": 2001.0,
            "config_sync_error": None,
            "config_sync_details": _telemetrie_stream_details(),
            "live_stable_since": 0.0,
            "updated_at": 2001.0,
        },
    )
    daten = {
        "fleet_telemetry_received_at": 2_099_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_099_000,
            "PackCurrent": 2_099_000,
            "Location": 2_099_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "Location": 1000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert app._fleet_telemetry_profile_status["live_stable_since"] == 2100.0
    assert app._fleet_telemetry_profile_status["config_sync_profile"] == "live"


def test_fleet_telemetrie_profile_ueberschreibt_pending_extended_nicht(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2110.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 2000.0,
            "last_sent": 2100.0,
            "last_sent_profile": "live_extended",
            "last_error": None,
            "config_synced": False,
            "config_key_paired": None,
            "config_sync_state": "pending",
            "config_sync_profile": "live_extended",
            "config_sync_checked_at": 2100.0,
            "config_sync_updated_at": 2100.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "live_stable_since": 2000.0,
            "updated_at": 2100.0,
        },
    )
    daten = {
        "fleet_telemetry_received_at": 2_109_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_109_000,
            "PackCurrent": 2_109_000,
            "Location": 2_109_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "Location": 1000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert app._fleet_telemetry_profile_status["config_sync_profile"] == "live_extended"


def test_fleet_telemetrie_profile_haelt_pending_extended_waehrend_neuverbindung(
    monkeypatch,
):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2110.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_ERWARTETE_NEUVERBINDUNG_SECONDS",
        30.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 2000.0,
            "last_sent": 2100.0,
            "last_sent_profile": "live_extended",
            "last_error": None,
            "config_synced": False,
            "config_key_paired": None,
            "config_sync_state": "pending",
            "config_sync_profile": "live_extended",
            "config_sync_checked_at": 2100.0,
            "config_sync_updated_at": 2100.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "live_stable_since": 2000.0,
            "updated_at": 2100.0,
        },
    )
    daten = {
        "fleet_telemetry_received_at": 2_109_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_109_000,
            "PackCurrent": 2_109_000,
            "Location": 2_109_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 10_000,
            "PackCurrent": 10_000,
            "Location": 10_000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert app._fleet_telemetry_profile_status["last_sent_profile"] == (
        "live_extended"
    )
    assert app._fleet_telemetry_profile_status["config_sync_profile"] == (
        "live_extended"
    )


def test_fleet_telemetrie_profile_haelt_parallel_angefordertes_live_plus(
    monkeypatch,
):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2099.9)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_ERWARTETE_NEUVERBINDUNG_SECONDS",
        30.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angefordert.append,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 2000.0,
            "last_sent": 2100.0,
            "last_sent_profile": "live_extended",
            "last_posted_profile": "live_extended",
            "last_error": None,
            "config_synced": False,
            "config_key_paired": None,
            "config_sync_state": "pending",
            "config_sync_profile": "live_extended",
            "config_sync_checked_at": 2100.0,
            "config_sync_updated_at": 2100.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "live_stable_since": 2000.0,
            "updated_at": 2100.0,
        },
    )
    daten = {
        "fleet_telemetry_received_at": 2_099_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_099_000,
            "PackCurrent": 2_099_000,
            "Location": 2_099_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 10_000,
            "PackCurrent": 10_000,
            "Location": 10_000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert app._fleet_telemetry_profile_status["last_sent_profile"] == (
        "live_extended"
    )
    assert app._fleet_telemetry_profile_status["config_sync_profile"] == (
        "live_extended"
    )


def test_fleet_telemetrie_profile_haelt_bestaetigtes_extended_beim_neustart(
    monkeypatch,
):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2110.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_ERWARTETE_NEUVERBINDUNG_SECONDS",
        30.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live_extended",
            "target": "live",
            "target_since": 2000.0,
            "last_sent": 2100.0,
            "last_sent_profile": "live_extended",
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live_extended",
            "config_sync_checked_at": 2101.0,
            "config_sync_updated_at": 2101.0,
            "config_sync_error": None,
            "config_sync_details": _telemetrie_stream_details(),
            "live_stable_since": 2000.0,
            "updated_at": 2101.0,
        },
    )
    daten = {
        "fleet_telemetry_received_at": 2_109_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_109_000,
            "PackCurrent": 2_109_000,
            "Location": 2_109_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 10_000,
            "PackCurrent": 10_000,
            "Location": 10_000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert app._fleet_telemetry_profile_status["last_sent_profile"] == (
        "live_extended"
    )
    assert app._fleet_telemetry_profile_status["config_sync_profile"] == (
        "live_extended"
    )


def test_fleet_telemetrie_profile_faellt_bei_instabilem_extended_auf_live(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2200.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_INSTABIL_TOLERANZ_SECONDS",
        5.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live_extended",
            "target": "live",
            "target_since": 2000.0,
            "last_sent": 2100.0,
            "last_sent_profile": "live_extended",
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live_extended",
            "config_sync_checked_at": 2101.0,
            "config_sync_updated_at": 2101.0,
            "config_sync_error": None,
            "config_sync_details": _telemetrie_stream_details(),
            "live_stable_since": 2000.0,
            "updated_at": 2101.0,
        },
    )
    daten = {
        "fleet_telemetry_received_at": 2_199_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_190_000,
            "PackCurrent": 2_190_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 30000,
            "PackCurrent": 30000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert daten["telemetry_profile"] == "live_extended"
    assert app._fleet_telemetry_profile_status["live_stable_since"] == 2000.0

    monkeypatch.setattr(app.time, "time", lambda: 2205.0)
    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == ["live"]
    assert app._fleet_telemetry_profile_status["config_sync_profile"] == "live"
    assert app._fleet_telemetry_profile_status["live_stable_since"] == 0.0


def test_fleet_telemetrie_profile_ignoriert_kurzen_live_aussetzer(monkeypatch):
    angefordert = []
    jetzt = [2200.0]

    monkeypatch.setattr(app.time, "time", lambda: jetzt[0])
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_LIVE_INSTABIL_TOLERANZ_SECONDS",
        5.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live_extended",
            "target": "live",
            "target_since": 2000.0,
            "last_sent": 2100.0,
            "last_sent_profile": "live_extended",
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live_extended",
            "config_sync_checked_at": 2101.0,
            "config_sync_updated_at": 2101.0,
            "config_sync_error": None,
            "config_sync_details": _telemetrie_stream_details(),
            "live_stable_since": 2000.0,
            "updated_at": 2101.0,
        },
    )
    instabil = {
        "fleet_telemetry_received_at": 2_200_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_180_000,
            "PackCurrent": 2_180_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 20000,
            "PackCurrent": 20000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", instabil)

    assert angefordert == []
    assert daten["telemetry_profile"] == "live_extended"
    assert app._fleet_telemetry_profile_status["live_stable_since"] == 2000.0

    jetzt[0] = 2201.0
    stabil = {
        "fleet_telemetry_received_at": 2_201_000,
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": 2_201_000,
            "PackCurrent": 2_201_000,
            "Location": 2_201_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "VehicleSpeed": 1000,
            "PackCurrent": 1000,
            "Location": 1000,
        },
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }

    daten = app._fleet_telemetrie_profile_aktualisieren("veh-1", stabil)

    assert angefordert == []
    assert daten["telemetry_profile"] == "live_extended"
    assert app._fleet_telemetry_profile_status["live_stable_since"] == 2000.0
    assert (
        app._fleet_telemetry_profile_status.get("live_unstable_since", 0.0)
        == 0.0
    )


def test_fleet_telemetrie_profile_ueberschreibt_pending_live_nicht(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2210.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live_extended",
            "target": "live",
            "target_since": 2000.0,
            "last_sent": 2200.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": False,
            "config_key_paired": None,
            "config_sync_state": "pending",
            "config_sync_profile": "live",
            "config_sync_checked_at": 2200.0,
            "config_sync_updated_at": 2200.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "live_stable_since": 2200.0,
            "updated_at": 2200.0,
        },
    )
    daten = {
        "fleet_telemetry_received_at": 2_209_000,
        "fleet_telemetry_field_received_at": {
            "PackCurrent": 2_209_000,
            "PackVoltage": 2_209_000,
        },
        "fleet_telemetry_field_interval_ms": {
            "PackCurrent": 1000,
            "PackVoltage": 1000,
        },
        "drive_state": {"shift_state": "P", "speed": 0},
        "climate_state": {"is_climate_on": True},
        "charge_state": {"charging_state": "Disconnected"},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert app._fleet_telemetry_profile_status["config_sync_profile"] == "live"


def test_fleet_telemetrie_profile_erfolg_setzt_current_erst_nach_sync(monkeypatch):
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "charging",
            "target": "live",
            "target_since": 1900.0,
            "last_sent": 1900.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": False,
            "config_key_paired": None,
            "config_sync_state": "pending",
            "config_sync_profile": "live",
            "config_sync_checked_at": 1900.0,
            "config_sync_updated_at": 1900.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "updated_at": 1900.0,
        },
    )

    app._fleet_telemetrie_profile_erfolg_setzen("live", {
        "synced": False,
        "key_paired": None,
        "state": "pending",
        "details": [{"vin": "TESTVIN", "synced": False}],
        "checked_at": 2000.0,
        "error": None,
    })

    assert app._fleet_telemetry_profile_status["current"] == "charging"

    assert app._fleet_telemetrie_profile_erfolg_setzen("live", {
        "synced": True,
        "key_paired": None,
        "state": "synced",
        "details": [{"vin": "TESTVIN", "synced": True}],
        "checked_at": 2001.0,
        "error": None,
    })

    assert app._fleet_telemetry_profile_status["current"] == "charging"

    app._fleet_telemetrie_profile_erfolg_setzen("live", {
        "synced": True,
        "key_paired": None,
        "state": "synced",
        "details": _telemetrie_stream_details(),
        "checked_at": 2002.0,
        "error": None,
    })

    assert app._fleet_telemetry_profile_status["current"] == "live"


def test_fleet_telemetrie_profile_ignoriert_veralteten_erfolg(monkeypatch):
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "charging",
            1999.0,
            current="live",
            last_posted_at=1998.0,
            last_posted_profile="live",
            config_synced=False,
            config_sync_state="pending",
            config_sync_details=[],
        ),
    )

    app._fleet_telemetrie_profile_erfolg_setzen("live", {
        "synced": True,
        "key_paired": None,
        "state": "synced",
        "details": _telemetrie_stream_details(),
        "checked_at": 2000.0,
        "error": None,
    }) is False

    status = app._fleet_telemetry_profile_status
    assert status["current"] == "live"
    assert status["config_synced"] is False
    assert status["config_sync_state"] == "pending"
    assert status["config_sync_profile"] == "charging"

    assert app._fleet_telemetrie_profile_fehler_setzen(
        "live",
        RuntimeError("Veralteter Fehler"),
    ) is False
    assert status["target"] == "charging"
    assert status["last_error"] is None
    assert status["config_sync_profile"] == "charging"


def test_fleet_telemetrie_profile_merkt_tatsaechlichen_versand(monkeypatch):
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)

    app._fleet_telemetrie_profile_versand_vermerken("live")

    status = app._fleet_telemetry_profile_status
    assert status["last_posted_profile"] == "live"
    assert status["last_posted_at"] == 2000.0
    assert (
        status["config_revision"]
        == app.FLEET_TELEMETRIE_PROFILE_CONFIG_REVISION
    )


def test_fleet_telemetrie_alte_profildefinition_wird_neu_gesendet(
    monkeypatch,
    tmp_path,
):
    statusdatei = tmp_path / "telemetry-profile-status.json"
    statusdatei.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        app,
        "TESLA_FLEET_TELEMETRY_PROFILE_STATUS_FILE",
        str(statusdatei),
    )

    status = app._fleet_telemetrie_profile_status_laden()
    status.update({
        "config_synced": True,
        "config_sync_state": "synced",
        "config_sync_profile": "live",
    })

    assert status["config_revision"] is None
    assert not app._fleet_telemetrie_profile_api_sync_bestaetigt(status, "live")


def test_fleet_telemetrie_alte_profildefinition_fordert_profil_neu_an(
    monkeypatch,
):
    angefordert = []
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktiviert", lambda: True)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angefordert.append,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "parked",
            1000.0,
            config_revision=0,
        ),
    )
    daten = {
        "drive_state": {"shift_state": "P", "speed": 0},
        "vehicle_state": {"is_user_present": False},
        "climate_state": {"is_climate_on": False},
        "charge_state": {"charging_state": "Disconnected"},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == ["parked"]
    assert app._fleet_telemetry_profile_status["config_sync_state"] == "pending"


def test_fleet_telemetrie_profile_pending_prueft_vor_timeout_nur_sync(monkeypatch):
    pruefungen = []

    monkeypatch.setattr(app.time, "time", lambda: 1299.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_SYNC_CHECK_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_RESEND_AFTER_SECONDS", 300.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_sync_pruefen",
        lambda: pruefungen.append("sync") or {
            "synced": False,
            "key_paired": True,
            "state": "pending",
            "details": [],
            "checked_at": 1299.0,
            "error": None,
        },
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_anwenden",
        lambda profil: pytest.fail("Konfiguration wurde zu früh erneut gesendet"),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 1000.0,
            "last_sent": 1000.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": False,
            "config_key_paired": True,
            "config_sync_state": "pending",
            "config_sync_profile": "live",
            "config_sync_checked_at": 1200.0,
            "config_sync_updated_at": 1000.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "updated_at": 1000.0,
        },
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert pruefungen == ["sync"]
    assert app._fleet_telemetry_profile_status["last_sent"] == 1000.0
    assert app._fleet_telemetry_profile_status["config_sync_state"] == "pending"


def test_fleet_telemetrie_profile_worker_stuft_offline_nach_parkfrist_ab(
    monkeypatch,
):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 1_800_000_301.0)
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktiviert", lambda: True)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_PARK_DELAY_SECONDS",
        120.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "offline",
            "state_since_ms": 1_800_000_000_000,
            "drive_state": {"shift_state": "R", "speed": 12},
            "vehicle_state": {
                "center_display_state": "DisplayStateDriving",
                "is_user_present": True,
            },
            "climate_state": {"is_climate_on": True},
            "charge_state": {"charging_state": "Charging"},
            "v2l_active": True,
        },
    })
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus(
            "live",
            1_799_999_900.0,
            live_retry_active=True,
            live_retry_started_at=1_799_999_950.0,
            live_retry_last_moving_at=1_799_999_990.0,
            live_retry_motion_active=True,
        ),
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    status = app._fleet_telemetry_profile_status
    assert angefordert == ["parked"]
    assert status["target"] == "parked"
    assert status["target_since"] == 1_800_000_000.0
    assert status["last_sent_profile"] == "parked"
    assert status["config_sync_profile"] == "parked"
    assert status["config_sync_state"] == "pending"
    assert status["live_retry_active"] is False
    assert status["live_retry_motion_active"] is False


def test_fleet_telemetrie_profile_worker_wartet_offline_parkfrist_ab(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 1_800_000_090.0)
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktiviert", lambda: True)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_PARK_DELAY_SECONDS",
        120.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(app, "latest_data", {
        "veh-1": {
            "state": "offline",
            "state_since_ms": 1_800_000_000_000,
            "drive_state": {"shift_state": "R", "speed": 12},
        },
    })
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        _bestaetigter_profilstatus("live", 1_799_999_900.0),
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    status = app._fleet_telemetry_profile_status
    assert angefordert == []
    assert status["target"] == "parked"
    assert status["target_since"] == 1_800_000_000.0
    assert status["last_sent_profile"] == "live"
    assert status["config_sync_state"] == "synced"


def test_fleet_telemetrie_profile_prueft_nach_wechsel_schnell(monkeypatch):
    pruefungen = []

    monkeypatch.setattr(app.time, "time", lambda: 1012.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_SYNC_CHECK_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_SYNC_FAST_CHECK_INTERVAL_SECONDS",
        10.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_SYNC_FAST_WINDOW_SECONDS",
        180.0,
    )
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_RESEND_AFTER_SECONDS", 300.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_FAST_RESEND_AFTER_SECONDS", 60.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_sync_pruefen",
        lambda: pruefungen.append("sync") or {
            "synced": False,
            "key_paired": None,
            "state": "pending",
            "details": [],
            "checked_at": 1012.0,
            "error": None,
        },
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_anwenden",
        lambda profil: pytest.fail("Nach 12 Sekunden soll nur geprüft werden"),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "parked",
            "target": "live",
            "target_since": 1000.0,
            "last_sent": 1000.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": False,
            "config_key_paired": None,
            "config_sync_state": "pending",
            "config_sync_profile": "live",
            "config_sync_checked_at": 1000.0,
            "config_sync_updated_at": 1000.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "updated_at": 1000.0,
        },
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert pruefungen == ["sync"]
    assert app._fleet_telemetry_profile_status["last_sent"] == 1000.0


@pytest.mark.parametrize(
    ("config_synced", "config_sync_state", "config_sync_details"),
    [
        (False, "pending", []),
        (
            True,
            "synced",
            [{"vin": "TESTVIN", "synced": True, "limit_reached": False}],
        ),
    ],
)
def test_fleet_telemetrie_profile_sendet_in_schnellphase_erneut(
    monkeypatch,
    config_synced,
    config_sync_state,
    config_sync_details,
):
    gesendet = []

    monkeypatch.setattr(app.time, "time", lambda: 1061.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_SYNC_CHECK_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_SYNC_FAST_CHECK_INTERVAL_SECONDS",
        10.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_SYNC_FAST_WINDOW_SECONDS",
        180.0,
    )
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_RESEND_AFTER_SECONDS", 300.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_FAST_RESEND_AFTER_SECONDS", 60.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_anwenden",
        lambda profil: gesendet.append(profil) or {
            "synced": False,
            "key_paired": None,
            "state": "pending",
            "details": [{"vin": "TESTVIN", "synced": False}],
            "checked_at": 1061.0,
            "error": None,
        },
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_sync_pruefen",
        lambda: pytest.fail("Nach 60 Sekunden soll erneut gesendet werden"),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "parked",
            "target": "live",
            "target_since": 1000.0,
            "last_sent": 1000.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": config_synced,
            "config_key_paired": None,
            "config_sync_state": config_sync_state,
            "config_sync_profile": "live",
            "config_sync_checked_at": 1050.0,
            "config_sync_updated_at": 1000.0,
            "config_sync_error": None,
            "config_sync_details": config_sync_details,
            "updated_at": 1000.0,
        },
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert gesendet == ["live"]
    assert app._fleet_telemetry_profile_status["last_sent"] == 1061.0
    assert app._fleet_telemetry_profile_status["config_sync_state"] == "pending"


def test_fleet_telemetrie_profile_sendet_geparktes_profil_schnell_erneut(monkeypatch):
    gesendet = []

    monkeypatch.setattr(app.time, "time", lambda: 1181.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_SYNC_CHECK_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_SYNC_FAST_CHECK_INTERVAL_SECONDS",
        10.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_SYNC_FAST_WINDOW_SECONDS",
        120.0,
    )
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_RESEND_AFTER_SECONDS", 120.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_FAST_RESEND_AFTER_SECONDS", 60.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_anwenden",
        lambda profil: gesendet.append(profil) or {
            "synced": False,
            "key_paired": None,
            "state": "pending",
            "details": [{"vin": "TESTVIN", "synced": False}],
            "checked_at": 1181.0,
            "error": None,
        },
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_sync_pruefen",
        lambda: pytest.fail("Das geparkte Profil sollte schnell erneut gesendet werden"),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "parked",
            "target_since": 1000.0,
            "last_sent": 1120.0,
            "last_sent_profile": "parked",
            "last_error": None,
            "config_synced": False,
            "config_key_paired": None,
            "config_sync_state": "pending",
            "config_sync_profile": "parked",
            "config_sync_checked_at": 1170.0,
            "config_sync_updated_at": 1120.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "updated_at": 1120.0,
        },
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert gesendet == ["parked"]
    assert app._fleet_telemetry_profile_status["last_sent"] == 1181.0
    assert app._fleet_telemetry_profile_status["config_sync_state"] == "pending"


def test_fleet_telemetrie_profile_prueft_bestaetigtes_profil_nicht(monkeypatch):
    pruefungen = []

    monkeypatch.setattr(app.time, "time", lambda: 1012.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_SYNC_CHECK_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_SYNC_FAST_CHECK_INTERVAL_SECONDS",
        10.0,
    )
    monkeypatch.setattr(
        app,
        "FLEET_TELEMETRIE_PROFILE_SYNC_FAST_WINDOW_SECONDS",
        180.0,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_sync_pruefen",
        lambda: pruefungen.append("sync"),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_anwenden",
        lambda profil: pytest.fail("Bestätigtes Profil darf nicht erneut gesendet werden"),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 1000.0,
            "last_sent": 1000.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live",
            "config_sync_checked_at": 1000.0,
            "config_sync_updated_at": 1000.0,
            "config_sync_error": None,
            "config_sync_details": _telemetrie_stream_details(),
            "updated_at": 1000.0,
        },
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert pruefungen == []


def test_fleet_telemetrie_profile_sendet_nach_sync_timeout_erneut(monkeypatch):
    gesendet = []

    monkeypatch.setattr(app.time, "time", lambda: 1301.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_SYNC_CHECK_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_RESEND_AFTER_SECONDS", 300.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_anwenden",
        lambda profil: gesendet.append(profil) or {
            "synced": False,
            "key_paired": True,
            "state": "pending",
            "details": [{"vin": "TESTVIN", "synced": False}],
            "checked_at": 1301.0,
            "error": None,
        },
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_sync_pruefen",
        lambda: pytest.fail("Es sollte direkt erneut gesendet werden"),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 1000.0,
            "last_sent": 1000.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": False,
            "config_key_paired": True,
            "config_sync_state": "pending",
            "config_sync_profile": "live",
            "config_sync_checked_at": 1200.0,
            "config_sync_updated_at": 1000.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "updated_at": 1000.0,
        },
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert gesendet == ["live"]
    assert app._fleet_telemetry_profile_status["last_sent"] == 1301.0
    assert app._fleet_telemetry_profile_status["last_sent_profile"] == "live"
    assert app._fleet_telemetry_profile_status["config_sync_state"] == "pending"
    assert app._fleet_telemetry_profile_status["config_sync_checked_at"] == 1301.0
    assert app._fleet_telemetry_profile_status["config_sync_details"] == [{
        "vin": "TESTVIN",
        "synced": False,
    }]


def test_fleet_telemetrie_profile_prueft_syncprofil_mismatch(monkeypatch):
    pruefungen = []

    monkeypatch.setattr(app.time, "time", lambda: 1299.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_SYNC_CHECK_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_RESEND_AFTER_SECONDS", 300.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_sync_pruefen",
        lambda: pruefungen.append("sync") or {
            "synced": True,
            "key_paired": None,
            "state": "synced",
            "details": [{"vin": "TESTVIN", "synced": True}],
            "checked_at": 1299.0,
            "error": None,
        },
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_anwenden",
        lambda profil: pytest.fail("Vor dem Timeout soll nur geprüft werden"),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "parked",
            "target_since": 900.0,
            "last_sent": 1000.0,
            "last_sent_profile": "parked",
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live",
            "config_sync_checked_at": 1200.0,
            "config_sync_updated_at": 1200.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "updated_at": 1200.0,
        },
    )

    app._fleet_telemetrie_profile_sync_erneut_pruefen()

    assert pruefungen == ["sync"]
    assert app._fleet_telemetry_profile_status["config_sync_state"] == "synced"
    assert app._fleet_telemetry_profile_status["config_sync_profile"] == "parked"
    assert app._fleet_telemetry_profile_status["config_synced"] is True


def test_fleet_telemetrie_profile_laeuft_auch_bei_unveraendertem_paket(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 1301.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_PARK_DELAY_SECONDS", 300.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_ids",
        lambda vin: ["veh-1"],
    )
    monkeypatch.setattr(app, "_load_cached", lambda vehicle_id: {})
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)
    monkeypatch.setattr(app, "_aprs_spaeter_senden", lambda *args: None)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *args: None,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "parked",
            "target_since": 900.0,
            "last_sent": 1000.0,
            "last_sent_profile": "live",
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live",
            "config_sync_checked_at": 1200.0,
            "config_sync_updated_at": 1200.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "updated_at": 1200.0,
        },
    )
    monkeypatch.setattr(
        app,
        "latest_data",
        {
            "veh-1": {
                "vin": "VIN1",
                "state": "online",
                "fleet_telemetry_raw": {"LightsHazardsActive": False},
                "vehicle_state": {
                    "lights_hazards_active": False,
                    "locked": True,
                    "is_user_present": False,
                },
                "drive_state": {"shift_state": "P", "speed": 0},
                "climate_state": {"is_climate_on": False},
                "charge_state": {"charging_state": "Disconnected"},
            },
        },
    )

    assert app._fleet_telemetrie_v_felder_aktualisieren(
        "VIN1",
        [("LightsHazardsActive", False, 1_301_000)],
    )

    daten = app.latest_data["veh-1"]
    assert angefordert == ["parked"]
    assert daten["telemetry_config_synced"] is False
    assert daten["telemetry_config_sync_state"] == "pending"
    assert daten["telemetry_config_sync_profile"] == "parked"


def test_fleet_telemetrie_profile_verzoegert_parkprofil(monkeypatch):
    angefordert = []
    jetzt = [1000.0]

    monkeypatch.setattr(app.time, "time", lambda: jetzt[0])
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_PARK_DELAY_SECONDS", 120.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "live",
            "target": "live",
            "target_since": 0.0,
            "last_sent": 0.0,
            "last_sent_profile": None,
            "last_error": None,
            "config_synced": True,
            "config_key_paired": None,
            "config_sync_state": "synced",
            "config_sync_profile": "live",
            "config_sync_checked_at": 999.0,
            "config_sync_updated_at": 999.0,
            "config_sync_error": None,
            "config_sync_details": _telemetrie_stream_details(),
            "updated_at": 0.0,
        },
    )
    daten = {
        "drive_state": {"shift_state": "P", "speed": 0},
        "vehicle_state": {"locked": True, "is_user_present": False},
        "climate_state": {"is_climate_on": False},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert daten["telemetry_profile"] == "live"
    assert daten["telemetry_profile_target"] == "parked"
    assert daten["telemetry_profile_target_since"] == 1000.0
    assert daten["telemetry_profile_park_delay_seconds"] == 120.0

    jetzt[0] = 1120.0
    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == ["parked"]
    assert app._fleet_telemetry_profile_status["config_synced"] is False
    assert app._fleet_telemetry_profile_status["config_sync_state"] == "pending"
    assert app._fleet_telemetry_profile_status["config_sync_profile"] == "parked"


def test_fleet_telemetrie_profile_wiederholt_fehlversuch_nicht_sofort(monkeypatch):
    angefordert = []

    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_SEND_COOLDOWN_SECONDS", 120.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        lambda profil: angefordert.append(profil),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetry_profile_status",
        {
            "current": "parked",
            "target": "parked",
            "target_since": 1900.0,
            "last_sent": 1990.0,
            "last_sent_profile": "live",
            "last_error": "Kein gültiger Fleet-OAuth-Zugriffstoken verfügbar",
            "updated_at": 1990.0,
        },
    )
    daten = {
        "drive_state": {"shift_state": "D", "speed": 0},
        "vehicle_state": {"is_user_present": True},
    }

    app._fleet_telemetrie_profile_aktualisieren("veh-1", daten)

    assert angefordert == []
    assert daten["telemetry_profile"] == "parked"
    assert daten["telemetry_profile_target"] == "live"


def test_fleet_telemetrie_speichert_oauth_tokens_in_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"

    monkeypatch.setattr(app, "ENV_FILE", str(env_file))
    monkeypatch.delenv("TESLA_FLEET_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("TESLA_FLEET_REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("TESLA_FLEET_TOKEN_EXPIRES_AT", raising=False)

    app._fleet_telemetrie_oauth_tokens_in_env_speichern({
        "access_token": "access-123",
        "refresh_token": "refresh-456",
        "expires_at": 2000,
    })

    inhalt = env_file.read_text(encoding="utf-8")

    assert "TESLA_FLEET_ACCESS_TOKEN='access-123'" in inhalt
    assert "TESLA_FLEET_REFRESH_TOKEN='refresh-456'" in inhalt
    assert "TESLA_FLEET_TOKEN_EXPIRES_AT='2000'" in inhalt
    assert app.os.environ["TESLA_FLEET_ACCESS_TOKEN"] == "access-123"


def test_fleet_telemetrie_ignoriert_abgelaufenen_env_token(monkeypatch):
    monkeypatch.setenv("TESLA_FLEET_ACCESS_TOKEN", "alter-token")
    monkeypatch.setenv("TESLA_FLEET_TOKEN_EXPIRES_AT", "100")
    monkeypatch.setattr(app.time, "time", lambda: 200.0)

    assert app._fleet_telemetrie_oauth_token_aus_env() is None


def test_fleet_telemetrie_nutzt_gueltigen_env_token(monkeypatch):
    monkeypatch.setenv("TESLA_FLEET_ACCESS_TOKEN", "frischer-token")
    monkeypatch.setenv("TESLA_FLEET_TOKEN_EXPIRES_AT", "1000")
    monkeypatch.setattr(app.time, "time", lambda: 200.0)

    assert app._fleet_telemetrie_oauth_token_aus_env() == "frischer-token"


def test_fleet_telemetrie_erneuert_token_automatisch_vor_ablauf(monkeypatch):
    aktualisiert = []

    monkeypatch.setenv("TESLA_FLEET_ACCESS_TOKEN", "alter-token")
    monkeypatch.setenv("TESLA_FLEET_REFRESH_TOKEN", "refresh-123")
    monkeypatch.setenv("TESLA_FLEET_TOKEN_EXPIRES_AT", "500")
    monkeypatch.setattr(app.time, "time", lambda: 200.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_TOKEN_REFRESH_BEFORE_SECONDS", 400.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_oauth_tokens_laden",
        lambda: {"refresh_token": "refresh-123"},
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_oauth_token_aktualisieren",
        lambda tokens: aktualisiert.append(tokens) or "neuer-token",
    )

    assert app._fleet_telemetrie_oauth_token_automatisch_erneuern() is True
    assert aktualisiert == [{"refresh_token": "refresh-123"}]


def test_fleet_telemetrie_automatischer_token_refresh_ueberspringt_frischen_token(
    monkeypatch,
):
    monkeypatch.setenv("TESLA_FLEET_ACCESS_TOKEN", "frischer-token")
    monkeypatch.setenv("TESLA_FLEET_REFRESH_TOKEN", "refresh-123")
    monkeypatch.setenv("TESLA_FLEET_TOKEN_EXPIRES_AT", "1000")
    monkeypatch.setattr(app.time, "time", lambda: 200.0)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_TOKEN_REFRESH_BEFORE_SECONDS", 300.0)
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_oauth_token_aktualisieren",
        lambda tokens: pytest.fail("Frischer Token darf nicht erneuert werden"),
    )

    assert app._fleet_telemetrie_oauth_token_automatisch_erneuern() is False
