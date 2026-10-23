"""Prüfe Übernahmen und Rücknahme mit lokalen Git-Repositories ohne Fahrzeugzugriff."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

import pytest

from tools import telemetrie_uebernahme as übernahme
from tools import telemetrie_neustart as neustart


@pytest.fixture
def auftrag(tmp_path, monkeypatch):
    for name, wert in {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
                       "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}.items():
        monkeypatch.setenv(name, wert)
    projekt = tmp_path / "projekt"
    projekt.mkdir()
    übernahme.git(projekt, "init", "-q", "-b", "main")
    (projekt / "app.py").write_text("wert = 1\n")
    übernahme.git(projekt, "add", ".")
    übernahme.git(projekt, "commit", "-qm", "Initial")
    basis = übernahme.git(projekt, "rev-parse", "HEAD").decode().strip()
    remote = tmp_path / "remote.git"
    übernahme.git(projekt, "init", "--bare", "-q", str(remote))
    übernahme.git(projekt, "remote", "add", "origin", str(remote))
    übernahme.git(projekt, "push", "-q", "origin", "main")
    kopie = tmp_path / "kandidat"
    übernahme.git(projekt, "clone", "-q", "--no-hardlinks", str(projekt), str(kopie))
    (kopie / "app.py").write_text("wert = 2\n")
    (kopie / "tests").mkdir()
    (kopie / "tests/test_regression.py").write_text("def test_wert():\n    assert True\n")
    übernahme.git(kopie, "add", ".")
    patch = übernahme.git(kopie, "diff", "--cached", "--binary")
    ordner = tmp_path / "audit"
    kennung = "a" * 64
    artefakte = ordner / "korrekturen" / kennung
    artefakte.mkdir(parents=True)
    (artefakte / "korrektur.patch").write_bytes(patch)
    (ordner / "übernahmeaufträge").mkdir()
    datei = ordner / "übernahmeaufträge" / f"{kennung}.json"
    datei.write_text(json.dumps({"basis": basis, "patch_sha256": hashlib.sha256(patch).hexdigest()}))
    aufrufe = []
    original = subprocess.run

    def ausführen(befehl, *args, **kwargs):
        if befehl[:len(übernahme.NEUSTART)] == übernahme.NEUSTART or befehl[0] == "/usr/bin/bwrap":
            aufrufe.append(befehl)
            return subprocess.CompletedProcess(befehl, 0)
        return original(befehl, *args, **kwargs)

    monkeypatch.setattr(übernahme.subprocess, "run", ausführen)
    return projekt, ordner, datei, time.time() + 3600, aufrufe


def test_getestete_korrektur_übernehmen_und_geschützt_neustarten(auftrag):
    projekt, ordner, datei, ende, aufrufe = auftrag
    ergebnis = übernahme.übernehmen(projekt, ordner, datei, ende)
    assert ergebnis["produktiv_übernommen"] and ergebnis["dienst_neu_gestartet"]
    assert (projekt / "app.py").read_text() == "wert = 2\n"
    assert übernahme.git(projekt, "status", "--porcelain") == b""
    assert aufrufe[-1] == übernahme.NEUSTART
    assert any(befehl[:2] == ["/usr/bin/bwrap", "--unshare-all"] for befehl in aufrufe)
    assert übernahme.git(projekt, "rev-parse", "HEAD") == übernahme.git(projekt, "rev-parse", "origin/main")


def test_fremde_änderungen_bleiben_unberührt(auftrag):
    projekt, ordner, datei, ende, aufrufe = auftrag
    (projekt / "app.py").write_text("fremde_änderung = True\n")
    with pytest.raises(ValueError, match="Arbeitsverzeichnis"):
        übernahme.übernehmen(projekt, ordner, datei, ende)
    assert not aufrufe
    assert (projekt / "app.py").read_text() == "fremde_änderung = True\n"


def test_veränderter_patch_verhindert_übernahme(auftrag):
    projekt, ordner, datei, ende, aufrufe = auftrag
    (ordner / "korrekturen" / datei.stem / "korrektur.patch").write_bytes(b"falsch")
    with pytest.raises(ValueError, match="Artefakt"):
        übernahme.übernehmen(projekt, ordner, datei, ende)
    assert not aufrufe


def test_fehlgeschlagene_tests_verhindern_push_und_neustart(auftrag, monkeypatch):
    projekt, ordner, datei, ende, aufrufe = auftrag
    original = übernahme.subprocess.run

    def ausführen(befehl, *args, **kwargs):
        if befehl[0] == "/usr/bin/bwrap":
            raise subprocess.CalledProcessError(1, befehl)
        return original(befehl, *args, **kwargs)

    monkeypatch.setattr(übernahme.subprocess, "run", ausführen)
    with pytest.raises(subprocess.CalledProcessError):
        übernahme.übernehmen(projekt, ordner, datei, ende)
    assert (projekt / "app.py").read_text() == "wert = 1\n"
    assert all(befehl != übernahme.NEUSTART for befehl in aufrufe)


def test_fehlgeschlagener_neustart_nimmt_nur_eigenen_commit_zurück(auftrag, monkeypatch):
    projekt, ordner, datei, ende, aufrufe = auftrag
    original = übernahme.subprocess.run
    versuche = []

    def ausführen(befehl, *args, **kwargs):
        if befehl == übernahme.NEUSTART:
            versuche.append(befehl)
            if len(versuche) == 1:
                raise subprocess.CalledProcessError(1, befehl)
        return original(befehl, *args, **kwargs)

    monkeypatch.setattr(übernahme.subprocess, "run", ausführen)
    ergebnis = übernahme.übernehmen(projekt, ordner, datei, ende)
    assert ergebnis["status"] == "zurückgenommen"
    assert (projekt / "app.py").read_text() == "wert = 1\n"
    assert len(versuche) == 2
    assert übernahme.git(projekt, "rev-parse", "HEAD") == übernahme.git(projekt, "rev-parse", "origin/main")


def test_nur_ein_versuch_und_nach_ende_keine_übernahme(auftrag, monkeypatch):
    projekt, ordner, datei, ende, _ = auftrag
    aufrufe = []
    monkeypatch.setattr(übernahme, "übernehmen", lambda *args: aufrufe.append(args) or {"status": "übernommen"})
    übernahme.ausführen(projekt, ordner, ende)
    übernahme.ausführen(projekt, ordner, ende)
    assert len(aufrufe) == 1
    übernahme.ausführen(projekt, ordner, 1)
    assert len(aufrufe) == 1


@pytest.mark.parametrize("dateien", [["tests/conftest.py"], ["tests/test_fahrzeugzugriffsschutz.py"],
                                     ["tests/../fahrzeugzugriffsschutz.py"], ["/tmp/app.py"],
                                     ["fahrzeugzugriffsschutz.py"], ["tools/telemetrie_neustart.py"]])
def test_schutzdateien_und_pfadtraversal_nicht_automatisch_änderbar(dateien):
    assert not übernahme.dateien_zulässig(dateien)


def test_keine_http_gesundheitsprüfung_und_keine_freie_dienstwahl():
    quelle = Path(neustart.__file__).read_text()
    assert '"/usr/bin/ss"' in quelle
    assert "requests" not in quelle and "curl" not in quelle
    assert 'DIENST = "tesla-dashboard.service"' in quelle


def test_testsandbox_versteckt_produktivdaten_und_umgebungsgeheimnisse():
    befehl = übernahme.testbefehl(Path("/home/test/projekt"), Path("/tmp/kopie"))
    assert "--unshare-all" in befehl and "--clearenv" in befehl
    assert ["--tmpfs", "/home"] == befehl[befehl.index("/home") - 1:befehl.index("/home") + 1]
    assert ["--ro-bind", "/", "/"] == befehl[3:6]


# © 2026 Erik Schauer, do1ffe@darc.de
