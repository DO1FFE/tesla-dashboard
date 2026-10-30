"""Keine Fahrzeugabfragen während geschützter Neustarts, auch nicht per SDK."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest
import requests

import app
import fahrzeugzugriffsschutz as schutz


@pytest.fixture
def gesperrt(monkeypatch):
    monkeypatch.setattr(schutz, "_ende", 2000)
    monkeypatch.setattr(schutz, "STARTZEIT", 1000)
    monkeypatch.setattr(schutz, "_profil_freigegeben", False)
    monkeypatch.setattr(schutz, "_proxy", ("https", "127.0.0.1", 4443))
    monkeypatch.setattr(schutz.time, "time", lambda: 1050)


@pytest.mark.parametrize("methode,adresse", [
    ("GET", "https://127.0.0.1:4443/api/1/vehicles/VIN/vehicle_data"),
    ("GET", "https://127.0.0.1:4443/api/1/vehicles/VIN/fleet_telemetry_config"),
    ("POST", "https://127.0.0.1:4443/api/1/vehicles/VIN/wake_up"),
    ("POST", "https://127.0.0.1:4443/api/1/vehicles/VIN/command/door_unlock"),
    ("GET", "https://fleet-api.prd.eu.vn.cloud.tesla.com/api/1/vehicles"),
    ("GET", "https://owner-api.teslamotors.com/api/1/vehicles/VIN"),
    ("GET", "https://proxy.example/api/1/vehicles/VIN/vehicle_data"),
    ("POST", "https://127.0.0.1:4443/api/1/vehicles/fleet_telemetry_config?x=1"),
])
@pytest.mark.parametrize("unbefristet", [False, True])
def test_daten_befehle_und_wakeups_gesperrt(gesperrt, methode, adresse, unbefristet):
    if unbefristet:
        schutz.konfigurieren("unbefristet", "https://127.0.0.1:4443")
    with pytest.raises(schutz.FahrzeugabfrageGesperrt):
        schutz.anfrage_prüfen(methode, adresse)


@pytest.mark.parametrize("unbefristet", [False, True])
def test_profil_nur_nach_neuem_stream_und_token_weiter_möglich(gesperrt, unbefristet):
    if unbefristet:
        schutz.konfigurieren("unbefristet", "https://127.0.0.1:4443")
    url = "https://127.0.0.1:4443/api/1/vehicles/fleet_telemetry_config"
    assert not schutz.profil_freigeben({"fleet_telemetry_received_at": 999000})
    assert not schutz.profil_freigeben({"fleet_telemetry_received_at": 9999999999999})
    assert not schutz.profil_freigeben({"fleet_telemetry_received_at": "nan"})
    with pytest.raises(schutz.FahrzeugabfrageGesperrt):
        schutz.anfrage_prüfen("POST", url)
    assert schutz.profil_freigeben({"fleet_telemetry_received_at": 1049000})
    schutz.anfrage_prüfen("POST", url)
    schutz.anfrage_prüfen("POST", "https://auth.tesla.com/oauth2/v3/token")


def test_sperre_endet_ohne_neustart(gesperrt, monkeypatch):
    monkeypatch.setattr(schutz.time, "time", lambda: 2000)
    assert not schutz.aktiv()
    schutz.anfrage_prüfen("GET", "https://127.0.0.1:4443/api/1/vehicles")


@pytest.mark.parametrize("jetzt", [2000, 10_000_000_000])
def test_unbefristete_sperre_läuft_nicht_ab(gesperrt, monkeypatch, jetzt):
    schutz.konfigurieren("unbefristet", "https://127.0.0.1:4443")
    monkeypatch.setattr(schutz.time, "time", lambda: jetzt)
    assert schutz.aktiv()
    with pytest.raises(schutz.FahrzeugabfrageGesperrt):
        schutz.anfrage_prüfen("GET", "https://127.0.0.1:4443/api/1/vehicles")


def test_transport_stoppt_direkte_requests_vor_dem_socket(gesperrt, monkeypatch):
    versand = Mock()
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", versand)
    monkeypatch.setattr(schutz, "_installiert", False)
    schutz.installieren()
    with pytest.raises(schutz.FahrzeugabfrageGesperrt):
        requests.get("https://127.0.0.1:4443/api/1/vehicles/VIN/vehicle_data")
    versand.assert_not_called()


def test_worker_und_sync_verzichten_auf_abfragen(gesperrt, monkeypatch):
    snapshot = Mock()
    token = Mock()
    monkeypatch.setattr(app, "_fleet_telemetrie_position_snapshot", snapshot)
    monkeypatch.setattr(app, "_fleet_telemetrie_oauth_token", token)
    assert not app._fleet_telemetrie_fahrzeug_abgleichen("VIN")
    assert app._fleet_telemetrie_profile_sync_pruefen()["state"] == "pending"
    snapshot.assert_not_called()
    token.assert_not_called()


def test_startcache_verändert_keinen_profilstatus(gesperrt, monkeypatch):
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktiviert", lambda: True)
    monkeypatch.setattr(app, "_fleet_telemetrie_api_pause_aktiv", lambda: False)
    vorher = copy.deepcopy(app._fleet_telemetry_profile_status)
    app._fleet_telemetrie_profile_aktualisieren("test", {"fleet_telemetry_received_at": 999000})
    assert app._fleet_telemetry_profile_status == vorher


@pytest.mark.parametrize("profil", ["live", "live_extended"])
def test_sekundentakt_und_änderungsgesteuerte_lenkradheizung_bleiben(gesperrt, profil):
    config = app._fleet_telemetrie_profile_config_erstellen({"config": {"fields": {
        feld: {"interval_seconds": 10} for feld in (
            "Location", "VehicleSpeed", "PackCurrent", "HvacSteeringWheelHeatLevel",
        )
    }}}, profil)
    for feld in ("Location", "VehicleSpeed", "PackCurrent", "HvacSteeringWheelHeatLevel"):
        assert config["config"]["fields"][feld]["interval_seconds"] == 1


def test_live_plus_auch_unter_sperre_möglich(gesperrt, monkeypatch):
    monkeypatch.setattr(schutz.time, "time", lambda: 2100)
    monkeypatch.setattr(schutz, "_ende", 3000)
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_aktiviert", lambda: True)
    monkeypatch.setattr(app, "_fleet_telemetrie_api_pause_aktiv", lambda: False)
    monkeypatch.setattr(app, "FLEET_TELEMETRIE_PROFILE_LIVE_EXTENDED_DELAY_SECONDS", 60)
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_status_speichern", lambda: None)
    senden = Mock()
    monkeypatch.setattr(app, "_fleet_telemetrie_profile_spaeter_anwenden", senden)
    monkeypatch.setattr(app, "_fleet_telemetry_profile_status", {
        "current": "live", "target": "live", "target_since": 2000,
        "last_sent": 2000, "last_sent_profile": "live", "config_synced": True,
        "config_sync_state": "synced", "config_sync_profile": "live",
        "config_sync_details": [{"source": "telemetry_stream", "synced": True}],
        "live_stable_since": 2000,
    })
    daten = {
        "fleet_telemetry_received_at": 2099000,
        "fleet_telemetry_field_received_at": {f: 2099000 for f in ("VehicleSpeed", "PackCurrent", "Location")},
        "fleet_telemetry_field_interval_ms": {f: 1000 for f in ("VehicleSpeed", "PackCurrent", "Location")},
        "drive_state": {"shift_state": "D", "speed": 12},
        "charge_state": {"charging_state": "Disconnected"},
    }
    app._fleet_telemetrie_profile_aktualisieren("test", daten)
    senden.assert_called_once_with("live_extended")


@pytest.mark.parametrize("ende", ["ungültig", "2026-10-25T13:50:00"])
def test_ungültige_schutzfrist_bricht_start_ab(ende):
    with pytest.raises(ValueError):
        schutz.konfigurieren(ende, "https://127.0.0.1:4443")


@pytest.mark.parametrize("ende", ["2099-10-25T13:50:00Z", "unbefristet"])
def test_starter_installiert_schutz_vor_app_start(tmp_path, monkeypatch, ende):
    from tools import telemetrie_geschuetzter_start as starter
    (tmp_path / "data").mkdir()
    monkeypatch.setenv("TESLA_DASHBOARD_ABFRAGESPERRE_BIS", ende)
    monkeypatch.setenv("TESLA_FLEET_VEHICLE_COMMAND_URL", "https://127.0.0.1:4443")
    monkeypatch.setattr(schutz, "_ende", None)
    monkeypatch.setattr(schutz, "_proxy", None)
    monkeypatch.setattr(schutz, "_installiert", False)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", Mock())
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.chdir(tmp_path)
    gestartet = []

    def starten(*args, **kwargs):
        gestartet.append(args)
        assert schutz.aktiv() and schutz._installiert
        with pytest.raises(schutz.FahrzeugabfrageGesperrt):
            requests.get("https://127.0.0.1:4443/api/1/vehicles/VIN/vehicle_data")

    monkeypatch.setattr(starter.runpy, "run_path", starten)
    starter.main(tmp_path)
    assert gestartet
    assert json.loads((tmp_path / "data/neustartschutz.json").read_text())["pid"] == os.getpid()


@pytest.mark.parametrize("ende", ["2099-10-25T13:50:00Z", "unbefristet"])
def test_vollständiger_start_in_frischem_prozess_ohne_http(tmp_path, ende):
    projekt = Path(__file__).resolve().parents[1]
    umgebung = dict(os.environ, TESLA_DASHBOARD_ABFRAGESPERRE_BIS=ende,
                    TESLA_DASHBOARD_DATA_DIR=str(tmp_path),
                    STATISTICS_DB_PATH=str(tmp_path / "statistik.db"),
                    DISABLE_STATISTICS_AGGREGATION="1")
    # Der richtige Starter lädt den ganzen Anwendungscode; nur der Serverlauf
    # wird durch eine lokale Bereitschaftsmeldung ersetzt. Kein HTTP-Aufruf.
    befehl = (
        "import sys; from pathlib import Path; "
        f"sys.path.insert(0, {str(projekt)!r}); "
        "from tools import telemetrie_geschuetzter_start as starter; "
        "import flask_socketio; "
        "flask_socketio.SocketIO.run = lambda *a, **k: print('START_OK'); "
        f"starter.main(Path({str(tmp_path)!r}))"
    )
    # Eine kleine Kopie ohne Produktivdaten; Templates werden beim Start nicht gerendert.
    (tmp_path / "data").mkdir()
    (tmp_path / "app.py").write_bytes((projekt / "app.py").read_bytes())
    ergebnis = subprocess.run([sys.executable, "-c", befehl], env=umgebung,
                              capture_output=True, text=True, timeout=30)
    assert ergebnis.returncode == 0, ergebnis.stderr[-3000:]
    assert "START_OK" in ergebnis.stdout


# © 2026 Erik Schauer, do1ffe@darc.de
