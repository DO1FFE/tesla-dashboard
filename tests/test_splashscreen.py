import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


def _test_client(monkeypatch):
    monkeypatch.setattr(app, "_start_statistics_aggregation", lambda: None)
    monkeypatch.setattr(app, "_schedule_socketio_client_download", lambda: None)
    monkeypatch.setattr(app, "socketio_client_script", lambda: "/static/js/socket.io-test.js")
    monkeypatch.setattr(app, "load_config", lambda: {})
    app.app.config["TESTING"] = True
    return app.app.test_client()


def test_erster_direkter_hauptseitenaufruf_zeigt_splashscreen(monkeypatch):
    client = _test_client(monkeypatch)

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="splashscreen"' in response.get_data(as_text=True)


def test_rückkehr_von_statistik_zeigt_keinen_splashscreen(monkeypatch):
    client = _test_client(monkeypatch)

    response = client.get("/", headers={"Referer": "http://localhost/statistik"})

    assert response.status_code == 200
    assert 'id="splashscreen"' not in response.get_data(as_text=True)


def test_zweiter_hauptseitenaufruf_zeigt_keinen_splashscreen(monkeypatch):
    client = _test_client(monkeypatch)

    erster_response = client.get("/")
    zweiter_response = client.get("/")

    assert 'id="splashscreen"' in erster_response.get_data(as_text=True)
    assert 'id="splashscreen"' not in zweiter_response.get_data(as_text=True)
