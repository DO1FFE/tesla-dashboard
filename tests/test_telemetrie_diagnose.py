"""Regressionen für neue Messfelder, Gültigkeit und Diagnoseverläufe."""

import shutil
import subprocess

import pytest

import app
import telemetrie_diagnose as diagnose


ZEIT = 1790416424000


def daten_mit(werte, zeit=ZEIT):
    daten = {
        "fleet_telemetry_raw": dict(werte),
        "fleet_telemetry_field_received_at": {feld: zeit for feld in werte},
    }
    diagnose.anreichern(daten)
    return daten


@pytest.mark.parametrize("nummer,name", diagnose.FELDNAMEN.items())
def test_numerische_und_benannte_felder(nummer, name):
    wert = True if name in diagnose.BOOL_FELDER else 42.5
    daten = daten_mit({nummer: wert})
    assert daten["telemetry_diagnostics"][name] == {
        "value": wert, "received_at": ZEIT, "valid": True,
    }
    assert nummer not in daten["fleet_telemetry_raw"]


def test_neuerer_nullwert_wird_nicht_durch_alte_nummer_ersetzt():
    daten = daten_mit({"263": 71.1, "NominalFullPackEnergyKwh": None})
    assert daten["telemetry_diagnostics"]["NominalFullPackEnergyKwh"]["value"] is None
    daten["fleet_telemetry_raw"]["263"] = 72.0
    daten["fleet_telemetry_field_received_at"]["263"] = ZEIT + 1000
    diagnose.anreichern(daten)
    assert daten["telemetry_diagnostics"]["NominalFullPackEnergyKwh"]["value"] == 72.0


@pytest.mark.parametrize("wert", [None, True, "ungültig", float("nan"), float("inf"), -1, 0])
def test_ungueltige_vollenergie_bleibt_unbekannt(wert):
    assert diagnose.messwert("NominalFullPackEnergyKwh", wert) is None


def test_null_false_und_null_prozent_bleiben_unterscheidbar():
    daten = daten_mit({"266": False, "262": 0, "261": None})
    werte = daten["telemetry_diagnostics"]
    assert werte["SoftwareUpdateAvailable"]["value"] is False
    assert werte["BrickSocMinPercent"]["value"] == 0
    assert werte["LifetimeEnergyChargedKwh"]["valid"] is False
    assert diagnose.frischer_wert(daten, "SoftwareUpdateAvailable", ZEIT + 121000, 120000) is None


@pytest.mark.parametrize("profil", ["live", "live_extended", "parked", "charging"])
def test_profile_mit_passenden_intervallen_ohne_semi(profil):
    config = app._fleet_telemetrie_profile_config_erstellen({"config": {"fields": {}}}, profil)
    felder = config["config"]["fields"]
    for feld, intervall in diagnose.profilfelder(profil).items():
        assert felder[feld]["interval_seconds"] == intervall
        assert "minimum_delta" not in felder[feld]
    assert felder["NominalFullPackEnergyKwh"]["interval_seconds"] == 300
    assert not {"SemiCruiseSpeedLimitMph", "Cabin12vPortKeepOn", "Cabin48vPortKeepOn"} & set(felder)
    if profil in {"live", "live_extended"}:
        assert "GpsAccuracyMeters" in felder["Location"]["include_fields"]
    else:
        assert "GradeEstimatePercent" not in felder
        assert "MaxSpeedToReachDestinationMph" not in felder


def test_gps_sprung_verwerfen_ohne_normale_fahrt_zu_blockieren():
    daten = daten_mit({"260": 2})
    daten["drive_state"] = {"latitude": 51.4, "longitude": 7.0, "gps_as_of": ZEIT - 1000, "speed": 30}
    assert diagnose.position_plausibel(daten, 51.4001, 7.0, ZEIT)
    assert not diagnose.position_plausibel(daten, 52.0, 7.0, ZEIT)
    assert daten["fleet_gps_rejected_at"] == ZEIT
    assert diagnose.position_plausibel(daten, 51.4002, 7.0, ZEIT + 1000)
    assert "fleet_gps_candidate" not in daten
    assert not diagnose.position_plausibel(daten, 51.4, 7, ZEIT - 2000)


def test_gps_neuen_fix_und_fahrt_nach_langer_luecke_zulassen():
    daten = daten_mit({"260": 2})
    daten["drive_state"] = {"latitude": 51.4, "longitude": 7.0, "gps_as_of": ZEIT - 1000}
    assert not diagnose.position_plausibel(daten, 52, 7, ZEIT)
    assert not diagnose.position_plausibel(daten, 52, 7, ZEIT + 1000)
    assert diagnose.position_plausibel(daten, 52, 7, ZEIT + 2000)
    assert diagnose.position_plausibel(daten, 52, 7, ZEIT + 180000)


