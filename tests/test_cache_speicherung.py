"""Prüfe vollständige Cache-Dateien bei parallelen Zugriffen und Schreibfehlern."""

import json

import pytest

import app


def test_leser_sieht_während_des_schreibens_den_vollständigen_cache(
    tmp_path, monkeypatch,
):
    ziel = tmp_path / "cache.json"
    vorher = {"zustand": "vorher"}
    ziel.write_text(json.dumps(vorher), encoding="utf-8")
    monkeypatch.setattr(app, "_cache_file", lambda _: str(ziel))
    beobachtungen = []

    def schrittweise_schreiben(daten, datei):
        datei.write('{"zustand":')
        datei.flush()
        beobachtungen.append(json.loads(ziel.read_text(encoding="utf-8")))
        datei.write('"nachher"}')

    monkeypatch.setattr(app.json, "dump", schrittweise_schreiben)
    app._save_cached("test", {"zustand": "nachher"})

    assert beobachtungen == [vorher]
    assert json.loads(ziel.read_text(encoding="utf-8")) == {"zustand": "nachher"}
    assert list(tmp_path.iterdir()) == [ziel]


@pytest.mark.parametrize("fehlerstelle", ["serialisierung", "ersetzen"])
def test_schreibfehler_erhält_den_bisherigen_cache_ohne_dateireste(
    tmp_path, monkeypatch, fehlerstelle,
):
    ziel = tmp_path / "cache.json"
    vorher = '{"zustand": "bisher"}'
    ziel.write_text(vorher, encoding="utf-8")
    monkeypatch.setattr(app, "_cache_file", lambda _: str(ziel))
    daten = {"zustand": "nachher"}
    if fehlerstelle == "serialisierung":
        daten["ungültig"] = object()
    else:
        def ersetzen_fehlgeschlagen(*args):
            raise OSError("Ersetzen fehlgeschlagen")

        monkeypatch.setattr(app.os, "replace", ersetzen_fehlgeschlagen)

    app._save_cached("test", daten)

    assert ziel.read_text(encoding="utf-8") == vorher
    assert list(tmp_path.iterdir()) == [ziel]


def test_überlappende_schreiber_verwenden_getrennte_temporäre_dateien(
    tmp_path, monkeypatch,
):
    ziel = tmp_path / "cache.json"
    ziel.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(app, "_cache_file", lambda _: str(ziel))
    original_schreiben = json.dump
    beobachtungen = []

    def überlappend_schreiben(daten, datei):
        if daten["zustand"] == "außen":
            datei.write('{"zustand":')
            datei.flush()
            app._save_cached("test", {"zustand": "innen mit längeren Daten"})
            beobachtungen.append(json.loads(ziel.read_text(encoding="utf-8")))
            datei.write('"außen"}')
        else:
            original_schreiben(daten, datei)

    monkeypatch.setattr(app.json, "dump", überlappend_schreiben)
    app._save_cached("test", {"zustand": "außen"})

    assert beobachtungen == [{"zustand": "innen mit längeren Daten"}]
    assert json.loads(ziel.read_text(encoding="utf-8")) == {"zustand": "außen"}
    assert list(tmp_path.iterdir()) == [ziel]


def test_cache_kann_erstmals_angelegt_werden(tmp_path, monkeypatch):
    ziel = tmp_path / "cache.json"
    monkeypatch.setattr(app, "_cache_file", lambda _: str(ziel))
    daten = {"zustand": "gültig äöüß"}

    app._save_cached("test", daten)

    assert json.loads(ziel.read_text(encoding="utf-8")) == daten
    assert list(tmp_path.iterdir()) == [ziel]


# © 2026 Erik Schauer, do1ffe@darc.de
