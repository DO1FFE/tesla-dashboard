import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


def test_wartungsmodus_zeigt_wartungsseite(monkeypatch, tmp_path):
    wartungsdatei = tmp_path / "wartung"
    wartungsdatei.write_text("aktiv\n", encoding="utf-8")
    monkeypatch.setenv("TESLA_DASHBOARD_WARTUNG", "1")
    monkeypatch.setattr(app, "WARTUNGSMODUS_DATEI", str(wartungsdatei))

    response = app.app.test_client().get("/")

    assert response.status_code == 503
    assert b"Dashboard wird gerade auf Fleet Telemetry umgestellt" in response.data
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert response.headers["Retry-After"] == "300"


def test_wartungsmodus_laesst_api_und_public_key_durch(monkeypatch, tmp_path):
    wartungsdatei = tmp_path / "wartung"
    wartungsdatei.write_text("aktiv\n", encoding="utf-8")
    public_key = tmp_path / "com.tesla.3p.public-key.pem"
    public_key.write_text("PUBLIC KEY\n", encoding="utf-8")
    monkeypatch.setenv("TESLA_DASHBOARD_WARTUNG", "1")
    monkeypatch.setattr(app, "WARTUNGSMODUS_DATEI", str(wartungsdatei))
    monkeypatch.setattr(app, "TESLA_FLEET_PUBLIC_KEY_PATH", str(public_key))

    client = app.app.test_client()

    assert client.get("/api/version").status_code == 200
    assert client.get("/.well-known/appspecific/com.tesla.3p.public-key.pem").status_code == 200
