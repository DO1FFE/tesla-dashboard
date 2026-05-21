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
