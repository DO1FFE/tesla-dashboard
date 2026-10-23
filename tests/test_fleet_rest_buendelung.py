"""Gebündelte Ersatzabfragen ohne regelmäßige Lenkradheizungs-Abfrage."""

import json
from unittest.mock import Mock

import pytest

import app


@pytest.fixture
def abgleich(monkeypatch):
    zeit = {"monoton": 100.0, "wand": 1_792_013_489.0}
    bedarf = {"stream": False, "parken": False, "laden": False, "position": False}
    daten = {
        "state": "online",
        "drive_state": {"shift_state": "D", "speed": 20},
        "vehicle_config": {"car_type": "models", "driver_assist": "MonoCam"},
        "driver_presence": {"value": True, "valid": True},
        "fleet_telemetry_received_at": zeit["wand"] * 1000,
        "fleet_telemetry_field_received_at": {"VehicleSpeed": zeit["wand"] * 1000},
        "fleet_telemetry_raw": {"HvacSteeringWheelHeatLevel": 0},
    }
    monkeypatch.setattr(app.time, "monotonic", lambda: zeit["monoton"])
    monkeypatch.setattr(app.time, "time", lambda: zeit["wand"])
    monkeypatch.setattr(app, "_fleet_telemetrie_api_pause_aktiv", lambda: False)
    monkeypatch.setattr(app, "_fleet_telemetrie_position_snapshot", lambda _v: daten)
    for schlüssel, funktion, sperre in (
        ("stream", "stream_wiederherstellung", "stream_wiederherstellung"),
        ("parken", "parkabgleich", "parkabgleich"),
        ("laden", "ladeabgleich", "ladeabgleich"),
        ("position", "position", "position"),
    ):
        monkeypatch.setattr(
            app, f"_fleet_telemetrie_{funktion}_soll_aktualisiert_werden",
            lambda _d, k=schlüssel: bedarf[k],
        )
        monkeypatch.setattr(
            app, f"_fleet_telemetry_{sperre}_letzte_abfrage", {},
        )
    namen = {
        "profil": "_fleet_telemetrie_streamprofil_wiederherstellung_anfordern",
        "zustand": "_fleet_telemetrie_fahrzeugzustand_abrufen",
        "voll": "_fleet_telemetrie_parkdaten_abrufen",
        "position": "_fleet_telemetrie_position_abrufen",
        "parkübernahme": "_fleet_telemetrie_parkdaten_uebernehmen",
        "vollübernahme": "_fleet_telemetrie_fallbackdaten_uebernehmen",
        "positionsübernahme": "_fleet_telemetrie_position_uebernehmen",
        "fahrtverbindung": "_fleet_telemetrie_fahrtverbindung_nach_timeout",
    }
    aufrufe = {k: Mock(return_value=True) for k in namen}
    aufrufe["zustand"].return_value = "online"
    aufrufe["voll"].return_value = {
        "state": "online", "drive_state": {"latitude": 51.45, "longitude": 7.09},
        "climate_state": {"steering_wheel_heater": True},
        "charge_state": {"charging_state": "Charging"},
    }
    aufrufe["position"].return_value = {"latitude": 51.45, "longitude": 7.09}
    for name, funktion in namen.items():
        monkeypatch.setattr(app, funktion, aufrufe[name])
    return zeit, bedarf, daten, aufrufe


@pytest.mark.parametrize("gang,tempo", [("P", 0), ("D", 0), ("D", 20), ("R", 2)])
@pytest.mark.parametrize("heizung", [None, False, True])
def test_heizung_allein_löst_keinen_rest_abruf_aus(abgleich, gang, tempo, heizung):
    zeit, _, daten, aufrufe = abgleich
    daten["drive_state"] = {"shift_state": gang, "speed": tempo}
    daten["climate_state"] = {"steering_wheel_heater": heizung}
    for abstand in (0, 60, 300, 3600):
        zeit["monoton"] = 100 + abstand
        zeit["wand"] = 1_792_013_489 + abstand
        daten["fleet_telemetry_received_at"] = zeit["wand"] * 1000
        daten["fleet_telemetry_field_received_at"]["VehicleSpeed"] = (
            zeit["wand"] * 1000
        )
        assert not app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
    for name in ("voll", "position", "zustand", "fahrtverbindung"):
        aufrufe[name].assert_not_called()