def test_gps_ohne_genauigkeit_und_mit_schlechtem_empfang_faehrt_weiter():
    daten = daten_mit({"260": None})
    daten["drive_state"] = {"latitude": 51.4, "longitude": 7.0, "gps_as_of": ZEIT - 1000}
    assert diagnose.position_plausibel(daten, 51.401, 7, ZEIT)
    assert not diagnose.position_plausibel(daten, 200, 7, ZEIT)
    daten["fleet_telemetry_raw"]["GpsAccuracyMeters"] = 200
    diagnose.anreichern(daten)
    assert diagnose.position_plausibel(daten, 51.401, 7, ZEIT)


def test_update_flags_keine_erfundene_phase_und_keine_veraltete_ruecksetzung():
    daten = daten_mit({"266": False, "267": True})
    software = daten.setdefault("vehicle_state", {}).setdefault("software_update", {})
    software.update({"status": "none", "download_perc": 100, "install_perc": 1})
    diagnose.software_signale(daten, ZEIT)
    assert software["telemetry_status"] == "updating"
    assert software["status"] == "none"
    diagnose.software_signale(daten, ZEIT + 121000)
    assert "telemetry_status" not in software
    daten["fleet_telemetry_raw"]["SoftwareUpdateInProgress"] = False
    diagnose.anreichern(daten)
    daten["fleet_telemetry_field_received_at"]["SoftwareUpdateVersion"] = ZEIT + 10000
    diagnose.software_signale(daten, ZEIT + 10000)
    assert "telemetry_status" not in software


@pytest.mark.parametrize("hindernis", ["rest", "fortschritt", "version"])
def test_alte_false_flags_ueberschreiben_keine_neueren_signale(hindernis):
    daten = daten_mit({"266": False, "267": False})
    if hindernis == "rest":
        daten["fleet_vehicle_data_received_at"] = ZEIT + 2000
    else:
        feld = "SoftwareUpdateVersion" if hindernis == "version" else "SoftwareUpdateInstallationPercentComplete"
        daten["fleet_telemetry_field_received_at"][feld] = ZEIT + 2000
    diagnose.software_signale(daten, ZEIT + 2000)
    assert "telemetry_status" not in daten["vehicle_state"]["software_update"]


def test_update_phase_nur_mit_frischem_fortschritt():
    daten = daten_mit({"267": True, "SoftwareUpdateInstallationPercentComplete": 35})
    daten["vehicle_state"] = {"software_update": {"install_perc": 35}}
    diagnose.software_signale(daten, ZEIT)
    assert daten["vehicle_state"]["software_update"]["telemetry_status"] == "installing"
    daten["fleet_telemetry_field_received_at"]["SoftwareUpdateInstallationPercentComplete"] -= 300000
    diagnose.software_signale(daten, ZEIT)
    assert daten["vehicle_state"]["software_update"]["telemetry_status"] == "updating"


def test_bestaetigte_ruecksetzung_oeffnet_alten_download_nicht_erneut():
    daten = daten_mit({"266": False, "267": False})
    daten["vehicle_state"] = {"software_update": {"status": "downloading"}}
    diagnose.software_signale(daten, ZEIT + 3600000)
    assert daten["vehicle_state"]["software_update"]["telemetry_status"] == "none"


def test_installationsbeginn_bei_einem_prozent_mit_bestaetigtem_update():
    daten = daten_mit({
        "267": True, "SoftwareUpdateDownloadPercentComplete": 100,
        "SoftwareUpdateInstallationPercentComplete": 1,
    })
    daten["vehicle_state"] = {"software_update": {
        "download_perc": 100, "install_perc": 1,
    }}
    diagnose.software_signale(daten, ZEIT)
    assert daten["vehicle_state"]["software_update"]["telemetry_status"] == "installing"


def test_gps_verworfener_identischer_fix_wird_erneut_geprueft():
    daten = daten_mit({"260": 2})
    daten["drive_state"] = {
        "latitude": 51.4, "longitude": 7.0, "gps_as_of": ZEIT - 1000,
    }
    wert = {"latitude": 52.0, "longitude": 7.0}
    app._fleet_telemetrie_setze_feld(daten, "Location", wert, ZEIT)
    assert daten["drive_state"]["latitude"] == 51.4
    assert not app._fleet_telemetrie_wert_unveraendert(daten, "Location", wert)
    app._fleet_telemetrie_setze_feld(daten, "Location", wert, ZEIT + 1000)
    app._fleet_telemetrie_setze_feld(daten, "Location", wert, ZEIT + 2000)
    assert daten["drive_state"]["latitude"] == 52.0


