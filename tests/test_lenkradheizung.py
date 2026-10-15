import copy
import json
import shutil
import subprocess
from unittest.mock import Mock

import pytest

import app


JETZT = 1_792_013_489_000


def _daten():
    return {
        "state": "online",
        "vehicle_config": {"car_type": "models", "driver_assist": "MonoCam"},
        "drive_state": {"shift_state": "P", "speed": 0},
        "driver_presence": {"value": True, "valid": True},
        "fleet_telemetry_received_at": JETZT,
        "fleet_telemetry_field_received_at": {
            "HvacSteeringWheelHeatLevel": JETZT - 900000,
            "VehicleSpeed": JETZT,
        },
        "fleet_telemetry_raw": {"HvacSteeringWheelHeatLevel": 0},
        "climate_state": {"steering_wheel_heater": False, "steering_wheel_heat_level": 0},
    }


@pytest.mark.parametrize("aktiv", [True, False])
def test_ap1_rest_schalter_gewinnt_gegen_auch_neuere_stufe_null(monkeypatch, aktiv):
    monkeypatch.setattr(app.time, "time", lambda: JETZT / 1000)
    daten = _daten()
    assert app._fleet_telemetrie_lenkradheizung_rest_merken(daten, {
        "steering_wheel_heater": aktiv, "timestamp": JETZT - 1000,
    }, JETZT)
    app._fleet_telemetrie_setze_feld(daten, "HvacSteeringWheelHeatLevel", 0, JETZT)
    daten = json.loads(json.dumps(daten))
    payload = app._subscriber_stream_payload(daten)
    assert payload["climate_state"]["steering_wheel_heater"] is aktiv
    assert payload["climate_state"]["steering_wheel_heat_level"] is None


@pytest.mark.parametrize("aktiv", [False, True])
@pytest.mark.parametrize("zustand", ["online", "offline", "asleep"])
def test_bestätigter_rest_status_bleibt_beim_parken_erhalten(
    monkeypatch, aktiv, zustand,
):
    daten = _daten()
    daten["state"] = zustand
    daten["driver_presence"] = {"value": False, "valid": True}
    app._fleet_telemetrie_lenkradheizung_rest_merken(daten, {
        "steering_wheel_heater": aktiv, "timestamp": JETZT,
    }, JETZT)
    monkeypatch.setattr(app.time, "time", lambda: JETZT / 1000 + 12 * 3600)
    daten = json.loads(json.dumps(daten))
    vorher = copy.deepcopy(daten["steering_wheel_heater_rest"])
    payload = app._subscriber_stream_payload(daten)
    klima = payload["climate_state"]
    assert klima["steering_wheel_heater"] is aktiv
    assert klima["steering_wheel_heater_cached"] is True
    assert klima["steering_wheel_heater_timestamp"] == JETZT
    assert klima["steering_wheel_heat_level"] is None
    assert daten["steering_wheel_heater_rest"] == vorher
    assert not app._fleet_telemetrie_lenkradheizung_abgleich_erlaubt(daten)


@pytest.mark.parametrize("aktiv", [False, True])
def test_frischer_rest_schalter_ersetzt_alten_cache(monkeypatch, aktiv):
    daten = _daten()
    app._fleet_telemetrie_lenkradheizung_rest_merken(daten, {
        "steering_wheel_heater": not aktiv, "timestamp": JETZT,
    }, JETZT)
    später = JETZT + 120000
    monkeypatch.setattr(app.time, "time", lambda: später / 1000)
    app._fleet_telemetrie_lenkradheizung_anreichern(daten)
    assert daten["climate_state"]["steering_wheel_heater_cached"] is True
    app._fleet_telemetrie_lenkradheizung_rest_merken(daten, {
        "steering_wheel_heater": aktiv, "timestamp": später,
    }, später)
    app._fleet_telemetrie_lenkradheizung_anreichern(daten)
    assert daten["climate_state"]["steering_wheel_heater"] is aktiv
    assert daten["climate_state"]["steering_wheel_heater_cached"] is False
    assert daten["climate_state"]["steering_wheel_heater_timestamp"] == später


