"""Offline-Tests der befristeten Überwachung und ihrer Mailwarteschlange."""

from email import policy
from email.parser import BytesParser
import json
from pathlib import Path
import shlex
from types import SimpleNamespace
from unittest.mock import Mock
import subprocess

import pytest

from tools import telemetrie_passivmail as mail
from tools import telemetrie_passivpruefung as prüfung


JETZT = prüfung.auswertung.zeitwert("2026-10-23T14:00:00Z")


def dienste():
    return {name: {"ActiveState": "active", "SubState": "running", "NRestarts": "0"}
            for name in prüfung.DIENSTE}


def cache(gang="D", tempo=30):
    return {"state": "online", "fleet_telemetry_received_at": JETZT * 1000,
            "drive_state": {"shift_state": gang, "speed": tempo},
            "fleet_telemetry_field_received_at": {"VehicleSpeed": JETZT * 1000}}


def profil(name="live"):
    return {"current": name, "target": name, "config_synced": True,
            "config_sync_profile": name, "target_since": JETZT - 600}


@pytest.mark.parametrize("name", ["live", "live_extended"])
def test_normale_fahrt_und_ampel_ohne_alarm(name):
    assert not prüfung.momentbefunde(cache(), profil(name), dienste(), JETZT)
    assert not prüfung.momentbefunde(cache(tempo=0), profil(name), dienste(), JETZT)


def test_bestätigtes_live_plus_passt_zum_übergeordneten_ziel_live():
    status = profil("live_extended")
    status["target"] = "live"
    assert not prüfung.momentbefunde(cache(), status, dienste(), JETZT)


@pytest.mark.parametrize("anpassung", [
    {"config_synced": False},
    {"config_sync_profile": "live"},
    {"target": "charging"},
    {"current": "live", "target": "live_extended", "config_sync_profile": "live"},
    {"current": None, "target": None, "config_sync_profile": None},
])
def test_unpassende_live_plus_bestätigung_bleibt_ein_befund(anpassung):
    status = profil("live_extended")
    status["target"] = "live"
    status.update(anpassung)
    assert "profilbestätigung" in prüfung.momentbefunde(cache(), status, dienste(), JETZT)


def test_schlaf_ist_keine_störung():
    daten = cache()
    daten["state"] = "offline"
    daten["fleet_telemetry_received_at"] -= 3600000
    daten["fleet_telemetry_field_received_at"]["VehicleSpeed"] -= 3600000
    assert not prüfung.momentbefunde(daten, profil("parked"), dienste(), JETZT)


def test_fahrt_nach_laden_und_profilbestätigung():
    status = profil("charging")
    status.update(target="live", config_synced=False)
    befunde = prüfung.momentbefunde(cache(), status, dienste(), JETZT)
    assert "fahrprofil" in befunde and "profilbestätigung" in befunde
    status["target_since"] = JETZT - 60
    assert "profilbestätigung" not in prüfung.momentbefunde(cache(), status, dienste(), JETZT)


def test_fehlende_navigation_und_zielkoordinaten():
    daten = cache()
    daten["drive_state"]["active_route_active"] = True
    befunde = prüfung.momentbefunde(daten, profil(), dienste(), JETZT)
    assert {"routeline", "navigationsziel"} <= befunde.keys()
    daten["drive_state"].update(active_route_line="kodierte Linie", active_route_latitude=51,
                               active_route_longitude=7)
    assert not prüfung.momentbefunde(daten, profil(), dienste(), JETZT)
    daten["drive_state"].update(active_route_active=False, active_route_line=None)
    assert not prüfung.momentbefunde(daten, profil(), dienste(), JETZT)


def test_fenster_und_türen_nur_bei_frischer_eindeutiger_rohmeldung():
    daten = cache()
    daten["fleet_telemetry_raw"] = {"DoorState": {"DriverFront": False}, "FpWindow": "WindowStateClosed"}
    daten["vehicle_state"] = {"df": 1, "fp_window": 1}
    assert not prüfung.momentbefunde(daten, profil(), dienste(), JETZT)
    daten["fleet_telemetry_field_received_at"].update(DoorState=JETZT * 1000, FpWindow=JETZT * 1000)
    assert {"tür:df", "fenster:fp_window"} <= prüfung.momentbefunde(daten, profil(), dienste(), JETZT).keys()


@pytest.mark.parametrize("wert", [None, False, float("nan"), float("inf"), JETZT * 1000 + 1])
def test_ungültige_zeitstempel_nicht_frisch(wert):
    assert not prüfung.frisch(wert, JETZT, 30)