def test_parken_und_laden_nutzen_eine_gemeinsame_antwort(abgleich):
    _, bedarf, _, aufrufe = abgleich
    bedarf.update(parken=True, laden=True, position=True)
    assert app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
    aufrufe["voll"].assert_called_once_with("TESTVIN")
    aufrufe["vollübernahme"].assert_called_once_with(
        "TESTVIN", aufrufe["voll"].return_value,
    )
    aufrufe["parkübernahme"].assert_not_called()
    aufrufe["position"].assert_not_called()
    assert not app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
    assert aufrufe["voll"].call_count == 1


def test_streamreparatur_verhindert_weitere_datenabfragen_im_selben_durchlauf(abgleich):
    _, bedarf, _, aufrufe = abgleich
    bedarf.update(stream=True, parken=True, laden=True, position=True)
    assert app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
    aufrufe["zustand"].assert_called_once_with("TESTVIN")
    aufrufe["voll"].assert_called_once_with("TESTVIN")
    aufrufe["vollübernahme"].assert_called_once()
    aufrufe["position"].assert_not_called()
    aufrufe["parkübernahme"].assert_not_called()


def test_gebündelte_antwort_aktualisiert_cache_und_ui_gemeinsam(monkeypatch):
    jetzt = 1_792_013_489_000
    daten = {
        "state": "online",
        "drive_state": {"shift_state": "D", "latitude": 51.0, "longitude": 7.0},
        "vehicle_config": {"car_type": "models", "driver_assist": "MonoCam"},
        "climate_state": {"steering_wheel_heater": True},
        "fleet_telemetry_raw": {"HvacSteeringWheelHeatLevel": 0},
    }
    antwort = {
        "state": "online",
        "drive_state": {"shift_state": "P", "latitude": 51.45, "longitude": 7.09},
        "climate_state": {"steering_wheel_heater": False, "timestamp": jetzt},
        "charge_state": {"charging_state": "Charging", "battery_level": 42},
    }
    http_antworten = []
    for inhalt in ({"state": "online"}, antwort):
        response = app.requests.Response()
        response.status_code = 200
        response._content = json.dumps({"response": inhalt}).encode("utf-8")
        http_antworten.append(response)
    anfrage = Mock(side_effect=http_antworten)
    gesendet = Mock()
    gespeichert = Mock()
    monkeypatch.setattr(app.time, "time", lambda: jetzt / 1000)
    monkeypatch.setattr(app, "latest_data", {"TESTVIN": daten})
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda _v: ["TESTVIN"])
    monkeypatch.setattr(app, "_fleet_telemetrie_position_snapshot", lambda _v: daten)
    monkeypatch.setattr(app, "_fleet_telemetrie_api_pause_aktiv", lambda: False)
    monkeypatch.setattr(app, "_fleet_telemetrie_oauth_token", lambda: "testtoken")
    monkeypatch.setattr(app, "_fleet_telemetrie_api_anfrage", anfrage)
    monkeypatch.setattr(app, "_fleet_telemetry_stream_wiederherstellung_letzte_abfrage", {})
    monkeypatch.setattr(
        app, "_fleet_telemetrie_stream_wiederherstellung_soll_aktualisiert_werden",
        lambda _d: True,
    )
    for name in ("dashboard_daten_anreichern", "profile_aktualisieren"):
        monkeypatch.setattr(app, f"_fleet_telemetrie_{name}", lambda _id, d: d)
    for name in ("streamprofil_wiederherstellung_anfordern", "parkstatus_aufzeichnen"):
        monkeypatch.setattr(app, f"_fleet_telemetrie_{name}", Mock())
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_spaeter_speichern", gespeichert)
    monkeypatch.setattr(app, "_subscriber_daten_senden", gesendet)
    monkeypatch.setattr(app, "_aprs_spaeter_senden", Mock())

    assert app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
    assert anfrage.call_count == 2
    statusabruf, datenabruf = anfrage.call_args_list
    assert statusabruf.args[1].endswith("/api/1/vehicles/TESTVIN")
    assert datenabruf.args[1].endswith("/api/1/vehicles/TESTVIN/vehicle_data")
    assert set(datenabruf.kwargs["params"]["endpoints"].split(";")) == {
        "location_data", "charge_state", "climate_state", "vehicle_state",
        "gui_settings", "vehicle_config",
    }
    assert daten["drive_state"]["latitude"] == 51.45
    assert daten["drive_state"]["longitude"] == 7.09
    assert daten["drive_state"]["shift_state"] == "P"
    assert daten["charge_state"]["charging_state"] == "Charging"
    assert daten["charge_state"]["battery_level"] == 42
    assert daten["steering_wheel_heater_rest"]["value"] is False
    assert daten["fleet_vehicle_data_received_at"] == jetzt
    gespeichert.assert_called_once_with("TESTVIN", daten)
    gesendet.assert_called_once_with("TESTVIN", daten)


