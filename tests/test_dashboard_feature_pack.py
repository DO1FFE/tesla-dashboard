import base64
import json
import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
import app as app_module


app = app_module.app


def auth_headers(user="test@example.org", password="geheim"):
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _http_error(status=429, headers=None):
    response = app_module.requests.Response()
    response.status_code = status
    response.headers.update(headers or {})
    error = app_module.requests.exceptions.HTTPError(f"{status} Client Error")
    error.response = response
    return error


def test_api_daten_bleiben_trotz_privatmodus_real(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "load_config",
        lambda vehicle_id=None: {"privacy-mode": True, "privacy_precision": 1},
    )
    monkeypatch.setattr(app_module, "_start_thread", lambda vehicle_id: None)
    app_module.latest_data["fahrzeug"] = {
        "drive_state": {"latitude": 51.455123, "longitude": 7.012345},
        "location_address": "Straße 1",
    }

    try:
        response = app.test_client().get("/api/data/fahrzeug")
    finally:
        app_module.latest_data.pop("fahrzeug", None)

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["drive_state"]["latitude"] == 51.455123
    assert payload["drive_state"]["longitude"] == 7.012345
    assert payload["location_address"] == "Straße 1"
    assert "privacy_mode" not in payload
    assert "privacy_radius_m" not in payload


