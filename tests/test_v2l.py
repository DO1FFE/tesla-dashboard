import copy
import time

import pytest

import app


def _v2l_daten(
    zeit_ms,
    soc=80.0,
    ladestatus="Starting",
    packleistung_kw=-2.0,
):
    packspannung = 400.0
    packstrom = packleistung_kw * 1000.0 / packspannung
    return {
        "id_s": "fahrzeug-1",
        "state": "online",
        "fleet_telemetry_received_at": zeit_ms,
        "fleet_telemetry_field_received_at": {
            "PackCurrent": zeit_ms,
            "PackVoltage": zeit_ms,
        },
        "fleet_telemetry_raw": {
            "PackCurrent": packstrom,
            "PackVoltage": packspannung,
        },
        "charge_state": {
            "battery_level": soc,
            "usable_battery_level": soc,
            "charging_state": ladestatus,
            "charger_power": 4.0,
            "conn_charge_cable": "IEC",
            "charge_port_color": "FlashingGreen",
            "pack_power": packleistung_kw,
            "pack_voltage": packspannung,
            "pack_current": packstrom,
            "timestamp": zeit_ms,
        },
        "drive_state": {
            "shift_state": "P",
            "speed": 0,
            "timestamp": zeit_ms,
        },
        "vehicle_state": {},
    }


def test_v2l_signatur_und_liveprofil_werden_erkannt():
    daten = _v2l_daten(1_700_000_000_000)

    assert app._v2l_signatur_aktiv(daten) is True
    daten["charge_state"]["conn_charge_cable"] = None
    daten["charge_state"]["charge_port_color"] = None
    assert app._v2l_signatur_aktiv(daten) is True
    daten["v2l_active"] = True
    assert app._fleet_telemetrie_profile_ziel(daten) == "live"

    daten["charge_state"]["charging_state"] = "Charging"
    assert app._v2l_signatur_aktiv(daten) is False


def test_v2l_signatur_verhindert_ladeprofil_auch_ohne_cacheflag():
    daten = _v2l_daten(
        1_700_000_100_000,
        packleistung_kw=-0.23,
    )
    daten["charge_state"]["charger_power"] = 3.7865848894280574
    daten["charge_state"]["charge_port_color"] = None

    assert "v2l_active" not in daten
    assert app._v2l_signatur_aktiv(daten) is True
    assert app._fleet_telemetrie_profile_ladezustand(daten) is False
    assert app._fleet_telemetrie_profile_ziel(daten) == "live"

    daten["charge_state"]["pack_power"] = 4.0
    daten["charge_state"]["pack_current"] = 10.0
    daten["charge_state"]["charge_port_color"] = "FlashingGreen"
    assert app._v2l_signatur_aktiv(daten) is False
    assert app._fleet_telemetrie_profile_ladezustand(daten) is True
    assert app._fleet_telemetrie_profile_ziel(daten) == "charging"


def test_v2l_status_wird_auf_alle_cache_aliasse_gespiegelt(monkeypatch):
    zeit_ms = 1_700_000_200_000
    basis = _v2l_daten(zeit_ms)
    cache_ids = ["fahrzeug-1", "alias-1", "default"]
    profilauswertungen = []
    profil_ziel = app._fleet_telemetrie_profile_ziel

    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_fahrzeuge",
        lambda: [{
            "vin": "TESTVIN",
            "id_s": "fahrzeug-1",
            "id": "alias-1",
        }],
    )
    monkeypatch.setattr(app, "_default_vehicle_id", "fahrzeug-1")
    monkeypatch.setattr(
        app,
        "latest_data",
        {cache_id: copy.deepcopy(basis) for cache_id in cache_ids},
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_aktualisieren",
        lambda cache_id, daten: (
            profilauswertungen.append(
                (cache_id, daten.get("v2l_active"), profil_ziel(daten))
            )
            or daten
        ),
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_parkstatus_aufzeichnen",
        lambda *_args: None,
    )
    monkeypatch.setattr(app, "_subscriber_daten_senden", lambda *_args: None)
    monkeypatch.setattr(app, "_aprs_spaeter_senden", lambda *_args: None)

    assert app._fleet_telemetrie_cache_ids("TESTVIN") == cache_ids
    assert app._fleet_telemetrie_v_felder_aktualisieren(
        "TESTVIN",
        [
            ("PackCurrent", -5.0, zeit_ms + 1_000),
            ("PackVoltage", 400.0, zeit_ms + 1_000),
        ],
    ) is True

    assert profilauswertungen == [
        ("fahrzeug-1", True, "live"),
        ("alias-1", True, "live"),
        ("default", True, "live"),
    ]
    for daten in app.latest_data.values():
        assert daten["v2l_active"] is True
        assert isinstance(daten["v2l_session_id"], int)


