"""Offline-Prüfungen für den einmaligen Auswertungsjob."""

from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shlex
from unittest.mock import Mock

import pytest

from tools import telemetrie_wochenpruefung as prüfung


START = prüfung.zeitwert("2026-10-23T00:00:00Z")


def cache(zeit, gang="D", tempo=20):
    return (zeit, 1, ("online", gang, tempo, zeit, zeit))


@pytest.mark.parametrize("profil", ["live", "live_extended"])
def test_takt_eine_sekunde_wird_getrennt_bestätigt(profil):
    felder = {feld: list(range(100, 160)) for feld in prüfung.FAHRFELDER}
    daten = prüfung.takt_auswerten([(100, 160, profil)], felder)
    assert daten[profil]["bewertung"].startswith("Sekundentakt")
    for wert in daten[profil]["felder"].values():
        assert wert["median_s"] == 1
        assert wert["p95_s"] == 1
        assert wert["frischeabdeckung_prozent"] == 100


@pytest.mark.parametrize("profil", ["live", "live_extended"])
def test_zehnsekundentakt_wird_nicht_als_erfolg_gemeldet(profil):
    felder = {feld: list(range(100, 300, 10)) for feld in prüfung.FAHRFELDER}
    daten = prüfung.takt_auswerten([(100, 300, profil)], felder)[profil]
    assert daten["bewertung"].startswith("Auffälligkeiten")
    assert daten["felder"]["Location"]["median_s"] == 10
    assert daten["felder"]["Location"]["lücken_ab_8_s"] == 20


def test_lücke_am_fahrtende_wird_nicht_übersehen():
    felder = {feld: list(range(100, 130)) for feld in prüfung.FAHRFELDER}
    daten = prüfung.takt_auswerten([(100, 180, "live")], felder)["live"]
    assert daten["bewertung"].startswith("Auffälligkeiten")
    assert daten["felder"]["Location"]["größte_lücken"][0]["dauer_s"] == 51


def test_fehlende_fahrten_oder_felder_sind_keine_bestätigung():
    assert prüfung.takt_auswerten([], {})["live"]["bewertung"].startswith("nicht beurteilbar")
    daten = prüfung.takt_auswerten([(100, 200, "live")], {})["live"]
    assert daten["bewertung"].startswith("nicht beurteilbar")
    assert daten["felder"]["Location"]["größte_lücken"][0]["dauer_s"] == 100


def test_ampel_und_profilwechsel_erzeugen_keine_falschen_empfangslücken():
    ereignisse = [
        (100, 0, "live"), cache(100), cache(110, tempo=0),
        (280, 0, "live_extended"), cache(290), cache(300, gang="P", tempo=0),
    ]
    fahrten, _, _, _ = prüfung.nutzungsfenster(ereignisse, 100, 310)
    assert fahrten == [(100, 110, "live"), (290, 300, "live_extended")]
    felder = {f: [*range(100, 110), *range(290, 300)] for f in prüfung.FAHRFELDER}
    takt = prüfung.takt_auswerten(fahrten, felder)
    assert not takt["live"]["felder"]["Location"]["lücken_über_5_s"]
    assert not takt["live_extended"]["felder"]["Location"]["lücken_über_5_s"]


def test_heizungsmodell_nur_frische_belegte_nutzung():
    ereignisse = [(100, 0, "live"), cache(100), cache(120, "P", 0),
                  (120, 2, True), cache(140, "P", 0), (145, 2, False)]
    _, heizung, _, _ = prüfung.nutzungsfenster(ereignisse, 100, 180)
    assert heizung == [(100, 115, "heizung"), (120, 145, "heizung")]
    assert prüfung.modellabrufe(heizung, 60) == 1
    assert prüfung.modellabrufe(heizung, 30) == 2


def test_lange_cachelücke_wird_ausgewiesen():
    fahrten, _, _, lücke = prüfung.nutzungsfenster(
        [(100, 0, "live"), cache(100)], 100, 1000,
    )
    assert fahrten == [(100, 400, "live")]
    assert lücke == 600


def test_logrotation_nullwerte_und_bericht_ohne_rohpositionen(tmp_path, monkeypatch):
    monkeypatch.setattr(prüfung, "journal_auswerten", lambda *a: {"verfügbar": False})
    protokoll = []
    for i in range(60):
        zeit = START + i
        iso = datetime.fromtimestamp(zeit, timezone.utc).isoformat()
        if i == 0:
            protokoll.append({"quelle": "profil", "beobachtet_am_utc": iso, "current": "live"})
        protokoll.append({
            "quelle": "cache", "beobachtet_am_utc": iso, "state": "online",
            "drive": {"shift_state": "D", "speed": 20, "latitude": 51.123456789},
            "telemetrie_empfangen_am": zeit * 1000,
            "feld_empfangen_am": {"VehicleSpeed": zeit * 1000},
        })
    (tmp_path / "fahrtstatus.ndjson").write_text(
        "\n".join(json.dumps(d) for d in protokoll) + "\nkaputt\n", encoding="utf-8",
    )
    mqtt = [f'{START+i}\ttesla/TESTVIN/v/{feld}\t1\n'
            for i in range(60) for feld in prüfung.FAHRFELDER]
    mqtt += [f'{START+1}\ttesla/TESTVIN/v/TpmsPressureFl\tnull\n',
             f'{START+2}\ttesla/TESTVIN/v/TpmsPressureFl\t2.8\n',
             f'{START+3}\ttesla/TESTVIN/v/TpmsPressureFl\t2.8\n']
    with gzip.open(tmp_path / "fleet-mqtt.tsv-20261024.gz", "wt") as datei:
        datei.writelines(mqtt)
    daten = prüfung.auswerten(tmp_path, START, START + 60)
    assert daten["takt"]["live"]["bewertung"].startswith("Sekundentakt")
    assert daten["gültige_signale"] == {"live": 242}
    assert daten["ungültige_signale"] == {"live": 1}
    assert daten["tpms_unveränderte_gültige_signale"] == {"live": 1}
    assert daten["quellen"]["ungültige_zeilen"] == 1
    assert len(daten["quellen"]["dateien"]) == 2
    ausgabe = prüfung.berichttext(daten, daten, prüfung.vergleichen(daten, daten))
    assert "TESTVIN" not in ausgabe
    assert "51.123456789" not in ausgabe
    assert "kein Rechnungsnachweis" in ausgabe


