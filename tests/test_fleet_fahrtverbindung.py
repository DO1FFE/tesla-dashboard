"""Fahrgebundene Verbindungsreparatur. © 2026 Erik Schauer, do1ffe@darc.de."""

import pathlib
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


@pytest.fixture
def fahrtverbindung(monkeypatch):
    zeit = {"wand": 2_000_000_000.0, "monoton": 100.0}
    daten = {
        "drive_state": {"shift_state": "D", "speed": 20},
        "fleet_telemetry_field_received_at": {
            "VehicleSpeed": zeit["wand"] * 1000 - 500,
        },
    }
    status = {
        "current": "parked", "target": "live",
        "live_retry_active": True, "config_synced": False,
    }
    antwort = app.requests.Response()
    antwort.status_code = 408
    fehler = app.requests.exceptions.HTTPError(response=antwort)
    zustand = Mock(return_value="asleep")
    post = Mock()
    monkeypatch.setattr(app.time, "time", lambda: zeit["wand"])
    monkeypatch.setattr(app.time, "monotonic", lambda: zeit["monoton"])
    monkeypatch.setattr(app, "_fleet_telemetry_fahrtverbindung_letzte_prüfung", {})
    monkeypatch.setattr(
        app, "_fleet_telemetrie_position_snapshot", lambda _vin: daten,
    )
    monkeypatch.setattr(
        app, "_fleet_telemetrie_profile_status_kopie", lambda: status.copy(),
    )
    monkeypatch.setattr(app, "_fleet_telemetrie_fahrzeugzustand_abrufen", zustand)
    monkeypatch.setattr(app, "_fleet_telemetrie_oauth_token", lambda: "testtoken")
    monkeypatch.setattr(app.requests, "post", post)
    return daten, status, zeit, fehler, zustand, post


@pytest.mark.parametrize("gang", ["D", "R"])
def test_fahrtverbindung_repariert_asleep_ohne_profilbestätigung(
    fahrtverbindung, gang,
):
    daten, status, _, fehler, zustand, post = fahrtverbindung
    daten["drive_state"]["shift_state"] = gang
    assert app._fleet_telemetrie_fahrtverbindung_nach_timeout("TESTVIN", fehler)
    zustand.assert_called_once_with("TESTVIN")
    post.assert_called_once()
    assert post.call_args.args[0].endswith("/api/1/vehicles/TESTVIN/wake_up")
    assert post.call_args.kwargs["headers"] == {
        "Authorization": "Bearer testtoken",
    }
    assert status["current"] == "parked"
    assert status["config_synced"] is False


@pytest.mark.parametrize("grund", [
    "parken", "stillstand", "gang_unbekannt", "neutral", "alt", "zukunft",
    "nur_rest", "kein_live", "keine_reparatur", "bestätigt",
])
def test_fahrtverbindung_weckt_nicht_ohne_aktuellen_fahrnachweis(
    fahrtverbindung, grund,
):
    daten, status, zeit, fehler, zustand, post = fahrtverbindung
    if grund in {"parken", "gang_unbekannt", "neutral"}:
        daten["drive_state"]["shift_state"] = {
            "parken": "P", "gang_unbekannt": None, "neutral": "N",
        }[grund]
    elif grund == "stillstand":
        daten["drive_state"]["speed"] = 0
    elif grund in {"alt", "zukunft", "nur_rest"}:
        daten["fleet_telemetry_field_received_at"]["VehicleSpeed"] = {
            "alt": (zeit["wand"] - 16) * 1000,
            "zukunft": (zeit["wand"] + 1) * 1000,
            "nur_rest": None,
        }[grund]
        daten["fleet_vehicle_data_received_at"] = zeit["wand"] * 1000
    else:
        status.update({
            "kein_live": {"target": "charging"},
            "keine_reparatur": {"live_retry_active": False},
            "bestätigt": {"config_synced": True},
        }[grund])
    assert not app._fleet_telemetrie_fahrtverbindung_nach_timeout("TESTVIN", fehler)
    zustand.assert_not_called()
    post.assert_not_called()


@pytest.mark.parametrize("zustand", ["online", "offline", "unknown", None])
def test_fahrtverbindung_weckt_nur_bei_asleep(fahrtverbindung, zustand):
    _, _, _, fehler, abfrage, post = fahrtverbindung
    abfrage.return_value = zustand
    assert not app._fleet_telemetrie_fahrtverbindung_nach_timeout("TESTVIN", fehler)
    post.assert_not_called()