@pytest.mark.parametrize("rest", [
    {}, {"value": None, "timestamp": JETZT},
    {"value": "false", "timestamp": JETZT},
    {"value": False}, {"value": False, "timestamp": 0},
    {"value": False, "timestamp": float("nan")},
    {"value": False, "timestamp": float("inf")},
    {"value": False, "timestamp": JETZT + 31000},
])
def test_ohne_bestätigten_schalter_bleibt_status_unbekannt(monkeypatch, rest):
    monkeypatch.setattr(app.time, "time", lambda: JETZT / 1000)
    daten = _daten()
    daten["steering_wheel_heater_rest"] = rest
    app._fleet_telemetrie_lenkradheizung_anreichern(daten)
    assert daten["climate_state"]["steering_wheel_heater"] is None
    assert daten["climate_state"]["steering_wheel_heat_level"] is None
    assert daten["climate_state"]["steering_wheel_heater_cached"] is False
    assert daten["climate_state"]["steering_wheel_heater_timestamp"] is None


def test_modernes_fahrzeug_bekommt_keinen_legacy_dauercache(monkeypatch):
    daten = _daten()
    daten["vehicle_config"] = {"car_type": "model3"}
    app._fleet_telemetrie_lenkradheizung_rest_merken(daten, {
        "steering_wheel_heater": True, "timestamp": JETZT,
    }, JETZT)
    monkeypatch.setattr(app.time, "time", lambda: JETZT / 1000 + 91)
    app._fleet_telemetrie_lenkradheizung_anreichern(daten)
    assert daten["climate_state"]["steering_wheel_heater"] is None
    assert daten["climate_state"]["steering_wheel_heater_cached"] is False


@pytest.mark.parametrize("wert", [None, "unknown", "HvacSteeringWheelHeatLevelUnknown", float("nan"), float("inf"), {"invalid": True}])
def test_ungültige_heizstufe_bleibt_unbekannt(wert):
    daten = {}
    app._fleet_telemetrie_setze_feld(daten, "HvacSteeringWheelHeatLevel", wert, JETZT)
    assert daten["climate_state"]["steering_wheel_heat_level"] is None
    assert daten["climate_state"]["steering_wheel_heater"] is None


def test_bestehender_rest_fallback_bewahrt_lenkradschalter(monkeypatch):
    monkeypatch.setattr(app.time, "time", lambda: JETZT / 1000)
    daten = _daten()
    daten["climate_state"]["steering_wheel_heater"] = True
    app._fleet_telemetrie_fallback_rohwerte_bereinigen(daten, {
        "climate_state": {"steering_wheel_heater": True, "timestamp": JETZT},
    }, JETZT)
    payload = app._subscriber_stream_payload(daten)
    assert payload["climate_state"]["steering_wheel_heater"] is True
    assert payload["climate_state"]["steering_wheel_heat_level"] is None


def test_modernes_fahrzeug_nutzt_neuere_telemetrie_nach_rest(monkeypatch):
    daten = _daten()
    daten["vehicle_config"] = {"car_type": "model3"}
    monkeypatch.setattr(app.time, "time", lambda: JETZT / 1000)
    app._fleet_telemetrie_lenkradheizung_rest_merken(daten, {
        "steering_wheel_heater": True, "timestamp": JETZT,
    }, JETZT)
    app._fleet_telemetrie_lenkradheizung_anreichern(daten)
    assert daten["climate_state"]["steering_wheel_heater"] is True
    assert daten["climate_state"]["steering_wheel_heat_level"] is None
    app._fleet_telemetrie_setze_feld(daten, "HvacSteeringWheelHeatLevel", 0, JETZT + 1000)
    assert daten["climate_state"]["steering_wheel_heater"] is False
    app._fleet_telemetrie_setze_feld(daten, "HvacSteeringWheelHeatLevel", None, JETZT + 2000)
    assert daten["climate_state"]["steering_wheel_heater"] is None


@pytest.mark.parametrize("antwort", [
    {}, {"steering_wheel_heater": None},
    {"steering_wheel_heater": True, "timestamp": JETZT - 91000},
    {"steering_wheel_heater": True, "timestamp": JETZT + 31000},
])
def test_unbrauchbare_rest_antwort_überschreibt_keinen_gültigen_stand(antwort):
    daten = _daten()
    app._fleet_telemetrie_lenkradheizung_rest_merken(daten, {
        "steering_wheel_heater": False, "timestamp": JETZT,
    }, JETZT)
    vorher = copy.deepcopy(daten)
    assert not app._fleet_telemetrie_lenkradheizung_rest_merken(daten, antwort, JETZT)
    assert daten == vorher