@pytest.mark.parametrize("zustand", ["asleep", "offline", None])
def test_stummer_stream_weckt_nicht_und_begrenzt_statusprüfungen(abgleich, zustand):
    zeit, bedarf, _, aufrufe = abgleich
    bedarf["stream"] = True
    aufrufe["zustand"].return_value = zustand
    assert not app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
    zeit["monoton"] += 29
    assert not app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
    aufrufe["zustand"].assert_called_once()
    aufrufe["voll"].assert_not_called()
    aufrufe["fahrtverbindung"].assert_not_called()


def test_fehlerpause_gilt_für_alle_pfade_aber_nicht_die_profilreparatur(abgleich):
    zeit, bedarf, _, aufrufe = abgleich
    aufrufe["voll"].side_effect = app.requests.exceptions.Timeout()
    aufrufe["position"].side_effect = app.requests.exceptions.Timeout()
    pfade = ("position", "stream", "parken", "laden", "position")
    for nummer, (pfad, pause) in enumerate(zip(pfade, (30, 60, 120, 300, 300)), 1):
        bedarf.update({name: name == pfad for name in bedarf})
        assert not app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
        status = app._fleet_telemetrie_rest_abgleich_status["TESTVIN"]
        assert status["frühestens"] == zeit["monoton"] + pause
        anfragen = aufrufe["voll"].call_count + aufrufe["position"].call_count
        assert anfragen == nummer
        zeit["monoton"] += pause - 0.001
        bedarf.update({name: True for name in bedarf})
        assert not app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
        assert aufrufe["voll"].call_count + aufrufe["position"].call_count == nummer
        zeit["monoton"] = status["frühestens"]
    assert aufrufe["profil"].call_count == 10


@pytest.mark.parametrize("code,header,pause", [
    (429, "600", 600), (503, "900", 900), (408, None, 30),
    (401, None, 300), (403, None, 300), (500, "ungültig", 30),
    (429, "nan", 30), (429, "inf", 30),
])
def test_retry_after_und_berechtigungsfehler_werden_beachtet(
    abgleich, code, header, pause,
):
    zeit, bedarf, _, aufrufe = abgleich
    bedarf["position"] = True
    response = app.requests.Response()
    response.status_code = code
    if header is not None:
        response.headers["Retry-After"] = header
    aufrufe["position"].side_effect = app.requests.exceptions.HTTPError(
        response=response,
    )
    assert not app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
    status = app._fleet_telemetrie_rest_abgleich_status["TESTVIN"]
    assert status["frühestens"] == zeit["monoton"] + pause
    assert status["läuft"] is False