def test_fehlende_logs_bestätigen_keine_ersparnis(tmp_path, monkeypatch):
    monkeypatch.setattr(prüfung, "journal_auswerten", lambda *a: {"verfügbar": False})
    daten = prüfung.auswerten(tmp_path, START, START + 3600)
    vergleich = prüfung.vergleichen(daten, daten)
    assert vergleich["heizungsersparnis_modell_euro_pro_30_tage"] is None
    assert vergleich["heizung_schätzung_7_bis_9_euro_erreicht"] is None
    assert vergleich["abrechnungsgenau_belegt"] is False
    assert "nicht beurteilbar" in prüfung.berichttext(daten, daten, vergleich)


def test_journal_ist_einziger_subprozess_und_nur_lesend(monkeypatch):
    aufruf = Mock(return_value=Mock(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(prüfung.subprocess, "run", aufruf)
    assert prüfung.journal_auswerten(START, START + 60)["verfügbar"]
    kommando = aufruf.call_args.args[0]
    assert kommando[:3] == ["/usr/bin/journalctl", "-u", "tesla-dashboard.service"]
    assert "--since" in kommando and "--until" in kommando
    assert "--grep" not in kommando


def test_zukünftiger_prüfzeitraum_erzeugt_keinen_abschluss(tmp_path, monkeypatch):
    aufruf = Mock()
    monkeypatch.setattr(prüfung, "auswerten", aufruf)
    monkeypatch.setattr("sys.argv", [
        "prüfung", "--logs", str(tmp_path), "--ausgabe", str(tmp_path),
        "--start", "2099-01-01T00:00:00Z", "--ende", "2099-01-02T00:00:00Z",
    ])
    with pytest.raises(SystemExit) as abbruch:
        prüfung.main()
    assert abbruch.value.code == 2
    aufruf.assert_not_called()
    assert not (tmp_path / "bericht.json").exists()
    assert not (tmp_path / "referenz.json").exists()


def test_bestehender_bericht_wird_nicht_erneut_ausgeführt(tmp_path, monkeypatch):
    ziel = tmp_path / "bericht.json"
    ziel.write_text("{}", encoding="utf-8")
    aufruf = Mock()
    monkeypatch.setattr(prüfung, "auswerten", aufruf)
    monkeypatch.setattr("sys.argv", [
        "prüfung", "--logs", str(tmp_path), "--ausgabe", str(tmp_path),
        "--start", "2026-01-01T00:00:00Z", "--ende", "2026-01-02T00:00:00Z",
        "--referenz", str(tmp_path / "referenz.json"),
    ])
    prüfung.main()
    aufruf.assert_not_called()
    assert ziel.read_text() == "{}"


def test_timer_einmalig_persistent_und_ohne_netzwerk():
    basis = Path(__file__).resolve().parents[1] / "systemd"
    service = (basis / "tesla-dashboard-wochenpruefung.service").read_text()
    timer = (basis / "tesla-dashboard-wochenpruefung.timer").read_text()
    assert "OnCalendar=2026-10-30 14:00:00 Europe/Berlin" in timer
    assert "Persistent=true" in timer
    for schutz in ("PrivateNetwork=true", "IPAddressDeny=any", "ProtectSystem=strict",
                   "RestrictAddressFamilies=AF_UNIX", "ProtectHome=read-only"):
        assert schutz in service
    assert "ConditionPathExists=!/home/do1ffe/tesla-audits/2026-10-30/bericht.json" in service
    kommando = shlex.split(next(
        z.split("=", 1)[1] for z in service.splitlines()
        if z.startswith("ExecStart=")
    ))
    ende = prüfung.zeitwert(kommando[kommando.index("--ende") + 1])
    assert ende == datetime(2026, 10, 30, 14, tzinfo=prüfung.BERLIN).timestamp()


def test_zeit_ohne_zeitzone_wird_abgelehnt():
    with pytest.raises(ValueError, match="Zeitzone"):
        prüfung.zeitwert("2026-10-30T14:00:00")


# © 2026 Erik Schauer, do1ffe@darc.de