def test_hysterese_deduplizierung_und_wiederauftreten():
    zustand = {}
    kandidaten = {"route": ("Route fehlt", 120)}
    assert not prüfung.befunde_fortschreiben(zustand, kandidaten, 100)
    assert not prüfung.befunde_fortschreiben(zustand, kandidaten, 219)
    assert prüfung.befunde_fortschreiben(zustand, kandidaten, 220)[0]["status"] == "neu"
    assert not prüfung.befunde_fortschreiben(zustand, kandidaten, 400)
    assert prüfung.befunde_fortschreiben(zustand, {}, 500)[0]["status"] == "nicht_mehr_beobachtet"
    assert not prüfung.befunde_fortschreiben(zustand, kandidaten, 600)
    assert prüfung.befunde_fortschreiben(zustand, kandidaten, 720)[0]["status"] == "neu"
    assert zustand["befunde"]["route"]["anzahl"] == 2


@pytest.mark.parametrize("name", ["live", "live_extended"])
def test_sekundentakt_und_zehnsekundentakt(name):
    def daten(schritt):
        return {"takt": prüfung.auswertung.takt_auswerten(
            [(100, 300, name)], {feld: list(range(100, 300, schritt))
                                  for feld in prüfung.auswertung.FAHRFELDER}),
            "fahrtstunden_ohne_liveprofil": 0}
    assert not prüfung.takt_befunde(daten(1))
    assert f"takt:{name}:Location" in prüfung.takt_befunde(daten(10))


def test_komplett_fehlende_meldungen_bei_bewegung_werden_erfasst():
    daten = {"takt": prüfung.auswertung.takt_auswerten([(100, 300, "live")], {}),
             "fahrtstunden_ohne_liveprofil": 0}
    assert "takt:live:Location" in prüfung.takt_befunde(daten)
    for wert in daten["takt"].values():
        wert["bewertung"] = "nicht beurteilbar: mehrere Fahrzeuge"
    assert not prüfung.takt_befunde(daten)


def vorbereiten(tmp_path, monkeypatch):
    args = SimpleNamespace(projekt=tmp_path / "projekt", ausgabe=tmp_path / "berichte",
                           referenz=tmp_path / "referenz.json", start=JETZT - 600,
                           ende=JETZT + 600)
    for name, daten in (("data/default/cache.json", cache()),
                         ("data/tesla_fleet/telemetry_profile_status.json", profil())):
        pfad = args.projekt / name
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(json.dumps(daten))
    (args.projekt / "data/monitoring").mkdir()
    (args.projekt / "data/monitoring/fahrtstatus.ndjson").touch()
    (args.ausgabe / "postausgang").mkdir(parents=True)
    daten = {"takt": prüfung.auswertung.takt_auswerten([], {}),
             "fahrtstunden_ohne_liveprofil": 0, "quellen": {"lesefehler": []},
             "journal": {"verfügbar": True}, "warnungen": []}
    monkeypatch.setattr(prüfung.auswertung, "auswerten", Mock(return_value=daten))
    monkeypatch.setattr(prüfung, "dienststatus", dienste)
    monkeypatch.setattr(prüfung, "journalfehler", lambda *a: {})
    return args


def test_normale_schritte_senden_keine_statusmails(tmp_path, monkeypatch):
    args = vorbereiten(tmp_path, monkeypatch)
    assert not prüfung.prüfschritt(args, JETZT)
    assert not list((args.ausgabe / "postausgang").glob("*.json"))
    assert not (args.ausgabe / "abschluss.json").exists()
    status = json.loads((args.ausgabe / "status.json").read_text())
    assert status["zusätzliche_fahrzeugabfragen"] == 0


def test_fehler_nur_lokal_keine_sofortmail(tmp_path, monkeypatch):
    args = vorbereiten(tmp_path, monkeypatch)
    monkeypatch.setattr(prüfung, "journalfehler", lambda *a: {"Python-Ausnahme": 2})
    prüfung.prüfschritt(args, JETZT)
    prüfung.prüfschritt(args, JETZT + 60)
    mails = list((args.ausgabe / "postausgang").glob("*.json"))
    assert not mails
    auftrag = next((args.ausgabe / "korrekturaufträge").glob("*.json")).read_text()
    assert "Python-Ausnahme" in auftrag
    assert "latitude" not in auftrag


def test_abschluss_nur_nach_ende_und_nicht_wiederholt(tmp_path, monkeypatch):
    args = vorbereiten(tmp_path, monkeypatch)
    args.ende = args.start + 48 * 3600
    assert prüfung.prüfschritt(args, args.ende + 10)
    assert (args.ausgabe / "abschluss.json").exists()
    prüfung.auswertung.auswerten.assert_called_once_with(
        args.projekt / "data/monitoring", args.start, args.ende,
    )
    nachricht = json.loads(next((args.ausgabe / "postausgang").glob("*.json")).read_text())
    assert "Tagesbericht 2/2" in nachricht["betreff"]
    monkeypatch.setattr("sys.argv", ["prüfung", "--projekt", str(args.projekt),
                        "--ausgabe", str(args.ausgabe), "--referenz", str(args.referenz),
                        "--start", prüfung.auswertung.zeittext(args.start),
                        "--ende", prüfung.auswertung.zeittext(args.ende)])
    prüfung.main()
    assert prüfung.auswertung.auswerten.call_count == 1


