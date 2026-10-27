import copy
import json
import shutil
import subprocess

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


@pytest.mark.parametrize("profil", ["live", "live_extended"])
@pytest.mark.parametrize("wiederherstellung", [False, True])
def test_lenkradheizung_bei_änderung_sekündlich_ohne_zusatzmeldungen(
    profil, wiederherstellung,
):
    felder = app._fleet_telemetrie_profile_config_erstellen(
        {"config": {"fields": {}}}, profil,
        wiederherstellung=wiederherstellung,
    )["config"]["fields"]
    for feld in ("HvacSteeringWheelHeatLevel", "HvacSteeringWheelHeatAuto"):
        assert felder[feld] == {"interval_seconds": 1}
        assert feld not in app.FLEET_TELEMETRIE_PROFILE_LIVE_BESTAETIGUNGSFELDER
        assert all(
            feld not in config.get("include_fields", [])
            for config in felder.values()
        )


def test_unterstützte_heizungsänderungen_erscheinen_sofort_ohne_rest(monkeypatch):
    daten = _daten()
    daten["vehicle_config"] = {"car_type": "model3"}
    monkeypatch.setattr(app.time, "time", lambda: JETZT / 1000)
    for stufe, erwartet in ((1, True), (0, False), (3, True), (None, None)):
        app._fleet_telemetrie_setze_feld(
            daten, "HvacSteeringWheelHeatLevel", stufe, JETZT,
        )
        payload = app._subscriber_stream_payload(daten)
        assert payload["climate_state"]["steering_wheel_heater"] is erwartet


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
 const jetzt = 1792013489000;
 Date.now = () => jetzt;
 const status = {steering_wheel_heater_cached:true,steering_wheel_heater_timestamp:1792013489000};
 const args = [null,null,aktiv,null,null,null,null,null,null,null,null,null,null,status];
 updateHeaterIndicator(...args);
 const anzeige = elemente['#steering-heater'];
 assert.ok(anzeige.title.startsWith('Lenkradheizung aktuell unbestätigt; Zuletzt ' + (aktiv ? 'an' : 'aus') + ':'));
 assert.ok(anzeige.title.includes('14.10.2026'));
 assert.ok(anzeige.title.includes('gespeicherter Stand'));
 assert.equal(anzeige['aria-label'],anzeige.title);
 assert.ok(!anzeige.inhalt.includes('is-unknown'));
 assert.ok(anzeige.inhalt.includes('is-cached'));
 assert.ok(anzeige.inhalt.includes('Aktuell unbestätigt'));
 assert.ok(anzeige.inhalt.includes('Zuletzt ' + (aktiv ? 'an' : 'aus')));
 assert.ok(anzeige.inhalt.includes('14.10.2026'));
 status.steering_wheel_heater_cached = false;
 updateHeaterIndicator(...args);
 assert.equal(anzeige.title,'Lenkradheizung ' + (aktiv ? 'an' : 'aus'));
 assert.ok(!anzeige.inhalt.includes('heater-history'));
 // Ohne neue Nachricht muss der zuletzt frische REST-Wert ebenfalls altern.
 Date.now = () => jetzt + 90000;
 updateHeaterIndicator(...args);
 assert.ok(!anzeige.inhalt.includes('heater-history'));
 Date.now = () => jetzt + 90001;
 updateHeaterIndicator(...args);
 assert.ok(anzeige.inhalt.includes('Aktuell unbestätigt'));
 assert.ok(anzeige.inhalt.includes('Zuletzt ' + (aktiv ? 'an' : 'aus')));
 // Neue Bestätigung entfernt den Hinweis und übernimmt den neuen Schalterwert.
 status.steering_wheel_heater_timestamp = Date.now();
 args[2] = !aktiv;
 updateHeaterIndicator(...args);
 assert.equal(anzeige.title,'Lenkradheizung ' + (!aktiv ? 'an' : 'aus'));
 assert.ok(!anzeige.inhalt.includes('is-cached'));
 assert.ok(!anzeige.inhalt.includes('heater-history'));
 // Fehlende oder ungültige Zeitstempel erzeugen keine erfundene Messzeit.
 for(const zeit of [null,0,'kaputt',Infinity]){
  status.steering_wheel_heater_timestamp = zeit;
  status.steering_wheel_heater_cached = true;
  updateHeaterIndicator(...args);
  assert.ok(anzeige.inhalt.includes('Aktuell unbestätigt'));
  assert.ok(!anzeige.inhalt.includes('Invalid Date'));
  assert.ok(!anzeige.inhalt.includes('1970'));
 }
 args[2] = null;
 updateHeaterIndicator(...args);
 assert.equal(anzeige.title,'Lenkradheizung unbekannt');
 assert.ok(!anzeige.inhalt.includes('heater-history'));
}
"""], capture_output=True, text=True, timeout=10)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr


# © 2026 Erik Schauer, do1ffe@darc.de
