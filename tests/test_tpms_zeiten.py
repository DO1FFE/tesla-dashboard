import copy
import json
import shutil
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import app


def _zeit(iso):
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


@pytest.mark.parametrize("ortsuhrzeit", [
    "2026-10-10T21:42:00", "2026-01-10T21:42:00", "2026-03-15T21:42:00",
])
@pytest.mark.parametrize("einheit", ["sekunden", "millisekunden", "iso"])
def test_messzeit_korrigiert_pacific_mit_sommerzeit(ortsuhrzeit, einheit):
    datum = datetime.fromisoformat(ortsuhrzeit)
    falsch = datum.replace(tzinfo=ZoneInfo("America/Los_Angeles"))
    erwartet = int(datum.replace(tzinfo=app.LOCAL_TZ).timestamp() * 1000)
    wert = {
        "sekunden": falsch.timestamp(),
        "millisekunden": falsch.timestamp() * 1000,
        "iso": falsch.isoformat(),
    }[einheit]
    assert app._fleet_telemetrie_tpms_messzeit(wert, erwartet + 2000) == erwartet


@pytest.mark.parametrize("wert", [None, 0, -1, "ungültig", float("nan"), float("inf")])
def test_ungültige_messzeiten_bleiben_unbekannt(wert):
    assert app._fleet_telemetrie_tpms_messzeit(wert, _zeit("2026-10-10T23:00:00+02:00")) is None


@pytest.mark.parametrize("ortsuhrzeit", [
    "2026-03-29T02:30:00", "2026-10-25T02:30:00", "2027-01-01T12:00:00",
])
def test_mehrdeutige_nicht_existierende_und_zukünftige_messzeit(ortsuhrzeit):
    falsch = datetime.fromisoformat(ortsuhrzeit).replace(tzinfo=ZoneInfo("America/Los_Angeles"))
    assert app._fleet_telemetrie_tpms_messzeit(
        falsch.timestamp(), _zeit("2026-10-25T12:00:00+01:00"),
    ) is None


@pytest.mark.parametrize("rad", ["fl", "fr", "rl", "rr"])
def test_empfang_und_messung_bleiben_getrennt_auch_nach_cache_neuladen(rad):
    empfangen = _zeit("2026-10-10T23:40:23+02:00")
    messzeit = _zeit("2026-10-10T21:42:00-07:00")
    druckfeld = "TpmsPressure" + rad.capitalize()
    zeitfeld = "TpmsLastSeenPressureTime" + rad.capitalize()
    daten = {"vehicle_state": {"tpms_pressure_" + rad: 2.85}, "fleet_telemetry_raw": {}}

    def meldung(feld, wert, zeit):
        app._fleet_telemetrie_empfang_vermerken(daten, zeit, feld)
        app._fleet_telemetrie_setze_feld(daten, feld, wert, zeit)
        app._fleet_telemetrie_tpms_zeiten_anreichern(daten)
        return daten["vehicle_state"]["tpms_timing"][rad]

    zeiten = meldung(druckfeld, 2.85, empfangen)
    assert zeiten == {"received_at": empfangen, "measured_at": None}
    zeiten = meldung(zeitfeld, messzeit, empfangen + 100)
    erwartet = _zeit("2026-10-10T21:42:00+02:00")
    assert zeiten["measured_at"] == erwartet
    daten = json.loads(json.dumps(daten))
    zeiten = meldung(druckfeld, 2.85, empfangen + 60000)
    assert zeiten == {"received_at": empfangen + 60000, "measured_at": erwartet}
    for ungültig in [None, {"invalid": True}, float("nan"), float("inf"), True]:
        zeiten = meldung(druckfeld, ungültig, empfangen + 120000)
        assert zeiten["received_at"] == empfangen + 60000
        assert daten["vehicle_state"]["tpms_pressure_" + rad] == 2.85
    zeiten = meldung(druckfeld, 2.86, empfangen + 180000)
    assert zeiten == {"received_at": empfangen + 180000, "measured_at": None}
    zeiten = meldung(zeitfeld, messzeit, empfangen + 180100)
    assert zeiten["measured_at"] == erwartet
    zeiten = meldung(zeitfeld, None, empfangen + 180200)
    assert zeiten["measured_at"] is None


def test_alter_rest_zeitstempel_wird_nicht_als_aktuelle_messung_ausgegeben():
    empfangen = _zeit("2026-10-10T23:40:23+02:00")
    daten = {
        "vehicle_state": {"tpms_pressure_fl": 2.85, "tpms_last_seen_pressure_time_fl": 1791656418},
        "fleet_telemetry_raw": {"TpmsPressureFl": 2.85, "TpmsLastSeenPressureTimeFl": None},
        "fleet_telemetry_field_received_at": {"TpmsPressureFl": empfangen},
    }
    vorher = copy.deepcopy(daten)
    payload = app._subscriber_stream_payload(daten)
    assert payload["vehicle_state"]["tpms_timing"]["fl"] == {
        "received_at": empfangen, "measured_at": None,
    }
    assert "fleet_telemetry_field_received_at" not in payload
    assert daten == vorher


