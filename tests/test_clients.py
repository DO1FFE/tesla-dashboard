import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


def _client_eintrag(first_seen, last_seen):
    return {
        "ip": "127.0.0.1",
        "hostname": "localhost",
        "location": "Teststadt, DE",
        "provider": "Testanbieter",
        "browser": "Chrome",
        "os": "Linux",
        "user_agent": "Testbrowser",
        "pages": ["index.html"],
        "first_seen": first_seen,
        "last_seen": last_seen,
    }


def test_client_details_liefern_startzeit(monkeypatch):
    monkeypatch.setattr(app, "load_config", lambda vehicle_id=None: {})
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    app.active_clients.clear()
    app.active_clients["127.0.0.1"] = _client_eintrag(1935.0, 2000.0)
    client = app.app.test_client()

    try:
        response = client.get("/api/clients/details")
    finally:
        app.active_clients.clear()

    data = response.get_json()
    assert response.status_code == 200
    assert data["clients"][0]["duration"] == "00 Tage, 00:01:05"
    assert data["clients"][0]["first_seen_ms"] == 1935000


def test_clients_seite_enthaelt_startzeit(monkeypatch):
    monkeypatch.setattr(app, "load_config", lambda vehicle_id=None: {})
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    app.active_clients.clear()
    app.active_clients["127.0.0.1"] = _client_eintrag(1935.0, 2000.0)
    client = app.app.test_client()

    try:
        response = client.get("/clients")
    finally:
        app.active_clients.clear()

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-first-seen="1935000"' in html
    assert "00 Tage, 00:01:05" in html


def test_stream_trennung_behaelt_startzeit_bis_timeout(monkeypatch):
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    app.active_clients.clear()
    app.active_clients["127.0.0.1"] = _client_eintrag(1000.0, 1999.0)
    app.active_clients["127.0.0.1"]["connections"] = 1

    try:
        app._client_stream_getrennt("127.0.0.1")
        items = app._client_detail_liste(now=2001.0)
    finally:
        app.active_clients.clear()

    assert len(items) == 1
    assert items[0]["first_seen_ms"] == 1000000
    assert items[0]["duration"] == "00 Tage, 00:16:41"


def test_fehlende_startzeit_wird_stabil_nachgetragen(monkeypatch):
    monkeypatch.setattr(app.time, "time", lambda: 2000.0)
    app.active_clients.clear()
    app.active_clients["127.0.0.1"] = {
        "ip": "127.0.0.1",
        "pages": ["index.html"],
        "last_seen": 1995.0,
    }

    try:
        zuerst = app._client_detail_liste(now=2000.0)
        später = app._client_detail_liste(now=2005.0)
    finally:
        app.active_clients.clear()

    assert zuerst[0]["first_seen_ms"] == 1995000
    assert zuerst[0]["duration"] == "00 Tage, 00:00:05"
    assert später[0]["first_seen_ms"] == 1995000
    assert später[0]["duration"] == "00 Tage, 00:00:10"


def test_direkter_client_kann_ip_nicht_per_header_fälschen(monkeypatch):
    monkeypatch.setattr(
        app,
        "VERTRAUENSWÜRDIGE_PROXY_NETZE",
        (app.ipaddress.ip_network("172.18.0.1/32"),),
    )

    with app.app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "203.0.113.10"},
        headers={"X-Forwarded-For": "198.51.100.25"},
    ):
        assert app._client_ip() == "203.0.113.10"


def test_proxy_kette_liefert_letzten_nicht_vertrauenswürdigen_client(
    monkeypatch,
):
    monkeypatch.setattr(
        app,
        "VERTRAUENSWÜRDIGE_PROXY_NETZE",
        (app.ipaddress.ip_network("172.18.0.1/32"),),
    )

    with app.app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "172.18.0.1"},
        headers={
            "X-Forwarded-For": "198.51.100.25, 203.0.113.10",
            "X-Real-IP": "203.0.113.10",
        },
    ):
        assert app._client_ip() == "203.0.113.10"


def test_browser_mit_gleicher_ip_werden_getrennt_erfasst(monkeypatch):
    monkeypatch.setattr(app, "_cached_hostname", lambda _ip: "")
    monkeypatch.setattr(app, "lookup_location", lambda _ip: "")
    monkeypatch.setattr(app, "lookup_provider", lambda _ip: "")
    app.active_clients.clear()
    headers_a = {
        "Cookie": f"client_id={'a' * 32}",
        "User-Agent": "Gleicher Testbrowser",
    }
    headers_b = {
        "Cookie": f"client_id={'b' * 32}",
        "User-Agent": "Gleicher Testbrowser",
    }

    try:
        with app.app.test_request_context(
            "/",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
            headers=headers_a,
        ):
            app._track_client()
        with app.app.test_request_context(
            "/",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
            headers=headers_b,
        ):
            app._track_client()

        assert len(app.active_clients) == 2
        assert {
            daten["ip"] for daten in app.active_clients.values()
        } == {"203.0.113.10"}
    finally:
        app.active_clients.clear()


def test_bekannter_browser_aktualisiert_seine_ip(monkeypatch):
    monkeypatch.setattr(app, "_cached_hostname", lambda ip: f"host-{ip}")
    monkeypatch.setattr(app, "lookup_location", lambda ip: f"ort-{ip}")
    monkeypatch.setattr(app, "lookup_provider", lambda ip: f"anbieter-{ip}")
    app.active_clients.clear()
    headers = {
        "Cookie": f"client_id={'c' * 32}",
        "User-Agent": "Mobiler Testbrowser",
    }

    try:
        with app.app.test_request_context(
            "/",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
            headers=headers,
        ):
            app._track_client()
        with app.app.test_request_context(
            "/",
            environ_base={"REMOTE_ADDR": "198.51.100.25"},
            headers=headers,
        ):
            app._track_client()

        daten = next(iter(app.active_clients.values()))
        assert daten["ip"] == "198.51.100.25"
        assert daten["hostname"] == "host-198.51.100.25"
        assert daten["location"] == "ort-198.51.100.25"
        assert daten["provider"] == "anbieter-198.51.100.25"
    finally:
        app.active_clients.clear()
