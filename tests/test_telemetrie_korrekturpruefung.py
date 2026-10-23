"""Prüfe die Sicherheitsgrenzen automatischer, nicht produktiver Korrekturen."""

from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools import telemetrie_korrekturpruefung as prüfung


def test_codex_sperrt_fahrzeugzugriff_und_escalation():
    befehl = prüfung.codex_befehl(Path("/tmp/kopie"), Path("schema"), Path("ausgabe"), "Prüfen")
    assert "workspace-write" in befehl
    assert "--ignore-user-config" in befehl and "--ignore-rules" in befehl
    assert "sandbox_workspace_write.network_access=false" in befehl
    assert 'approval_policy="never"' in befehl
    assert 'web_search="disabled"' in befehl
    assert "danger-full-access" not in befehl
    assert "--model" not in befehl


@pytest.mark.parametrize("dateien", [[], [".env"], ["systemd/test.service"],
                                     ["tools/telemetrie_korrekturpruefung.py"], ["docs/test.txt"]])
def test_unzulässige_korrekturen_werden_nicht_als_patch_übernommen(dateien):
    assert not prüfung.dateien_zulässig(dateien)


def test_app_und_regressionstest_zulässig():
    assert prüfung.dateien_zulässig(["app.py", "tests/test_neuer_fehler.py"])


def test_aufträge_nur_einmal_und_nicht_nach_frist(tmp_path, monkeypatch):
    warteschlange = tmp_path / "korrekturaufträge"
    warteschlange.mkdir()
    (warteschlange / "eins.json").write_text("{}")
    lauf = Mock(return_value={"status": "kein_codefehler", "ergebnis": "Kein reproduzierbarer Fehler"})
    monkeypatch.setattr(prüfung, "prüfen", lauf)
    ende = datetime.now(timezone.utc).timestamp() + 3600
    prüfung.ausführen(tmp_path / "projekt", tmp_path, ende)
    prüfung.ausführen(tmp_path / "projekt", tmp_path, ende)
    lauf.assert_called_once()
    (warteschlange / "zwei.json").write_text("{}")
    prüfung.ausführen(tmp_path / "projekt", tmp_path, 1)
    lauf.assert_called_once()
    status = json.loads((tmp_path / "korrekturstatus.json").read_text())
    assert len(status["läufe"]) == 1


def test_fehlgeschlagene_korrektur_keine_wiederholungsschleife(tmp_path, monkeypatch):
    warteschlange = tmp_path / "korrekturaufträge"
    warteschlange.mkdir()
    (warteschlange / "eins.json").write_text("{}")
    lauf = Mock(side_effect=ValueError("ungültiger Patch"))
    monkeypatch.setattr(prüfung, "prüfen", lauf)
    ende = datetime.now(timezone.utc).timestamp() + 3600
    prüfung.ausführen(tmp_path / "projekt", tmp_path, ende)
    prüfung.ausführen(tmp_path / "projekt", tmp_path, ende)
    lauf.assert_called_once()
    status = json.loads((tmp_path / "korrekturstatus.json").read_text())
    assert status["läufe"][0]["status"] == "Prüfung fehlgeschlagen"


def test_ressourcenlimit(tmp_path, monkeypatch):
    (tmp_path / "korrekturaufträge").mkdir()
    (tmp_path / "korrekturaufträge/neu.json").write_text("{}")
    (tmp_path / "korrekturstatus.json").write_text(json.dumps({"verarbeitet": [], "läufe": [{}] * 24}))
    lauf = Mock()
    monkeypatch.setattr(prüfung, "prüfen", lauf)
    prüfung.ausführen(tmp_path / "projekt", tmp_path, datetime.now(timezone.utc).timestamp() + 3600)
    lauf.assert_not_called()


def test_produktivprojekt_und_zugangsdaten_geschützt():
    basis = Path(__file__).resolve().parents[1]
    dienst = (basis / "systemd/tesla-dashboard-korrekturpruefung.service").read_text()
    assert "ReadOnlyPaths=/home/do1ffe/tesla-dashboard" in dienst
    assert "InaccessiblePaths=-/home/do1ffe/tesla-dashboard/.env" in dienst
    assert "NoNewPrivileges=true" in dienst
    skript = (basis / "tools/telemetrie_korrekturpruefung.py").read_text()
    assert "testbefehl(projekt, quelle)" in skript
    assert '"git", "push"' not in skript
    assert '"systemctl", "restart"' not in skript


# © 2026 Erik Schauer, do1ffe@darc.de
