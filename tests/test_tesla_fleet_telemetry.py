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
            "last_error": None,
            "config_synced": None,
            "config_key_paired": None,
            "config_sync_state": "unknown",
            "config_sync_profile": None,
            "config_sync_checked_at": 0.0,
            "config_sync_updated_at": 0.0,
            "config_sync_error": None,
            "config_sync_details": [],
            "updated_at": 0.0,
        },
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
    assert daten["drive_state"]["active_route_active"] is True
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


def test_fleet_telemetrie_mqtt_batch_default_ist_200_und_stream_latest_only():
    inhalt = pathlib.Path("app.py").read_text(encoding="utf-8")

    assert "FLEET_TELEMETRY_MQTT_BATCH_MAX = max(\n    200," in inhalt
    assert 'os.getenv("TESLA_FLEET_TELEMETRY_MQTT_BATCH_MAX", "200")' in inhalt
    assert "FLEET_TELEMETRY_STREAM_QUEUE_MAX = max(\n    1," in inhalt
    assert 'os.getenv("TESLA_FLEET_TELEMETRY_STREAM_QUEUE_MAX", "1")' in inhalt
    assert "FLEET_TELEMETRY_STREAM_KEEPALIVE_SECONDS = max(" in inhalt
    assert 'os.getenv("TESLA_FLEET_TELEMETRY_STREAM_KEEPALIVE_SECONDS", "0.5")' in inhalt
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

    app._fleet_telemetrie_navigation_cache_bereinigen(daten)

    drive = daten["drive_state"]
    assert "active_route_line" not in drive
    assert "active_route_latitude" not in drive
    assert "active_route_longitude" not in drive
    assert drive["active_route_active"] is False
    assert drive["active_route_ended_at"] == 1234


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
                "InsideTemp": {"interval_seconds": 1, "minimum_delta": 0.1},
                "Location": {"interval_seconds": 1, "minimum_delta": 0},
                "MediaNowPlayingTitle": {"interval_seconds": 30},
                "BatteryLevel": {"interval_seconds": 1, "minimum_delta": 0.1},
                "ChargeState": {"interval_seconds": 1},
                "PackCurrent": {"interval_seconds": 1, "minimum_delta": 0.1},
                "RouteLine": {"interval_seconds": 1},
                "VehicleSpeed": {"interval_seconds": 1, "minimum_delta": 0.1},
            },
        },
    }

    live = app._fleet_telemetrie_profile_config_erstellen(basis, "live")
    live_fields = live["config"]["fields"]

    assert live_fields["Location"]["interval_seconds"] == 1
    assert "minimum_delta" not in live_fields["Location"]
    assert live_fields["VehicleSpeed"]["interval_seconds"] == 1
    assert "minimum_delta" not in live_fields["VehicleSpeed"]
    assert live_fields["PackCurrent"]["interval_seconds"] == 1
    assert "minimum_delta" not in live_fields["PackCurrent"]
    assert live_fields["BatteryLevel"]["interval_seconds"] == 5
    assert "minimum_delta" not in live_fields["BatteryLevel"]
    assert live_fields["ChargeState"]["interval_seconds"] == 10
    assert live_fields["InsideTemp"]["interval_seconds"] == 10
    assert "minimum_delta" not in live_fields["InsideTemp"]
    assert live_fields["MediaNowPlayingTitle"]["interval_seconds"] == 60
    assert live_fields["RouteLine"]["interval_seconds"] == 10

    gedrosselt = app._fleet_telemetrie_profile_config_erstellen(basis, "parked")
    fields = gedrosselt["config"]["fields"]

    assert basis["config"]["fields"]["Location"]["interval_seconds"] == 1
    assert "InsideTemp" not in fields
    assert "Location" not in fields
    assert "MediaNowPlayingTitle" not in fields
    assert "RouteLine" not in fields
    assert fields["BatteryLevel"]["interval_seconds"] == 60
    assert fields["BatteryLevel"]["minimum_delta"] == 1.0
    assert fields["ChargeState"]["interval_seconds"] == 10
    assert fields["VehicleSpeed"]["interval_seconds"] == 10
    assert fields["VehicleSpeed"]["minimum_delta"] == 1.0


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


def test_fleet_telemetrie_profile_sendet_in_schnellphase_erneut(monkeypatch):
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
            "config_synced": False,
            "config_key_paired": None,
            "config_sync_state": "pending",
            "config_sync_profile": "live",
            "config_sync_checked_at": 1050.0,
            "config_sync_updated_at": 1000.0,
            "config_sync_error": None,
            "config_sync_details": [],
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
            "config_sync_details": [],
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
            "config_sync_details": [],
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