def test_erfolg_setzt_fehlerpause_zurück_und_andere_fahrzeuge_bleiben_frei(abgleich):
    zeit, bedarf, _, aufrufe = abgleich
    bedarf["position"] = True
    aufrufe["position"].side_effect = app.requests.exceptions.Timeout()
    assert not app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
    aufrufe["position"].side_effect = None
    assert app._fleet_telemetrie_fahrzeug_abgleichen("ANDEREVIN")
    zeit["monoton"] += 30
    assert app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
    assert app._fleet_telemetrie_rest_abgleich_status["TESTVIN"]["fehler"] == 0
    zeit["monoton"] += 30
    aufrufe["position"].side_effect = app.requests.exceptions.Timeout()
    assert not app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
    assert app._fleet_telemetrie_rest_abgleich_status["TESTVIN"]["frühestens"] == (
        zeit["monoton"] + 30
    )


def test_keine_parallelen_abrufe_auch_nach_ablauf_der_zeitgrenze(abgleich):
    zeit, _, _, _ = abgleich
    assert app._fleet_telemetrie_rest_abgleich_reservieren("TESTVIN")
    zeit["monoton"] += 600
    assert not app._fleet_telemetrie_rest_abgleich_erlaubt("TESTVIN")
    assert not app._fleet_telemetrie_rest_abgleich_reservieren("TESTVIN")
    assert app._fleet_telemetrie_rest_abgleich_reservieren("ANDEREVIN")


def test_abrechnungssperre_verhindert_auch_gebündelte_abrufe(abgleich, monkeypatch):
    _, bedarf, _, aufrufe = abgleich
    bedarf.update({name: True for name in bedarf})
    monkeypatch.setattr(app, "_fleet_telemetrie_api_pause_aktiv", lambda: True)
    assert not app._fleet_telemetrie_fahrzeug_abgleichen("TESTVIN")
    for aufruf in aufrufe.values():
        aufruf.assert_not_called()


@pytest.mark.parametrize("payload", [None, [], {}, {"response": {}}, {
    "response": {"state": "online", "climate_state": {}},
}])
def test_leere_antworten_gelten_nicht_als_erfolgreicher_abgleich(monkeypatch, payload):
    response = app.requests.Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode("utf-8")
    monkeypatch.setattr(app, "_fleet_telemetrie_oauth_token", lambda: "testtoken")
    monkeypatch.setattr(app, "_fleet_telemetrie_api_anfrage", lambda *a, **k: response)
    with pytest.raises(RuntimeError, match="keine Fahrzeugdaten"):
        app._fleet_telemetrie_parkdaten_abrufen("TESTVIN")


@pytest.mark.parametrize("profil", ["live", "live_extended"])
def test_fahrdaten_behalten_sekundentakt_und_navigation(profil):
    kernfelder = {
        "VehicleSpeed", "Gear", "GpsHeading", "GpsState", "Location",
        "BrakePedal", "BrakePedalPos", "LightsTurnSignal", "LightsHighBeams",
        "LightsHazardsActive", "PackCurrent", "PackVoltage", "PedalPosition",
    }
    felder = app._fleet_telemetrie_profile_config_erstellen({"config": {"fields": {
        feld: {"interval_seconds": 30, "minimum_delta": 5}
        for feld in kernfelder | {"DestinationLocation", "DestinationName", "RouteLine"}
    }}}, profil)["config"]["fields"]
    for feld in kernfelder | {"GradeEstimatePercent"}:
        assert felder[feld]["interval_seconds"] == 1
        assert "minimum_delta" not in felder[feld]
    assert set(felder["Location"]["include_fields"]) == (
        app.FLEET_TELEMETRIE_PROFILE_LIVE_BEWEGUNGS_INKLUSIVFELDER
    )
    for feld in ("Odometer", "DestinationLocation", "DestinationName"):
        assert "RouteLine" in felder[feld]["include_fields"]
    assert felder["RouteLine"]["interval_seconds"] == 10


# © 2026 Erik Schauer, do1ffe@darc.de