def test_cache_schreiber_speichert_den_urspruenglichen_messpunkt(monkeypatch, tmp_path):
    pfad = str(tmp_path / "diagnose.sqlite")
    daten = daten_mit({"263": 71.1})
    daten["id_s"] = "A"
    monkeypatch.setattr(app, "_fleet_telemetry_cache_pending", {"A": daten, "default": daten})
    monkeypatch.setattr(app, "_save_cached", lambda *args: None)
    monkeypatch.setattr(app, "_telemetrie_diagnose_datenbankpfad", lambda: pfad)
    app._fleet_telemetrie_cache_pending_schreiben()
    assert diagnose.verlauf_laden(pfad, "A") == [{"received_at": ZEIT, "value": 71.1}]
    assert diagnose.verlauf_laden(pfad, "default") == []


def test_navigation_prognose_veraltet_oder_beendet():
    daten = daten_mit({"265": 60})
    daten["drive_state"] = {"active_route_active": True, "active_route_target_changed_at": ZEIT}
    diagnose.anreichern(daten)
    assert daten["drive_state"]["active_route_max_speed_mph"] == 60
    daten["drive_state"]["active_route_target_changed_at"] = ZEIT + 2000
    diagnose.anreichern(daten)
    assert "active_route_max_speed_mph" not in daten["drive_state"]
    app._fleet_telemetrie_navigation_beenden(daten["drive_state"], ZEIT + 3000, daten)
    diagnose.anreichern(daten)
    assert not daten["telemetry_diagnostics"]["MaxSpeedToReachDestinationMph"]["valid"]


def test_verlauf_ursprungszeit_raster_null_und_fahrzeugtrennung(tmp_path):
    pfad = str(tmp_path / "diagnose.sqlite")
    daten = daten_mit({"263": 71.1, "261": None})
    for _ in range(3):
        diagnose.verlauf_speichern(pfad, "A", daten)
    assert diagnose.verlauf_laden(pfad, "A") == [{"received_at": ZEIT, "value": 71.1}]
    diagnose.verlauf_speichern(pfad, "A", daten_mit({"263": 71.2}, ZEIT + 1000))
    diagnose.verlauf_speichern(pfad, "A", daten)
    diagnose.verlauf_speichern(pfad, "A", daten_mit({"263": None}, ZEIT + 2000))
    assert diagnose.verlauf_laden(pfad, "A") == [{"received_at": ZEIT + 1000, "value": 71.2}]
    diagnose.verlauf_speichern(pfad, "A", daten_mit({"263": 71.3}, ZEIT - 86400000))
    diagnose.verlauf_speichern(pfad, "B", daten_mit({"263": 75}))
    assert len(diagnose.verlauf_laden(pfad, "A", täglich=True)) == 2
    assert diagnose.verlauf_laden(pfad, "B")[0]["value"] == 75
    assert diagnose.verlauf_laden(pfad, "A", "LifetimeEnergyChargedKwh") == []


def test_steigung_wird_nur_beim_fahren_protokolliert(tmp_path):
    pfad = str(tmp_path / "diagnose.sqlite")
    daten = daten_mit({"264": -3.5})
    daten["drive_state"]["shift_state"] = "P"
    diagnose.verlauf_speichern(pfad, "A", daten)
    assert diagnose.verlauf_laden(pfad, "A", "GradeEstimatePercent") == []
    daten["drive_state"]["shift_state"] = "D"
    diagnose.verlauf_speichern(pfad, "A", daten)
    assert diagnose.verlauf_laden(pfad, "A", "GradeEstimatePercent")[0]["value"] == -3.5


def test_verlauf_api_und_statistik_leerzustand(monkeypatch, tmp_path):
    pfad = str(tmp_path / "diagnose.sqlite")
    monkeypatch.setattr(app, "_telemetrie_diagnose_datenbankpfad", lambda: pfad)
    monkeypatch.setattr(app, "_default_vehicle_id", "A")
    with app.app.test_client() as client:
        assert client.get("/api/akku-verlauf").get_json()["points"] == []
        diagnose.verlauf_speichern(pfad, "A", daten_mit({"263": 71.1}))
        antwort = client.get("/api/akku-verlauf").get_json()
        assert antwort["points"][0]["received_at"] == ZEIT
        assert client.get("/api/akku-verlauf?vehicle_id=B").get_json()["points"] == []
    with app.app.test_request_context("/statistik"):
        html = app.render_template("statistik.html", config={}, rows=[], summary=None)
        assert 'id="akku-diagramm"' in html
        assert '© 2025-' in html