@pytest.mark.parametrize("änderung", ["parken", "stillstand", "alt", "bestätigt"])
def test_fahrtverbindung_prüft_fahrt_nach_statusabfrage_erneut(
    fahrtverbindung, änderung,
):
    daten, status, zeit, fehler, zustand, post = fahrtverbindung

    def inzwischen_geändert(_vin):
        if änderung == "parken":
            daten["drive_state"]["shift_state"] = "P"
        elif änderung == "stillstand":
            daten["drive_state"]["speed"] = 0
        elif änderung == "alt":
            zeit["wand"] += 20
        else:
            status["config_synced"] = True
        return "asleep"

    zustand.side_effect = inzwischen_geändert
    assert not app._fleet_telemetrie_fahrtverbindung_nach_timeout("TESTVIN", fehler)
    post.assert_not_called()


@pytest.mark.parametrize("fehler", [
    app.requests.exceptions.Timeout(),
    app.requests.exceptions.HTTPError(),
    RuntimeError("Keine Fahrzeugdaten"),
])
def test_fahrtverbindung_ignoriert_fehler_ohne_http_408(fahrtverbindung, fehler):
    _, _, _, _, zustand, post = fahrtverbindung
    assert not app._fleet_telemetrie_fahrtverbindung_nach_timeout("TESTVIN", fehler)
    zustand.assert_not_called()
    post.assert_not_called()


@pytest.mark.parametrize("phase", ["status", "token", "wake"])
def test_fahrtverbindung_begrenzt_auch_fehlgeschlagene_versuche(
    fahrtverbindung, monkeypatch, phase,
):
    _, _, _, fehler, zustand, post = fahrtverbindung
    if phase == "status":
        zustand.side_effect = app.requests.exceptions.Timeout()
    elif phase == "token":
        monkeypatch.setattr(app, "_fleet_telemetrie_oauth_token", lambda: None)
    else:
        post.side_effect = app.requests.exceptions.Timeout()
    for _ in range(2):
        assert not app._fleet_telemetrie_fahrtverbindung_nach_timeout(
            "TESTVIN", fehler,
        )
    assert zustand.call_count == 1
    assert post.call_count == (1 if phase == "wake" else 0)


def test_fahrtverbindung_hat_fünf_minuten_sperrfrist(fahrtverbindung):
    daten, _, zeit, fehler, zustand, post = fahrtverbindung
    assert app._fleet_telemetrie_fahrtverbindung_nach_timeout("TESTVIN", fehler)
    for abstand in (1, 299, 300):
        zeit["monoton"] = 100 + abstand
        zeit["wand"] = 2_000_000_000 + abstand
        daten["fleet_telemetry_field_received_at"]["VehicleSpeed"] = (
            zeit["wand"] * 1000
        )
        assert app._fleet_telemetrie_fahrtverbindung_nach_timeout(
            "TESTVIN", fehler,
        ) is (abstand == 300)
    assert zustand.call_count == post.call_count == 2


@pytest.mark.parametrize("http_status", [408, 401, 429, 500])
def test_positionswächter_repariert_nur_http_408(
    fahrtverbindung, monkeypatch, http_status,
):
    _, _, _, fehler, zustand, post = fahrtverbindung
    fehler.response.status_code = http_status
    aktiv = iter([True, False])
    monkeypatch.setattr(app, "_fleet_telemetrie_aktiv", lambda: next(aktiv))
    monkeypatch.setattr(
        app, "_fleet_telemetrie_fahrzeuge", lambda: [{"vin": "TESTVIN"}],
    )
    for name in (
        "_fleet_telemetrie_streamprofil_wiederherstellung_anfordern",
        "_fleet_telemetrie_stream_wiederherstellung_soll_aktualisiert_werden",
        "_fleet_telemetrie_parkabgleich_soll_aktualisiert_werden",
        "_fleet_telemetrie_ladeabgleich_soll_aktualisiert_werden",
    ):
        monkeypatch.setattr(app, name, lambda _data: False)
    monkeypatch.setattr(
        app, "_fleet_telemetrie_position_soll_aktualisiert_werden", lambda _d: True,
    )
    monkeypatch.setattr(
        app, "_fleet_telemetrie_position_abfrage_reservieren", lambda _v: True,
    )
    monkeypatch.setattr(
        app, "_fleet_telemetrie_position_abrufen", Mock(side_effect=fehler),
    )
    monkeypatch.setattr(app.time, "sleep", lambda _pause: None)
    app._fleet_telemetrie_position_worker_loop()
    assert zustand.call_count == post.call_count == (1 if http_status == 408 else 0)