def test_höchstens_ein_bericht_pro_24_stunden(tmp_path, monkeypatch):
    args = vorbereiten(tmp_path, monkeypatch)
    args.ende = args.start + 48 * 3600
    prüfung.prüfschritt(args, args.start + 23 * 3600)
    assert not list((args.ausgabe / "postausgang").glob("*.json"))
    prüfung.prüfschritt(args, args.start + 24 * 3600)
    assert len(list((args.ausgabe / "postausgang").glob("*.json"))) == 1
    prüfung.prüfschritt(args, args.start + 25 * 3600)
    assert len(list((args.ausgabe / "postausgang").glob("*.json"))) == 1
    prüfung.prüfschritt(args, args.ende)
    assert len(list((args.ausgabe / "postausgang").glob("*.json"))) == 2


def test_tagesvergleich_meldet_keine_historischen_journalfehler_erneut(
    tmp_path, monkeypatch,
):
    args = vorbereiten(tmp_path, monkeypatch)
    args.start = JETZT - 86400
    args.ende = args.start + 48 * 3600
    journal = Mock(return_value={})
    monkeypatch.setattr(prüfung, "journalfehler", journal)
    prüfung.prüfschritt(args, JETZT)
    journal.assert_called_once_with(JETZT - 600, JETZT)
    prüfung.auswertung.auswerten.assert_called_once_with(
        args.projekt / "data/monitoring", args.start, JETZT,
    )


def test_bericht_trennt_aktuellen_takt_vom_älteren_kostenzeitraum(
    tmp_path, monkeypatch,
):
    args = vorbereiten(tmp_path, monkeypatch)
    args.start = JETZT - 86400
    args.ende = args.start + 48 * 3600
    args.referenz.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(prüfung.auswertung, "vergleichen", lambda *a: {
        "heizungsersparnis_modell_euro_pro_30_tage": 2.5,
        "streamdifferenz_profilbereinigt_euro_pro_30_tage": 3.7,
        "einschränkung": "Modellrechnung",
    })
    prüfung.prüfschritt(args, JETZT)
    prüfung.prüfschritt(args, JETZT + 3600)
    status = json.loads((args.ausgabe / "status.json").read_text())
    assert status["vergleichszeitraum"] == {
        "von": prüfung.auswertung.zeittext(args.start),
        "bis": prüfung.auswertung.zeittext(JETZT),
    }
    assert status["auswertungszeitraum"] == {
        "von": prüfung.auswertung.zeittext(JETZT + 3000),
        "bis": prüfung.auswertung.zeittext(JETZT + 3600),
    }
    text = prüfung.berichttext(status)
    assert sum(zeile.startswith("Zeitraum:") for zeile in text.splitlines()) == 2
    del status["vergleichszeitraum"]
    assert "kein aktueller Gesamtvergleich" in prüfung.berichttext(status)


def test_bestätigtes_live_plus_erzeugt_keine_korrekturaufträge(tmp_path, monkeypatch):
    args = vorbereiten(tmp_path, monkeypatch)
    status = profil("live_extended")
    status["target"] = "live"
    (args.projekt / "data/tesla_fleet/telemetry_profile_status.json").write_text(
        json.dumps(status), encoding="utf-8",
    )
    for jetzt in (JETZT, JETZT + 60, JETZT + 120):
        daten = cache()
        daten["fleet_telemetry_received_at"] = jetzt * 1000
        daten["fleet_telemetry_field_received_at"]["VehicleSpeed"] = jetzt * 1000
        (args.projekt / "data/default/cache.json").write_text(
            json.dumps(daten), encoding="utf-8",
        )
        prüfung.prüfschritt(args, jetzt)
    assert not list((args.ausgabe / "korrekturaufträge").glob("*.json"))


def test_cachefehler_wird_als_befund_gemeldet(tmp_path, monkeypatch):
    args = vorbereiten(tmp_path, monkeypatch)
    (args.projekt / "data/default/cache.json").write_text('{"drive_state": [1]}')
    prüfung.prüfschritt(args, JETZT)
    status = json.loads((args.ausgabe / "status.json").read_text())
    assert status["befunde"]["statuszugriff"]["aktiv"]