def test_mqtt_neue_werte_auch_unveraendert_mit_zeit_bis_sse(monkeypatch):
    cache = {"A": {"id_s": "A"}}
    monkeypatch.setattr(app, "latest_data", cache)
    monkeypatch.setattr(app, "_fleet_telemetrie_cache_ids", lambda vin: ["A"])
    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeuge", lambda: [])
    monkeypatch.setattr(app, "_fleet_telemetrie_dashboard_daten_anreichern", lambda _id, daten: daten)
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktualisieren", lambda _id, daten: daten)
    for name in ("_fleet_telemetrie_cache_spaeter_speichern", "_fleet_telemetrie_parkstatus_aufzeichnen", "_aprs_spaeter_senden"):
        monkeypatch.setattr(app, name, lambda *args: None)
    nachrichten = []
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda _id, daten: nachrichten.append(app._subscriber_stream_payload(daten)))
    app._fleet_telemetrie_v_felder_aktualisieren("VIN", [("263", 71.1, ZEIT)])
    app._fleet_telemetrie_v_felder_aktualisieren("VIN", [("NominalFullPackEnergyKwh", 71.1, ZEIT + 300000)])
    app._fleet_telemetrie_v_felder_aktualisieren("VIN", [("263", None, ZEIT + 1000)])
    punkt = nachrichten[-1]["telemetry_diagnostics"]["NominalFullPackEnergyKwh"]
    assert punkt == {"value": 71.1, "received_at": ZEIT + 300000, "valid": True}
    assert "fleet_telemetry_field_received_at" not in nachrichten[-1]
    assert cache["A"]["fleet_telemetry_raw"]["NominalFullPackEnergyKwh"] == 71.1


def test_frontend_null_false_zeit_update_und_navigationsprognose():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js nicht verfügbar")
    skript = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const quelle = fs.readFileSync('static/js/main.js', 'utf8');
for (const name of ['diagnoseWertText', 'diagnoseEmpfangText', 'softwareUpdateMitTelemetrie', 'navigationFuerKarteAktiv', 'updateNavBar']) {
    const start = quelle.indexOf('function ' + name + '(');
    const ende = quelle.indexOf('\nfunction ', start + 1);
    vm.runInThisContext(quelle.slice(start, ende));
}
assert.equal(diagnoseWertText({value: 0, valid: true}, 0, '%'), '0 %');
assert.equal(diagnoseWertText({value: false, valid: true}, 0, ''), 'Nein');
assert.match(diagnoseWertText({value: null, valid: false, received_at: 123}, 0, ''), /ungültig/);
assert.match(diagnoseWertText(null, 0, ''), /Noch nicht/);
assert.match(diagnoseEmpfangText({received_at: 1000}, 100), /veraltet/);
const jetzt = Date.now();
const alt = {status: 'downloading', telemetry_status: 'none', telemetry_status_received_at: jetzt};
assert.equal(softwareUpdateMitTelemetrie(alt), null);
assert.equal(alt.status, 'downloading');
assert.equal(softwareUpdateMitTelemetrie({...alt, telemetry_status_received_at: jetzt-121000}), null);
assert.equal(softwareUpdateMitTelemetrie({...alt, telemetry_status: 'updating', telemetry_status_received_at: jetzt-121000}).status, 'downloading');
assert.equal(softwareUpdateMitTelemetrie({...alt, telemetry_status: 'updating', install_perc: 1}).install_perc, null);
let html = '';
global.$ = () => ({html: text => {html = text;}});
global.escapeHtml = wert => String(wert);
global.MILES_TO_KM = 1.609344;
const fahrt = {active_route_active: true, active_route_max_speed_mph: 60, active_route_max_speed_received_at: jetzt};
updateNavBar(fahrt);
assert.match(html, /97 km\/h/);
updateNavBar({...fahrt, active_route_active: false});
assert.doesNotMatch(html, /97 km\/h/);
updateNavBar({...fahrt, active_route_max_speed_received_at: jetzt-61000});
assert.doesNotMatch(html, /97 km\/h/);
"""
    ergebnis = subprocess.run([node, "-e", skript], capture_output=True, text=True, timeout=10)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr


# © 2026 Erik Schauer, do1ffe@darc.de
