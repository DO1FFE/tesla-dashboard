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


def test_ladeplanung_und_reifendruckdetails_sind_konfigurierbar():
    ids = {item["id"] for item in app.CONFIG_ITEMS}

    assert "ladeplanung-info" in ids
    assert "preconditioning-info" in ids
    assert "technical-info" in ids
    assert "reifendruck-details" in ids


def test_hauptseite_enthält_zusatzanzeigen(monkeypatch):
    client = _test_client(monkeypatch)

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="ladeplanung-info"' in html
    assert 'id="preconditioning-info"' in html
    assert 'id="technical-info"' in html
    assert 'id="reifendruck-details"' in html