def test_v2l_integriert_packleistung_lueckenlos():
    start_ms = 1_700_000_000_000
    for sekunden in range(0, 61, 10):
        daten = _v2l_daten(
            start_ms + sekunden * 1000,
            soc=80.0 - sekunden / 1000.0,
        )
        app._v2l_telemetrie_aktualisieren("fahrzeug-1", daten)
        assert daten["v2l_active"] is True

    ende = _v2l_daten(
        start_ms + 70_000,
        soc=79.93,
        ladestatus="Disconnected",
    )
    app._v2l_telemetrie_aktualisieren("fahrzeug-1", ende)

    auswertung = app._v2l_auswertung("fahrzeug-1")
    assert ende["v2l_active"] is False
    assert auswertung["zusammenfassung"]["anzahl"] == 1
    sitzung = auswertung["sitzungen"][0]
    assert sitzung["status"] == "completed"
    assert sitzung["methode"] == "Packleistung"
    assert sitzung["dauer_s"] == pytest.approx(70.0)
    assert sitzung["pack_energie_kwh"] == pytest.approx(
        2.0 * 70.0 / 3600.0,
        abs=1e-6,
    )
    assert sitzung["messabdeckung_prozent"] == pytest.approx(100.0)
    assert sitzung["spitze_kw"] == pytest.approx(2.0)


def test_v2l_faellt_bei_messluecke_auf_soc_zurueck():
    start_ms = 1_700_100_000_000
    app._v2l_telemetrie_aktualisieren(
        "fahrzeug-1",
        _v2l_daten(start_ms, soc=80.0),
    )
    app._v2l_telemetrie_aktualisieren(
        "fahrzeug-1",
        _v2l_daten(start_ms + 120_000, soc=79.5),
    )
    app._v2l_telemetrie_aktualisieren(
        "fahrzeug-1",
        _v2l_daten(
            start_ms + 180_000,
            soc=79.0,
            ladestatus="Disconnected",
        ),
    )

    sitzung = app._v2l_auswertung("fahrzeug-1")["sitzungen"][0]
    assert sitzung["methode"] == "SOC"
    assert sitzung["pack_energie_kwh"] == pytest.approx(0.0)
    assert sitzung["soc_energie_kwh"] == pytest.approx(0.716)
    assert sitzung["verbrauch_kwh"] == pytest.approx(0.716)
    assert sitzung["messabdeckung_prozent"] == pytest.approx(0.0)
    assert sitzung["messlücke_s"] == pytest.approx(180.0)


def test_unveraenderte_packwerte_werden_mit_neuem_zeitstempel_integriert(
    monkeypatch,
):
    start_ms = 1_700_200_000_000
    daten = _v2l_daten(start_ms)
    app._v2l_telemetrie_aktualisieren("fahrzeug-1", daten)
    monkeypatch.setattr(app, "latest_data", {"fahrzeug-1": daten})
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_ids",
        lambda _vin: ["fahrzeug-1"],
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_aktualisieren",
        lambda _cache_id, aktuelle_daten: aktuelle_daten,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_cache_spaeter_speichern",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_parkstatus_aufzeichnen",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        app,
        "_subscriber_daten_senden",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        app,
        "_aprs_spaeter_senden",
        lambda *_args, **_kwargs: None,
    )

    app._fleet_telemetrie_v_felder_aktualisieren(
        "TESTVIN",
        [
            ("PackCurrent", -5.0, start_ms + 10_000),
            ("PackVoltage", 400.0, start_ms + 10_000),
        ],
    )

    verbindung = app._v2l_datenbank_öffnen()
    try:
        zeile = app._v2l_aktive_sitzung_ungesperrt(
            verbindung,
            "fahrzeug-1",
        )
    finally:
        verbindung.close()
    sitzung = app._v2l_sitzung_payload(
        zeile,
        jetzt_ms=start_ms + 10_000,
    )
    assert sitzung["pack_energie_kwh"] == pytest.approx(
        2.0 * 10.0 / 3600.0,
        abs=1e-6,
    )
    assert sitzung["messabdeckung_prozent"] == pytest.approx(100.0)