def _isoliere_empfang(monkeypatch, daten):
    monkeypatch.setattr(app, "latest_data", {"TEST": daten})
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda _vin: ["TEST"])
    monkeypatch.setattr(app, "_load_cached", lambda _id: {})
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_spaeter_speichern", lambda *args: None)
    monkeypatch.setattr(app, "_fleet_telemetrie_dashboard_daten_anreichern", lambda _id, d: d)
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktualisieren", lambda _id, d: d)
    monkeypatch.setattr(app, "_fleet_telemetrie_parkstatus_aufzeichnen", lambda *args: None)
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *args: None)
    monkeypatch.setattr(app, "_aprs_spaeter_senden", lambda *args: None)


def test_stream_wiederholungen_ungültige_und_veraltete_druckmeldungen(monkeypatch):
    daten = {"vehicle_state": {}, "fleet_telemetry_raw": {}}
    _isoliere_empfang(monkeypatch, daten)
    zeit = _zeit("2026-10-10T23:40:23+02:00")
    for wert, offset, erwartet in [(2.85, 0, 0), (2.85, 2000, 2000), (None, 4000, 2000), (2.7, 1000, 2000)]:
        app._fleet_telemetrie_cache_aktualisieren("TESTVIN", "TpmsPressureFl", wert, zeit + offset)
        vehicle = app._subscriber_stream_payload(daten)["vehicle_state"]
        assert vehicle["tpms_pressure_fl"] == 2.85
        assert vehicle["tpms_timing"]["fl"]["received_at"] == zeit + erwartet


def test_rest_druckempfang_aktualisiert_nur_gültige_werte(monkeypatch):
    zeit = _zeit("2026-10-10T23:40:23+02:00")
    daten = {"vehicle_state": {
        "tpms_pressure_fl": 2.85, "tpms_pressure_fr": 2.9,
        "tpms_pressure_fl_received_at": zeit - 60000,
        "tpms_pressure_fr_received_at": zeit - 60000,
    }}
    _isoliere_empfang(monkeypatch, daten)
    assert app._fleet_telemetrie_fallbackdaten_uebernehmen("TESTVIN", {
        "vehicle_state": {"tpms_pressure_fl": 2.86, "tpms_pressure_fr": None},
    }, zeit)
    vehicle = app._subscriber_stream_payload(daten)["vehicle_state"]
    assert vehicle["tpms_pressure_fl"] == 2.86
    assert vehicle["tpms_pressure_fr"] == 2.9
    assert vehicle["tpms_timing"]["fl"] == {"received_at": zeit, "measured_at": None}
    assert vehicle["tpms_timing"]["fr"]["received_at"] == zeit - 60000


def test_reifendruck_frontend_trennt_zeiten_und_lässt_sie_offline_altern():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js für den Reifendrucktest erforderlich")
    ergebnis = subprocess.run([node, "-e", r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const quelle = fs.readFileSync('static/js/main.js', 'utf8');
global.parseNumber = wert => wert == null ? null : Number.isFinite(Number(wert)) ? Number(wert) : null;
global.escapeHtml = text => String(text).replaceAll('&', '&amp;').replaceAll('"', '&quot;');
vm.runInThisContext(quelle.slice(quelle.indexOf('var letzterReifendruckStatus'), quelle.indexOf('function normalizeShiftState')));
vm.runInThisContext(quelle.slice(quelle.indexOf('function leseZeitstempelMillis'), quelle.indexOf('function reifendruckStatus')));
vm.runInThisContext(quelle.slice(quelle.indexOf('function reifendruckMitLetztenWerten'), quelle.indexOf('function updateTPMS')));
let jetzt = Date.parse('2026-10-11T00:40:23+02:00');
Date.now = () => jetzt;
let vehicle = {tpms_pressure_fl: 2.85, tpms_last_seen_pressure_time_fl: 1791656418,
  tpms_timing: {fl: {received_at: jetzt - 3600000, measured_at: null}}};
let rad = reifendruckReifen(vehicle)[0];
assert.equal(rad.zeit, null);
assert.equal(reifendruckZeittext(rad.zeit), 'Nicht verfügbar');
assert.equal(reifendruckZeittext(rad.empfangen), 'vor 1 h 0 min');
jetzt += 120000;
assert.equal(reifendruckZeittext(rad.empfangen), 'vor 1 h 2 min');
assert.equal(reifendruckZeittext(0), 'Nicht verfügbar');
assert.equal(reifendruckZeittext(jetzt + 120000), 'Nicht verfügbar');
assert.ok(reifendruckZeitZelle(rad.empfangen).includes('23:40:23'));
rad = reifendruckReifen({})[0];
assert.equal(rad.wert, 2.85);
assert.equal(reifendruckZeittext(rad.empfangen), 'vor 1 h 2 min');
vehicle.tpms_timing.fl.measured_at = jetzt - 7200000;
assert.equal(reifendruckReifen(vehicle)[0].zeit, jetzt - 7200000);
vehicle.tpms_timing = {fl: {received_at: rad.empfangen, measured_at: null}};
assert.equal(reifendruckReifen(vehicle)[0].zeit, null);
const timer = quelle.slice(quelle.lastIndexOf('setInterval(function()'));
assert.ok(timer.includes('updateTPMS(letzteDiagnoseDaten.vehicle_state || {})'));
assert.ok(timer.includes('updateReifendruckDetails(letzteDiagnoseDaten.vehicle_state || {})'));
"""], capture_output=True, text=True, timeout=10)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr


# © 2026 Erik Schauer, do1ffe@darc.de