def test_apiliste_aktualisiert_vor_ausgabe(monkeypatch, tmp_path):
    erfasst = {}

    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_start_thread", lambda vehicle_id: None)
    monkeypatch.setattr(app_module, "_fetch_data_once", lambda vehicle_id: {})
    monkeypatch.setattr(
        app_module,
        "latest_data",
        {
            "default": {
                "drive_state": {"shift_state": "P"},
                "path": [[51.0, 7.0]],
            },
        },
    )

    def fake_update_api_list(data):
        erfasst["data"] = data
        (tmp_path / "api-liste.txt").write_text(
            "drive_state.shift_state: P\n"
            "path: [[51.0, 7.0]]\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(app_module, "update_api_list", fake_update_api_list)

    response = app.test_client().get("/apiliste")

    assert response.status_code == 200
    assert erfasst["data"]["drive_state"]["shift_state"] == "P"
    text = response.get_data(as_text=True)
    assert "drive_state.shift_state: P" in text
    assert "path:" not in text


def test_stream_fehlerpfad_setzt_karte_nicht_auf_default():
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")
    start = js.index("eventSource.onerror = function()")
    ende = js.index("function startStreamIfOnline()", start)
    fehlerpfad = js[start:ende]

    assert "map.setView(DEFAULT_POS" not in fehlerpfad
    assert "STREAM_WIEDERVERBINDUNG_MS = 250" in js
    assert "streamWiederverbindungsTimer = setTimeout(function()" in fehlerpfad
    assert "startStream();" in fehlerpfad
    assert "setTimeout(startStreamIfOnline" not in fehlerpfad
    assert "5000" not in fehlerpfad


def test_live_zoom_nutzt_drive_speed_immer_als_mph():
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")
    start = js.index("var speedVal = parseFloat(drive.speed);")
    ende = js.index("var zoom = computeZoomForSpeed(speedKmh);", start)
    zoombereich = js[start:ende]

    assert "speedVal * MILES_TO_KM" in zoombereich
    assert "gui_distance_units" not in zoombereich


def test_karte_filtert_gps_drift_im_geparkten_zustand():
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")

    assert "PARKED_MAP_JITTER_METERS" in js
    assert "function entfernungMeter" in js
    assert "function fahrzeugIstGeparktFuerKarte" in js
    assert "positionIstNeu(mapLat, mapLng, karteGeparkt)" in js
    assert "entfernung < PARKED_MAP_JITTER_METERS" in js
    assert "if (coordsNeu || !letzteKartenPosition)" in js


def test_fahrzeugsymbole_sind_in_ui_eingebunden():
    html = pathlib.Path("templates/index.html").read_text(encoding="utf-8")
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")

    assert 'id="vehicle-symbols"' in html
    assert 'id="speed-limit-symbol"' in html
    assert 'id="center-display-symbol"' in html
    assert 'id="software-update-symbol"' in html
    assert "updateVehicleSymbols(vehicle, data.gui_settings || {})" in js


def test_footer_zeigt_telemetrie_profile():
    html = pathlib.Path("templates/index.html").read_text(encoding="utf-8")
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")

    assert 'id="telemetry-profile"' in html
    assert "updateTelemetryProfile(" in js
    assert "data.telemetry_profile," in js
    assert "data.telemetry_profile_target_since" in js
    assert "data.telemetry_profile_park_delay_seconds" in js
    assert "function zeichneTelemetryProfile" in js
    assert "telemetryProfileParkCountdownSekunden" in js
    assert "Telemetry: " in js
    assert "sun_roof_status_available" in js
    assert "part-unknown" in js


def test_technische_packdetails_sind_in_ui_eingebunden():
    html = pathlib.Path("templates/index.html").read_text(encoding="utf-8")
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")

    assert 'id="technical-info"' in html
    assert "updateTechnischeDetails(charge)" in js
    assert "charge.pack_voltage" in js
    assert "charge.pack_current" in js
    assert "charge.pack_power" in js


def test_batterietemperatur_zeigt_durchschnitt_minimum_und_maximum():
    html = pathlib.Path("templates/index.html").read_text(encoding="utf-8")
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")
    css = pathlib.Path("static/css/style.css").read_text(encoding="utf-8")

    assert "Batterie Ø: -- °C" in html
    assert 'id="battery-temp-minmax"' in html
    assert 'id="battery-temp-min-value"' in html
    assert 'id="battery-temp-max-value"' in html
    assert "charge.module_temp_min" in js
    assert "charge.module_temp_max" in js
    assert "anzeigename += ' Ø'" in js
    assert "aktualisiereBatterieTemperaturGrenzen" in js
    assert "Batterietemperatur Min/Max" in js
    assert "#battery-temp-minmax" in css


def test_innen_und_wunschtemperatur_richten_doppelpunkte_aus():
    html = pathlib.Path("templates/index.html").read_text(encoding="utf-8")
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")
    css = pathlib.Path("static/css/style.css").read_text(encoding="utf-8")

    assert 'id="inside-temp-value" class="label temperatur-zeile"' in html
    assert 'id="desired-temp" class="label temperatur-zeile"' in html
    assert '<span class="temperatur-name">Innen:</span>' in html
    assert '<span class="temperatur-name">Wunsch:</span>' in html
    assert "function setzeTemperaturAnzeige" in js
    assert "setzeTemperaturAnzeige('#desired-temp', 'Wunsch'" in js
    assert "setzeTemperaturAnzeige($label, anzeigename, label)" in js
    assert "#inside-temp-value.temperatur-zeile" in css
    assert "#desired-temp.temperatur-zeile" in css
    assert "grid-template-columns: 4.6em 4.4em" in css


def test_pedalposition_ist_unter_dem_tacho_eingebunden():
    html = pathlib.Path("templates/index.html").read_text(encoding="utf-8")
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")
    css = pathlib.Path("static/css/style.css").read_text(encoding="utf-8")

    assert 'id="pedal-position-needle"' in html
    assert 'id="pedal-position-needle-outline"' in html
    assert 'id="pedal-position-value"' not in html
    assert html.index('id="speedometer-needle"') < html.index('id="pedal-position-needle"')
    assert "updatePedalPosition(vehicle.pedal_position)" in js
    assert "function updatePedalPosition(value)" in js
    assert "prozent / 100 * 180 - 90" in js
    assert "#pedal-position-needle" in css
    assert "#pedal-position-needle-outline" in css
    assert "#speedometer .pedal-position" not in css


def test_routeline_wird_in_der_livekarte_verwendet():
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")

    assert "function dekodierePolyline(polyline, praezision)" in js
    assert "function routeLineZuKartenPunkte(routeLine)" in js
    assert "dekodierePolyline(kodiertePolyline, 6)" in js
    assert "privacyModeAktiv ? [] : routeLineZuKartenPunkte(drive.active_route_line)" in js
    assert "var zeigtNavigationsLinie = nutztRouteLine || (" in js
    assert "var linienPunkte = nutztRouteLine ? routenPunkte : []" in js
    assert "linienPunkte = [[mapLat, mapLng], [dLat, dLng]]" in js
    assert "nutztRouteLine ? kartenPunkteSignatur(routenPunkte) : 'luftlinie'" in js
    assert "color: '#00e5ff'" in js
    assert "smoothFactor: 0" in js
    assert "lineJoin: 'round'" in js


def test_livekarte_verwirft_unplausible_routeline_spruenge():
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")

    assert "ROUTENPUNKT_MAX_SPRUNG_METER" in js
    assert "function routenPunkteSindPlausibel" in js
    assert "function routenPunkteAusreisserAmRandEntfernen(points)" in js
    assert "routenPunkte = routenPunkteAusreisserAmRandEntfernen(routenPunkte)" in js
    assert "bereinigt.shift()" in js
    assert "bereinigt.pop()" in js
    assert "entfernung > ROUTENPUNKT_MAX_SPRUNG_METER" in js
    assert "routenPunkteSindPlausibel(" in js
    assert "aktuellePositionPlausibel ? mapLat : null" in js
    assert "zielKoordinatePlausibel ? dLat : null" in js
    assert "istPlausibleNavigationsZielKoordinate(dLat, dLng)" in js


def test_livekarte_loescht_navigation_bei_inaktivem_status():
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")

    assert "function navigationFuerKarteAktiv(data, drive)" in js
    assert "drive.active_route_active === false" in js
    assert "drive.active_route_active === true" in js
    assert "drive.active_route_line ||" not in js
    assert "var navigationInKarteAktiv = navigationFuerKarteAktiv(data, drive)" in js
    assert "navigationInKarteAktiv && (zeigtNavigationsLinie || zielKoordinatePlausibel)" in js


def test_livepfad_wird_per_delta_an_leaflet_angehaengt():
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")

    assert "lastPathDelta.push(pt)" in js
    assert "function neuerPfadNurAngehängt(data)" in js
    assert "polyline.addLatLng(pt)" in js


def test_live_update_alter_nutzt_telemetrie_empfangszeit():
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")
    start = js.index("function neuesterDatenZeitstempel")
    ende = js.index("function updateDataAge", start)
    block = js[start:ende]

    assert "data && data.fleet_telemetry_received_at" in block
    assert (
        block.index("data && data.fleet_telemetry_received_at")
        < block.index("data && data.fleet_telemetry_updated_at")
    )


def test_stream_heartbeat_wird_im_browser_als_signal_genutzt():
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")

    assert "var lastStreamTimestamp = null" in js
    assert "function aktualisiereStreamSignal(ts)" in js
    assert "eventSource.addEventListener('stream'" in js
    assert "data.stream_heartbeat_at" in js
    assert "Letztes Signal vor " in js


def test_online_und_offline_state_zaehlen_seit_dauer_hoch():
    js = pathlib.Path("static/js/main.js").read_text(encoding="utf-8")

    assert "lastStateSinceTimestamp" in js
    assert "function formatiereHochzaehlendeDauer(seitMillis)" in js
    assert "function normalisiereDashboardState(status)" in js
    assert "st === 'disconnected'" in js
    assert "return 'offline'" in js
    assert "State: ' + lastVehicleState" in js
    assert "lastVehicleState === 'offline'" in js
    assert "lastVehicleState === 'online'" in js
    assert "text += ' (seit ' + formatiereHochzaehlendeDauer" in js


def test_history_nutzt_trotz_privatmodus_reale_punkte(monkeypatch):
    trip_path = str(pathlib.Path(app_module.DATA_DIR) / "fahrzeug" / "trips" / "trip_20260521.csv")
    monkeypatch.setattr(
        app_module,
        "load_config",
        lambda vehicle_id=None: {"privacy-mode": True, "privacy_precision": 1},
    )
    monkeypatch.setattr(app_module, "_get_trip_files", lambda: [trip_path])
    monkeypatch.setattr(app_module, "_get_trip_periods", lambda: ([], [], []))
    monkeypatch.setattr(
        app_module,
        "_load_trip",
        lambda path: [[51.455123, 7.012345, 0, 0, 0, 123]],
    )
    monkeypatch.setattr(app_module, "compute_trip_summaries", lambda: ({}, {}))

    response = app.test_client().get("/history")

    assert response.status_code == 200
    assert b"51.455123" in response.data
    assert b"7.012345" in response.data


def test_heatmap_nutzt_trotz_privatmodus_reale_punkte(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "load_config",
        lambda vehicle_id=None: {"privacy-mode": True, "privacy_precision": 1},
    )
    monkeypatch.setattr(app_module, "_trip_paths_for_scope", lambda *args, **kwargs: ["trip"])
    monkeypatch.setattr(
        app_module,
        "_heatmap_points_for_paths",
        lambda paths, max_points=None: [(51.455123, 7.012345, 0.5)],
    )

    response = app.test_client().get("/api/heatmap")

    assert response.status_code == 200
    assert response.get_json()["points"] == [[51.455123, 7.012345, 0.5]]


def test_fahrten_export_nutzt_trotz_privatmodus_reale_datei(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "load_config",
        lambda vehicle_id=None: {"privacy-mode": True, "privacy_precision": 1},
    )
    monkeypatch.setattr(
        app_module,
        "_fahrtberichte_laden",
        lambda: [{"datei": "fahrzeug/trips/trip_20260521.csv"}],
    )

    rows = app_module._datensatz_exportieren("fahrten")

    assert rows[0]["datei"] == "fahrzeug/trips/trip_20260521.csv"


def test_export_routen_liefern_json_csv_pdf(monkeypatch):
    monkeypatch.setenv("TESLA_EMAIL", "test@example.org")
    monkeypatch.setenv("TESLA_PASSWORD", "geheim")
    monkeypatch.setattr(
        app_module,
        "_datensatz_exportieren",
        lambda dataset: [{"zeit": "01.01.2026 12:00:00", "wert": 42}],
    )
    client = app.test_client()

    json_response = client.get("/export/statistik.json", headers=auth_headers())
    csv_response = client.get("/export/statistik.csv", headers=auth_headers())
    pdf_response = client.get("/export/statistik.pdf", headers=auth_headers())

    assert json_response.status_code == 200
    assert json_response.get_json()["rows"][0]["wert"] == 42
    assert csv_response.status_code == 200
    assert "zeit,wert" in csv_response.get_data(as_text=True)
    assert pdf_response.status_code == 200
    assert pdf_response.mimetype == "application/pdf"
    assert pdf_response.data.startswith(b"%PDF")


def test_timeline_page_zeigt_ereignisse(monkeypatch):
    monkeypatch.setenv("TESLA_EMAIL", "test@example.org")
    monkeypatch.setenv("TESLA_PASSWORD", "geheim")
    monkeypatch.setattr(
        app_module,
        "_timeline_events",
        lambda limit=100: [
            {
                "zeit": "01.01.2026 12:00:00",
                "typ": "Status",
                "titel": "Fahrzeugstatus: online",
                "details": "Test",
                "severity": "ok",
            }
        ],
    )

    response = app.test_client().get("/timeline", headers=auth_headers())

    assert response.status_code == 200
    assert "Fahrzeugstatus: online".encode("utf-8") in response.data


def test_werkzeug_navigation_markiert_aktuelle_seite(monkeypatch):
    monkeypatch.setenv("TESLA_EMAIL", "test@example.org")
    monkeypatch.setenv("TESLA_PASSWORD", "geheim")
    monkeypatch.setattr(app_module, "_ladeberichte_laden", lambda: [])

    response = app.test_client().get("/laden", headers=auth_headers())
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<a class="is-active" href="/laden" aria-current="page">Laden</a>' in html


def test_seitenmenü_zeigt_aktuelle_seite_trotz_ausgeblendeter_links(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "load_config",
        lambda vehicle_id=None: {
            "page-menu": True,
            "menu-dashboard": False,
            "menu-statistik": False,
            "menu-history": False,
            "menu-heatmap": False,
        },
    )
    monkeypatch.setattr(app_module, "_get_trip_files", lambda: [])
    monkeypatch.setattr(app_module, "_get_trip_periods", lambda: ([], [], []))
    monkeypatch.setattr(app_module, "compute_trip_summaries", lambda: ({}, {}))

    response = app.test_client().get("/history")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert (
        '<a class="menu-button is-active" href="/history" '
        'aria-current="page">History</a>'
    ) in html


def test_ptt_notiz_wichtig_und_löschen(tmp_path, monkeypatch):
    monkeypatch.setenv("TESLA_EMAIL", "test@example.org")
    monkeypatch.setenv("TESLA_PASSWORD", "geheim")
    monkeypatch.setattr(app_module, "PTT_RECORDINGS_DIR", str(tmp_path))
    old_csrf = app.config.get("WTF_CSRF_ENABLED", True)
    app.config["WTF_CSRF_ENABLED"] = False
    audio = tmp_path / "aufnahme.webm"
    audio.write_bytes(b"audio")
    app_module._ptt_index_schreiben_ungesperrt([
        {
            "id": "abc",
            "filename": "aufnahme.webm",
            "timestamp": 9999999999,
            "duration_seconds": 2.0,
            "size_bytes": 5,
        }
    ])
    client = app.test_client()

    try:
        response = client.post(
            "/ptt",
            data={
                "action": "save",
                "recording_id": "abc",
                "note": "merken",
                "important": "1",
            },
            headers=auth_headers(),
        )
        assert response.status_code == 302
        eintrag = app_module._ptt_aufnahme_finden("abc")
        assert eintrag["note"] == "merken"
        assert eintrag["important"] is True

        response = client.post(
            "/ptt",
            data={"action": "delete", "recording_id": "abc"},
            headers=auth_headers(),
        )
        assert response.status_code == 302
        assert app_module._ptt_aufnahme_finden("abc") is None
        assert not audio.exists()
    finally:
        app.config["WTF_CSRF_ENABLED"] = old_csrf


def test_ladebericht_zusammenfassung():
    summary = app_module._ladebericht_zusammenfassung([
        {"monat": "2026-05", "energy_kwh": 10.5},
        {"monat": "2026-05", "energy_kwh": 4.5},
        {"monat": "2026-04", "energy_kwh": 2.0},
    ])

    assert summary["sessions"] == 3
    assert summary["energy_kwh"] == 17.0
    assert summary["months"][0]["month"] == "2026-05"


def test_ladeberichte_laden_dedupliziert_migrierte_logs(monkeypatch):
    einträge = [
        {
            "timestamp": 1779988768.813,
            "data": {"vehicle_id": "1492931508551122", "added_energy": 38.95},
        },
        {
            "timestamp": 1779988768.813,
            "data": {"vehicle_id": "1492931508551122", "added_energy": 38.95},
        },
        {
            "timestamp": 1779727020.766,
            "data": {"vehicle_id": "1492931508551122", "added_energy": 30.76},
        },
    ]
    monkeypatch.setattr(app_module, "_json_log_einträge", lambda name: einträge)

    berichte = app_module._ladeberichte_laden()
    summary = app_module._ladebericht_zusammenfassung(berichte)

    assert len(berichte) == 2
    assert summary["sessions"] == 2
    assert summary["energy_kwh"] == 69.71


def test_health_api(monkeypatch):
    monkeypatch.setenv("TESLA_EMAIL", "test@example.org")
    monkeypatch.setenv("TESLA_PASSWORD", "geheim")
    monkeypatch.setattr(app_module, "load_config", lambda vehicle_id=None: {})
    monkeypatch.setattr(app_module, "_ptt_aufnahmen_laden", lambda: [])
    monkeypatch.setattr(app_module, "_ptt_diagnosen_auflisten", lambda: [])

    response = app.test_client().get("/api/health", headers=auth_headers())
    data = json.loads(response.data)

    assert response.status_code == 200
    assert "polling" in data


def test_health_api_fasst_cache_aliase_zusammen(monkeypatch):
    monkeypatch.setenv("TESLA_EMAIL", "test@example.org")
    monkeypatch.setenv("TESLA_PASSWORD", "geheim")
    monkeypatch.setattr(app_module, "load_config", lambda vehicle_id=None: {})
    monkeypatch.setattr(app_module, "_ptt_aufnahmen_laden", lambda: [])
    monkeypatch.setattr(app_module, "_ptt_diagnosen_auflisten", lambda: [])
    monkeypatch.setattr(app_module, "api_errors", [])
    monkeypatch.setattr(
        app_module,
        "latest_data",
        {
            "config.env": {
                "id_s": "1492931508551122",
                "state": "online",
                "_live": True,
                "state_checked_at": 1779988768000,
            },
            "debug.log": {
                "id_s": "1492931508551122",
                "state": "online",
                "_live": True,
                "state_checked_at": 1779988769000,
            },
            "1492931508551122": {
                "id_s": "1492931508551122",
                "state": "online",
                "_live": True,
                "state_checked_at": 1779988770000,
            },
        },
    )

    response = app.test_client().get("/api/health", headers=auth_headers())
    data = json.loads(response.data)

    assert response.status_code == 200
    assert [row["vehicle_id"] for row in data["latest"]] == ["1492931508551122"]


def test_supercharger_rate_limit_nutzt_retry_after(monkeypatch):
    app_module._supercharger_cache.clear()
    app_module._supercharger_backoff_until.clear()
    fehler = []
    now = [1000.0]
    backoff_until = None

    class Vehicle:
        def __init__(self):
            self.calls = 0

        def api(self, endpoint):
            self.calls += 1
            assert endpoint == "NEARBY_CHARGING_SITES"
            raise _http_error(429, {"Retry-After": "120"})

    vehicle = Vehicle()
    monkeypatch.setattr(app_module.time, "time", lambda: now[0])
    monkeypatch.setattr(app_module, "_log_api_error", lambda exc: fehler.append(exc))

    try:
        result = app_module._fetch_nearby_superchargers(
            vehicle,
            {"latitude": 51.0, "longitude": 7.0},
            "fahrzeug",
        )
        result_backoff = app_module._fetch_nearby_superchargers(
            vehicle,
            {"latitude": 51.0, "longitude": 7.0},
            "fahrzeug",
        )
        backoff_until = app_module._supercharger_backoff_until.get("fahrzeug")
    finally:
        app_module._supercharger_cache.clear()
        app_module._supercharger_backoff_until.clear()

    assert result == []
    assert result_backoff == []
    assert vehicle.calls == 1
    assert fehler == []
    assert backoff_until == 1120.0


def test_supercharger_rate_limit_nutzt_alten_cache(monkeypatch):
    app_module._supercharger_cache.clear()
    app_module._supercharger_backoff_until.clear()
    now = [2000.0]
    payload = {
        "response": {
            "superchargers": [
                {
                    "name": "Essen, Germany",
                    "available_stalls": 2,
                    "total_stalls": 8,
                    "location": {"lat": 51.05, "long": 7.05},
                }
            ]
        }
    }
    cache_key = ("fahrzeug", app_module._coarse_location(51.0, 7.0))
    app_module._supercharger_cache[cache_key] = {
        "payload": payload,
        "ts": 1.0,
        "location": (51.0, 7.0),
    }

    class Vehicle:
        def __init__(self):
            self.calls = 0

        def api(self, endpoint):
            self.calls += 1
            assert endpoint == "NEARBY_CHARGING_SITES"
            raise _http_error(429, {"RateLimit-Device-Realtime-Reset": "60"})

    vehicle = Vehicle()
    monkeypatch.setattr(app_module.time, "time", lambda: now[0])

    try:
        result = app_module._fetch_nearby_superchargers(
            vehicle,
            {"latitude": 51.0, "longitude": 7.0},
            "fahrzeug",
        )
        result_backoff = app_module._fetch_nearby_superchargers(
            vehicle,
            {"latitude": 51.0, "longitude": 7.0},
            "fahrzeug",
        )
    finally:
        app_module._supercharger_cache.clear()
        app_module._supercharger_backoff_until.clear()

    assert result[0]["name"] == "Essen, Germany"
    assert result_backoff[0]["name"] == "Essen, Germany"
    assert vehicle.calls == 1
