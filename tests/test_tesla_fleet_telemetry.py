import pathlib
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


@pytest.fixture(autouse=True)
def keine_echten_parking_logs(monkeypatch):
    """Verhindere echte Log-Einträge in Fleet-Telemetry-Tests."""

    monkeypatch.setattr(
        app,
        "_record_dashboard_parking_state",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_ladeinformationen_aktualisieren",
        lambda _cache_id, data, cached=None: data,
    )


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


def test_fleet_telemetrie_mqtt_ignoriert_unveraenderte_rohwerte(monkeypatch):
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
    )
    erster_zeitstempel = app.latest_data["veh-1"]["fleet_telemetry_updated_at"]

    assert not app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/LightsHighBeams",
        b"false",
        {"topic_base": "tesla"},
    )
    assert app.latest_data["veh-1"]["fleet_telemetry_updated_at"] == erster_zeitstempel
    assert len(gespeicherte_daten) == 1
    assert len(sammler.daten) == 1

    assert app._fleet_telemetrie_mqtt_message(
        "tesla/TESTVIN/v/LightsHighBeams",
        b"true",
        {"topic_base": "tesla"},
    )
    assert app.latest_data["veh-1"]["vehicle_state"]["lights_high_beams"] is True
    assert len(gespeicherte_daten) == 2
    assert len(sammler.daten) == 2


def test_fleet_telemetrie_connectivity_unterscheidet_connected_und_disconnected(monkeypatch):
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
    assert app.latest_data["veh-1"]["state"] == "disconnected"
    assert app.latest_data["veh-1"]["state_since_ms"] == disconnected_ms
    assert app.latest_data["veh-1"]["state_since_at"] == disconnected_at
    assert gespeicherte_daten[-1][1]["state"] == "disconnected"
    assert gespeicherte_daten[-1][1]["state_since_ms"] == disconnected_ms
    assert sammler.daten[-1]["state"] == "disconnected"
    assert sammler.daten[-1]["state_since_ms"] == disconnected_ms


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
    assert daten["drive_state"]["gps_state"] == "GpsStateActive"
    assert daten["charge_state"]["charge_energy_added"] == 7.5
    assert daten["charge_state"]["charger_power"] == 11
    assert daten["charge_state"]["charging_state"] == "Disconnected"
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


def test_fleet_telemetrie_reichert_tpms_und_spiegel_aus_rohdaten_an():
    daten = {
        "fleet_telemetry_raw": {
            "TpmsPressureFl": 2.95,
            "TpmsLastSeenPressureTimeFl": 1781412111,
            "RearDefrostEnabled": True,
        },
        "vehicle_state": {},
        "climate_state": {},
    }

    app._fleet_telemetrie_rohdaten_anreichern(daten)

    assert daten["vehicle_state"]["tpms_pressure_fl"] == 2.95
    assert daten["vehicle_state"]["tpms_last_seen_pressure_time_fl"] == 1781412111000
    assert daten["climate_state"]["side_mirror_heaters"] is True


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