def test_v2l_gesamtsumme_ist_unabhaengig_vom_anzeigelimit():
    verbindung = app._v2l_datenbank_öffnen()
    try:
        for nummer in range(2):
            start_ms = 1_700_300_000_000 + nummer * 100_000
            verbindung.execute(
                """
                INSERT INTO v2l_sessions (
                    vehicle_id, title, source, status, started_at_ms,
                    ended_at_ms, start_soc, end_soc,
                    battery_capacity_kwh, last_seen_at_ms, created_at_ms,
                    updated_at_ms
                ) VALUES (?, ?, 'reconstructed', 'completed', ?, ?, 80, 79,
                          71.6, ?, ?, ?)
                """,
                (
                    "fahrzeug-1",
                    f"Sitzung {nummer + 1}",
                    start_ms,
                    start_ms + 60_000,
                    start_ms + 60_000,
                    start_ms,
                    start_ms + 60_000,
                ),
            )
        verbindung.commit()
    finally:
        verbindung.close()

    auswertung = app._v2l_auswertung("fahrzeug-1", limit=1)

    assert len(auswertung["sitzungen"]) == 1
    assert auswertung["zusammenfassung"]["anzahl"] == 2
    assert auswertung["zusammenfassung"]["verbrauch_kwh"] == pytest.approx(
        1.432
    )


def test_v2l_seite_start_stop_api_und_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(app, "_config_cache", {})
    monkeypatch.setattr(app, "_config_mtime", {})
    monkeypatch.setattr(app, "_default_vehicle_id", "fahrzeug-1")
    monkeypatch.setattr(
        app,
        "latest_data",
        {"fahrzeug-1": _v2l_daten(int(time.time() * 1000), soc=78.5)},
    )
    angeforderte_profile = []

    def profil_aktualisieren(_vehicle_id, daten):
        angeforderte_profile.append(app._fleet_telemetrie_profile_ziel(daten))
        return daten

    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_aktualisieren",
        profil_aktualisieren,
    )
    monkeypatch.setattr(
        app,
        "_fleet_telemetrie_profile_spaeter_anwenden",
        angeforderte_profile.append,
    )
    vorheriger_csrf_status = app.app.config.get("WTF_CSRF_ENABLED", True)
    app.app.config["WTF_CSRF_ENABLED"] = False
    client = app.app.test_client()
    try:
        seite = client.get("/v2l")
        assert seite.status_code == 200
        assert "V2L-Statistik" in seite.get_data(as_text=True)
        assert "/static/js/v2l.js" in seite.get_data(as_text=True)
        assert "© 2025-2026 Erik Schauer" in seite.get_data(as_text=True)
        assert seite.headers["X-Robots-Tag"] == "noindex, nofollow"
        assert 'content="noindex, nofollow"' in seite.get_data(as_text=True)

        start = client.post(
            "/api/v2l/start",
            json={
                "vehicle_id": "fahrzeug-1",
                "titel": "Werkstatt",
                "kapazität_kwh": 72.0,
            },
        )
        assert start.status_code == 201
        assert start.get_json()["sitzung"]["titel"] == "Werkstatt"
        assert angeforderte_profile[-1] == "live"

        live = client.get(
            "/api/v2l?vehicle_id=fahrzeug-1",
        )
        assert live.status_code == 200
        assert live.get_json()["aktiv"]["titel"] == "Werkstatt"
        assert live.get_json()["kapazität_kwh"] == pytest.approx(72.0)

        ungueltige_id = client.get("/api/v2l?vehicle_id=../../etc")
        assert ungueltige_id.status_code == 400
        unbekannte_id = client.get("/api/v2l?vehicle_id=fremdes-fahrzeug")
        assert unbekannte_id.status_code == 404
        ungueltiges_limit = client.get("/api/v2l?limit=ungueltig")
        assert ungueltiges_limit.status_code == 200

        stopp = client.post(
            "/api/v2l/stop",
            json={"vehicle_id": "fahrzeug-1"},
        )
        assert stopp.status_code == 200
        assert stopp.get_json()["sitzung"]["status"] == "completed"

        export = client.get(
            "/v2l/export.csv?vehicle_id=fahrzeug-1",
        )
        csv_text = export.get_data(as_text=True)
        assert export.status_code == 200
        assert "Verbrauch kWh" in csv_text
        assert "Werkstatt" in csv_text
        assert "Packmessung kWh" in csv_text
    finally:
        app.app.config["WTF_CSRF_ENABLED"] = vorheriger_csrf_status
