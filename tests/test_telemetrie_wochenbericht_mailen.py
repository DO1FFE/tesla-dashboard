"""Prüfe Mailaufbau und Versandmarkierung ohne tatsächlichen Mailversand."""

from email import policy
from email.parser import BytesParser
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from tools import telemetrie_wochenbericht_mailen as mail


@pytest.fixture
def bericht(tmp_path):
    (tmp_path / "bericht.txt").write_text(
        "Prüfung: Einsparungen und größere Empfangslücken.\n"
        "© 2026 Erik Schauer, do1ffe@darc.de\n", encoding="utf-8",
    )
    (tmp_path / "bericht.json").write_text(json.dumps({
        "vorher": {}, "nachher": {"bis": "2026-01-02T14:00:00+01:00"},
        "vergleich": {"abrechnungsgenau_belegt": False},
    }), encoding="utf-8")
    return tmp_path


def test_adresse_anhänge_und_umlaute_sind_korrekt(bericht):
    nachricht, prüfsumme = mail.nachricht_erstellen(bericht)
    dekodiert = BytesParser(policy=policy.default).parsebytes(nachricht.as_bytes())
    assert dekodiert["To"] == "do1ffe@darc.de"
    assert dekodiert["From"] == "Tesla-Dashboard <no-reply@do1ffe.de>"
    assert "Wochenprüfung vom 02.01.2026" in dekodiert["Subject"]
    assert prüfsumme in dekodiert["Message-ID"]
    assert dekodiert["Auto-Submitted"] == "auto-generated"
    assert "größere Empfangslücken" in dekodiert.get_body().get_content()
    anhänge = list(dekodiert.iter_attachments())
    assert [a.get_filename() for a in anhänge] == ["bericht.txt", "bericht.json"]
    assert "Prüfung" in anhänge[0].get_content()
    assert json.loads(anhänge[1].get_content())["vergleich"] == {
        "abrechnungsgenau_belegt": False,
    }
    assert mail.nachricht_erstellen(bericht)[1] == prüfsumme


def test_erfolg_markiert_übergabe_und_verhindert_erneuten_versand(bericht, monkeypatch):
    senden = Mock()
    monkeypatch.setattr(mail.subprocess, "run", senden)
    assert mail.versenden(bericht)
    status = json.loads((bericht / "mail-versand.json").read_text())
    assert status["status"] == "an_lokalen_mailserver_übergeben"
    assert status["empfänger"] == "do1ffe@darc.de"
    assert not mail.versenden(bericht)
    senden.assert_called_once()
    assert senden.call_args.args[0] == [
        "/usr/sbin/sendmail", "-i", "-f", "no-reply@do1ffe.de", "do1ffe@darc.de",
    ]
    assert senden.call_args.kwargs["check"] is True
    assert senden.call_args.kwargs["timeout"] == 90


@pytest.mark.parametrize("fehler", [
    subprocess.CalledProcessError(75, "sendmail"),
    subprocess.TimeoutExpired("sendmail", 90),
])
def test_fehler_wird_nicht_als_erfolg_markiert(bericht, monkeypatch, fehler):
    monkeypatch.setattr(mail.subprocess, "run", Mock(side_effect=fehler))
    with pytest.raises(type(fehler)):
        mail.versenden(bericht)
    assert not (bericht / "mail-versand.json").exists()


def test_probe_versendet_nichts_und_sperrt_späteren_versand_nicht(bericht, monkeypatch):
    senden = Mock()
    monkeypatch.setattr(mail.subprocess, "run", senden)
    assert not mail.versenden(bericht, probe=True)
    senden.assert_not_called()
    assert (bericht / "mail-vorschau.eml").exists()
    assert not (bericht / "mail-versand.json").exists()


def test_unfertiger_bericht_wird_nicht_versendet(tmp_path, monkeypatch):
    senden = Mock()
    monkeypatch.setattr(mail.subprocess, "run", senden)
    with pytest.raises(FileNotFoundError):
        mail.versenden(tmp_path)
    senden.assert_not_called()
    assert not (tmp_path / "mail-versand.json").exists()


@pytest.mark.parametrize("daten", [
    {}, [], {"vorher": {}, "nachher": {}, "vergleich": {}},
    {"vorher": {}, "nachher": {"bis": "2099-10-30T14:00:00+01:00"}, "vergleich": {}},
])
def test_ungültiger_oder_zukünftiger_bericht_wird_nicht_versendet(
    bericht, monkeypatch, daten,
):
    senden = Mock()
    monkeypatch.setattr(mail.subprocess, "run", senden)
    (bericht / "bericht.json").write_text(json.dumps(daten), encoding="utf-8")
    with pytest.raises((ValueError, KeyError)):
        mail.versenden(bericht)
    senden.assert_not_called()


def test_versand_startet_nach_erfolg_und_nutzt_nur_lokalen_mailserver():
    systemd = Path(__file__).resolve().parents[1] / "systemd"
    prüfung = (systemd / "tesla-dashboard-wochenpruefung.service").read_text()
    versand = (systemd / "tesla-dashboard-wochenbericht-mail.service").read_text()
    assert "OnSuccess=tesla-dashboard-wochenbericht-mail.service" in prüfung
    assert "PrivateNetwork=true" in prüfung
    assert "IPAddressDeny=any" in prüfung
    assert "IPAddressDeny=any" in versand
    assert "IPAddressAllow=127.0.0.1/32" in versand
    assert "ConditionPathExists=!/home/do1ffe/tesla-audits/2026-10-30/mail-versand.json" in versand
    assert "Restart=on-failure" in versand
    assert "StartLimitBurst=3" in versand


# © 2026 Erik Schauer, do1ffe@darc.de