def test_journal_zählt_ohne_geheimnisse_zu_übernehmen(monkeypatch):
    lauf = Mock(return_value=Mock(stdout=json.dumps(
        {"MESSAGE": "ERROR token=geheim", "PRIORITY": "3"}) + "\n"))
    monkeypatch.setattr(prüfung.subprocess, "run", lauf)
    ergebnis = prüfung.journalfehler(JETZT - 60, JETZT)
    assert ergebnis == {"Fehlermeldung": 1, "Journal-Priorität Fehler": 1}
    assert lauf.call_args.args[0][0] == "/usr/bin/journalctl"
    assert "geheim" not in str(ergebnis)


def mail_vorbereiten(tmp_path):
    (tmp_path / "postausgang").mkdir()
    pfad = tmp_path / "postausgang/test.json"
    pfad.write_text(json.dumps({"betreff": "Befund", "text": "Prüfbericht mit Umlauten äöüß.",
                               "daten": {"zusätzliche_fahrzeugabfragen": 0}}))
    return pfad


def test_mail_fester_empfänger_anhänge_und_kein_doppelversand(tmp_path, monkeypatch):
    pfad = mail_vorbereiten(tmp_path)
    lauf = Mock()
    monkeypatch.setattr(mail.subprocess, "run", lauf)
    mail.versenden(tmp_path)
    mail.versenden(tmp_path)
    lauf.assert_called_once()
    assert lauf.call_args.args[0] == ["/usr/sbin/sendmail", "-i", "-f", "no-reply@do1ffe.de", "do1ffe@darc.de"]
    nachricht = BytesParser(policy=policy.default).parsebytes(lauf.call_args.kwargs["input"])
    assert nachricht["To"] == "do1ffe@darc.de"
    assert "äöüß" in nachricht.get_body(preferencelist=("plain",)).get_content()
    assert {a.get_filename() for a in nachricht.iter_attachments()} == {"bericht.txt", "bericht.json"}
    assert not pfad.exists() and (tmp_path / "versendet/test.json").exists()


def test_mailfehler_auf_drei_versuche_begrenzt(tmp_path, monkeypatch):
    pfad = mail_vorbereiten(tmp_path)
    lauf = Mock(side_effect=subprocess.CalledProcessError(1, "sendmail"))
    monkeypatch.setattr(mail.subprocess, "run", lauf)
    for _ in range(3):
        with pytest.raises(subprocess.CalledProcessError):
            mail.versenden(tmp_path)
        assert pfad.exists()
    mail.versenden(tmp_path)
    mail.versenden(tmp_path)
    assert lauf.call_count == 3
    assert not pfad.exists() and (tmp_path / "mail-fehlgeschlagen/test.json").exists()


def test_unbekannter_mailstatus_wird_nicht_blind_wiederholt(tmp_path, monkeypatch):
    mail_vorbereiten(tmp_path)
    lauf = Mock(side_effect=subprocess.TimeoutExpired("sendmail", 90))
    monkeypatch.setattr(mail.subprocess, "run", lauf)
    mail.versenden(tmp_path)
    mail.versenden(tmp_path)
    lauf.assert_called_once()
    assert (tmp_path / "mail-fehlgeschlagen/test.json").exists()


def test_beschädigte_maildatei_verursacht_keine_endlosschleife(tmp_path, monkeypatch):
    pfad = mail_vorbereiten(tmp_path)
    pfad.write_text("kaputt")
    lauf = Mock()
    monkeypatch.setattr(mail.subprocess, "run", lauf)
    for _ in range(3):
        with pytest.raises(ValueError):
            mail.versenden(tmp_path)
    mail.versenden(tmp_path)
    lauf.assert_not_called()
    assert (tmp_path / "mail-fehlgeschlagen/test.json").exists()


def test_dienste_trennen_netzwerk_und_prüfung_und_laufen_genau_48_stunden():
    basis = Path(__file__).resolve().parents[1] / "systemd"
    dienst = (basis / "tesla-dashboard-passivpruefung.service").read_text()
    maildienst = (basis / "tesla-dashboard-passivmail.service").read_text()
    for schutz in ("PrivateNetwork=true", "RestrictAddressFamilies=AF_UNIX",
                   "IPAddressDeny=any", "ProtectSystem=strict", "ProtectHome=read-only"):
        assert schutz in dienst
    assert "IPAddressAllow=127.0.0.1/32" in maildienst
    kommando = shlex.split(next(z.split("=", 1)[1] for z in dienst.splitlines()
                              if z.startswith("ExecStart=")))
    start = prüfung.auswertung.zeitwert(kommando[kommando.index("--start") + 1])
    ende = prüfung.auswertung.zeitwert(kommando[kommando.index("--ende") + 1])
    assert ende - start == 48 * 3600
    assert "restart tesla-dashboard" not in dienst


# © 2026 Erik Schauer, do1ffe@darc.de