@pytest.mark.parametrize("gang,tempo,erwartet", [
    ("P", 0, True), ("D", 10, True), ("R", 2, True),
    ("D", 0, False), ("R", 0, False), ("N", 0, False), (None, 0, False),
])
def test_abgleich_nur_bei_nutzung_nicht_an_der_ampel(gang, tempo, erwartet):
    daten = _daten()
    daten["drive_state"] = {"shift_state": gang, "speed": tempo}
    assert app._fleet_telemetrie_lenkradheizung_abgleich_erlaubt(daten, JETZT) is erwartet


@pytest.mark.parametrize("grund", ["offline", "asleep", "alter_stream", "zukunft", "leer", "unbekannt", "modern", "frisch_abgerufen", "altes_tempo"])
def test_abgleich_ohne_aktuellen_nutzungsnachweis_gesperrt(grund):
    daten = _daten()
    if grund in {"offline", "asleep"}:
        daten["state"] = grund
    elif grund in {"alter_stream", "zukunft"}:
        daten["fleet_telemetry_received_at"] = JETZT + (-21000 if grund == "alter_stream" else 1000)
    elif grund in {"leer", "unbekannt"}:
        daten["driver_presence"] = {"value": False, "valid": grund == "leer"}
    elif grund == "modern":
        daten["vehicle_config"]["driver_assist"] = "TeslaAP3"
    elif grund == "frisch_abgerufen":
        daten["steering_wheel_heater_rest"] = {"received_at": JETZT - 29000}
    elif grund == "altes_tempo":
        daten["drive_state"] = {"shift_state": "D", "speed": 20}
        daten["fleet_telemetry_field_received_at"]["VehicleSpeed"] = JETZT - 16000
    assert not app._fleet_telemetrie_lenkradheizung_abgleich_erlaubt(daten, JETZT)


@pytest.fixture
def abgleich(monkeypatch):
    daten = _daten()
    zeit = {"wand": JETZT / 1000, "monoton": 100.0}
    monkeypatch.setattr(app.time, "time", lambda: zeit["wand"])
    monkeypatch.setattr(app.time, "monotonic", lambda: zeit["monoton"])
    monkeypatch.setattr(app, "_fleet_telemetry_lenkradheizung_letzte_abfrage", {})
    monkeypatch.setattr(app, "latest_data", {"TEST": daten})
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda _vin: ["TEST"])
    monkeypatch.setattr(app, "_fleet_telemetrie_position_snapshot", lambda _vin: daten)
    monkeypatch.setattr(app, "_fleet_telemetrie_oauth_token", lambda: "testtoken")
    monkeypatch.setattr(app, "_fleet_telemetrie_api_pause_aktiv", lambda: False)
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_spaeter_speichern", lambda *args: None)
    senden = Mock()
    monkeypatch.setattr(app, "_subscriber_daten_senden", senden)
    antwort = Mock()
    antwort.json.return_value = {"response": {"climate_state": {
        "steering_wheel_heater": True, "timestamp": JETZT,
        "driver_temp_setting": 30, "is_climate_on": False,
    }}}
    abfrage = Mock(return_value=antwort)
    monkeypatch.setattr(app, "_fleet_telemetrie_api_anfrage", abfrage)
    return daten, zeit, antwort, abfrage, senden


def test_abgleich_lädt_nur_klima_ohne_zu_wecken_oder_andere_daten_zu_ändern(abgleich):
    daten, zeit, antwort, abfrage, senden = abgleich
    daten["climate_state"].update({"driver_temp_setting": 20, "is_climate_on": True})
    assert app._fleet_telemetrie_lenkradheizung_abgleichen("TESTVIN")
    assert abfrage.call_args.args[0] is app.requests.get
    assert abfrage.call_args.args[1].endswith("/api/1/vehicles/TESTVIN/vehicle_data")
    assert abfrage.call_args.kwargs["params"] == {"endpoints": "climate_state"}
    assert daten["climate_state"]["steering_wheel_heater"] is True
    assert daten["climate_state"]["driver_temp_setting"] == 20
    assert daten["climate_state"]["is_climate_on"] is True
    assert daten["fleet_telemetry_received_at"] == JETZT
    senden.assert_called_once()
    assert not app._fleet_telemetrie_lenkradheizung_abgleichen("TESTVIN")
    zeit["wand"] += 30
    zeit["monoton"] += 30
    daten["fleet_telemetry_received_at"] += 30000
    antwort.json.return_value["response"]["climate_state"].update({
        "steering_wheel_heater": False, "timestamp": JETZT + 30000,
    })
    assert app._fleet_telemetrie_lenkradheizung_abgleichen("TESTVIN")
    assert daten["climate_state"]["steering_wheel_heater"] is False
    assert abfrage.call_count == 2


def test_fehlgeschlagener_abgleich_wird_ebenfalls_gedrosselt(abgleich):
    _, _, _, abfrage, _ = abgleich
    abfrage.side_effect = app.requests.exceptions.Timeout()
    with pytest.raises(app.requests.exceptions.Timeout):
        app._fleet_telemetrie_lenkradheizung_abgleichen("TESTVIN")
    assert not app._fleet_telemetrie_lenkradheizung_abgleichen("TESTVIN")
    assert abfrage.call_count == 1


def test_abgleich_respektiert_abrechnungssperre(abgleich, monkeypatch):
    _, _, _, abfrage, _ = abgleich
    monkeypatch.setattr(app, "_fleet_telemetrie_api_pause_aktiv", lambda: True)
    assert not app._fleet_telemetrie_lenkradheizung_abgleichen("TESTVIN")
    abfrage.assert_not_called()


def test_lenkradheizung_im_browser_ohne_erfundene_stufe_oder_automatikwärme():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js für den Heizungs-Anzeigetest erforderlich")
    ergebnis = subprocess.run([node, "-e", r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const quelle = fs.readFileSync('static/js/main.js', 'utf8');
global.parseNumber = x => x == null || x === '' || !Number.isFinite(Number(x)) ? null : Number(x);
global.istAktiv = x => x === true || x === 1;
const elemente = {};
global.$ = id => elemente[id] ||= {html(w){this.inhalt=w;return this},attr(k,w){this[k]=w;return this}};
vm.runInThisContext(quelle.slice(quelle.indexOf('function updateHeaterIndicator('), quelle.indexOf('function leseZeitstempelMillis(')));
for(const [aktiv,stufe,automatik,titel] of [
 [true,0,false,'Lenkradheizung an'], [true,null,null,'Lenkradheizung an'],
 [false,3,false,'Lenkradheizung aus'], [null,null,false,'Lenkradheizung unbekannt'],
 [null,null,true,'Lenkradheizung unbekannt'], [false,0,true,'Lenkradheizung aus (Automatik)'],
 [true,2,false,'Lenkradheizung Stufe 2'], [null,1,false,'Lenkradheizung Stufe 1'],
 [null,'unknown',false,'Lenkradheizung unbekannt']
]){
 updateHeaterIndicator(null,null,aktiv,stufe,automatik);
 assert.equal(elemente['#steering-heater'].title,titel);
}
for(const aktiv of [false,true]){
 const status = {steering_wheel_heater_cached:true,steering_wheel_heater_timestamp:1792013489000};
 const args = [null,null,aktiv,null,null,null,null,null,null,null,null,null,null,status];
 updateHeaterIndicator(...args);
 const anzeige = elemente['#steering-heater'];
 assert.ok(anzeige.title.startsWith('Lenkradheizung ' + (aktiv ? 'an' : 'aus') + ' (zuletzt bestätigt:'));
 assert.ok(anzeige.title.includes('14.10.2026'));
 assert.ok(anzeige.title.includes('gespeicherter Stand'));
 assert.equal(anzeige['aria-label'],anzeige.title);
 assert.ok(!anzeige.inhalt.includes('is-unknown'));
 status.steering_wheel_heater_cached = false;
 updateHeaterIndicator(...args);
 assert.equal(anzeige.title,'Lenkradheizung ' + (aktiv ? 'an' : 'aus'));
}
"""], capture_output=True, text=True, timeout=10)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr


# © 2026 Erik Schauer, do1ffe@darc.de
