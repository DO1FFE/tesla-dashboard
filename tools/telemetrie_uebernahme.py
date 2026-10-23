#!/usr/bin/env python3
"""Übernehme erneut geprüfte Patches mit geschütztem Neustart und Rücknahme."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

try:
    from .telemetrie_korrekturpruefung import dateien_zulässig
    from .telemetrie_passivpruefung import json_laden, speichern
    from .telemetrie_wochenpruefung import zeitwert, zeittext
    from .telemetrie_testsandbox import testbefehl
except ImportError:
    from telemetrie_korrekturpruefung import dateien_zulässig
    from telemetrie_passivpruefung import json_laden, speichern
    from telemetrie_wochenpruefung import zeitwert, zeittext
    from telemetrie_testsandbox import testbefehl


NEUSTART = ["/usr/bin/sudo", "-n", "/usr/local/libexec/tesla-dashboard/telemetrie_neustart.py"]


def git(projekt, *argumente):
    return subprocess.check_output([
        "/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
        *argumente,
    ], cwd=projekt, timeout=90, stderr=subprocess.STDOUT)


def sauber(projekt, basis):
    if git(projekt, "status", "--porcelain").strip():
        raise ValueError("Arbeitsverzeichnis verändert; keine automatische Übernahme")
    if (git(projekt, "rev-parse", "HEAD").decode().strip() != basis
            or git(projekt, "branch", "--show-current").strip() != b"main"):
        raise ValueError("Patch passt nicht mehr zum unveränderten main-Stand")


def patch_laden(ordner, auftrag):
    if not re.fullmatch(r"[0-9a-f]{64}", auftrag.stem):
        raise ValueError("Ungültige Auftragskennung")
    daten = json_laden(auftrag)
    if not re.fullmatch(r"[0-9a-f]{40}", daten.get("basis", "")):
        raise ValueError("Ungültiger Basis-Commit")
    patch = ordner / "korrekturen" / auftrag.stem / "korrektur.patch"
    if patch.is_symlink() or not patch.resolve().is_relative_to(ordner.resolve()):
        raise ValueError("Patch außerhalb der isolierten Arbeitskopie")
    inhalt = patch.read_bytes()
    if not 0 < len(inhalt) <= 256000 or hashlib.sha256(inhalt).hexdigest() != daten.get("patch_sha256"):
        raise ValueError("Patch stimmt nicht mit dem geprüften Artefakt überein")
    return daten["basis"], inhalt


def änderungen_prüfen(kopie):
    dateien = git(kopie, "diff", "--cached", "--name-only", "-z").decode().strip("\0").split("\0")
    if not dateien_zulässig(dateien) or not any(p.startswith("tests/") for p in dateien):
        raise ValueError("Unzulässige Änderung oder fehlender Regressionstest")
    # Keine Symlinks, Submodule oder Löschungen in einer automatischen Korrektur.
    einträge = git(kopie, "diff", "--cached", "--raw", "--no-renames", "-z").decode().split("\0")
    for zeile in einträge[:-1:2]:
        teile = zeile.split()
        if teile[1] not in {"100644", "100755"} or teile[4] not in {"A", "M"}:
            raise ValueError("Dateityp oder Änderungsart nicht automatisch zulässig")
    git(kopie, "diff", "--cached", "--check")


def übernehmen(projekt, ordner, auftrag, ende):
    basis, inhalt = patch_laden(ordner, auftrag)
    sauber(projekt, basis)
    subprocess.run(NEUSTART + ["--prüfen"], check=True, timeout=30, capture_output=True)
    if time.time() + 360 >= ende:
        raise ValueError("Zu wenig Zeit für Prüfung und geschützten Neustart")
    protokoll = ordner / "korrekturen" / auftrag.stem / "übernahme-tests.log"
    with tempfile.TemporaryDirectory(prefix="übernahme-", dir=ordner) as verzeichnis:
        wurzel = Path(verzeichnis)
        kopie = wurzel / "quelle"
        git(projekt, "clone", "--no-hardlinks", "--quiet", str(projekt), str(kopie))
        patch = wurzel / "korrektur.patch"
        patch.write_bytes(inhalt)
        git(kopie, "apply", "--index", str(patch))
        änderungen_prüfen(kopie)
        with protokoll.open("w", encoding="utf-8") as ausgabe:
            subprocess.run(testbefehl(projekt, kopie), cwd=kopie, stdout=ausgabe,
                           stderr=subprocess.STDOUT, check=True, timeout=300)
        # Nochmals prüfen: Entwickleränderungen während des Testlaufs nie überschreiben.
        sauber(projekt, basis)
        subprocess.run(NEUSTART + ["--prüfen"], check=True, timeout=30, capture_output=True)
        if time.time() + 90 >= ende:
            raise ValueError("Schutzfrist reicht nicht mehr für die Übernahme")
        git(kopie, "commit", "-m", "Fix issue found by passive monitoring")
        kandidat = git(kopie, "rev-parse", "HEAD").decode().strip()
        git(projekt, "fetch", "--no-tags", str(kopie), kandidat)
        sauber(projekt, basis)
        git(projekt, "merge", "--ff-only", kandidat)
    commit = kandidat
    ergebnis = {"commit": commit, "produktiv_übernommen": False, "dienst_neu_gestartet": False}
    try:
        sauber(projekt, commit)
        git(projekt, "push", "origin", "main")
        sauber(projekt, commit)
        subprocess.run(NEUSTART, check=True, timeout=110, capture_output=True)
    except subprocess.SubprocessError:
        # Nur den eigenen, unveränderten Commit zurücknehmen; niemals fremde Änderungen.
        sauber(projekt, commit)
        git(projekt, "revert", "--no-edit", commit)
        try:
            git(projekt, "push", "origin", "main")
        finally:
            subprocess.run(NEUSTART, check=True, timeout=110, capture_output=True)
        return {**ergebnis, "status": "zurückgenommen",
                "ergebnis": "Übernahme fehlgeschlagen; eigener Commit zurückgenommen."}
    return {**ergebnis, "status": "übernommen", "produktiv_übernommen": True,
            "dienst_neu_gestartet": True,
            "ergebnis": "Offline-Tests bestanden, main gepusht, Dienst geschützt neu gestartet."}


def ausführen(projekt, ordner, ende):
    os.umask(0o077)
    statuspfad = ordner / "übernahmestatus.json"
    with (ordner / "übernahme.lock").open("a") as sperre:
        fcntl.flock(sperre, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status = json_laden(statuspfad) if statuspfad.exists() else {"läufe": []}
        for lauf in status["läufe"]:
            if lauf.get("status") == "läuft":
                lauf.update(status="unterbrochen", ergebnis="Übernahme manuell prüfen; keine automatische Wiederholung.")
        speichern(statuspfad, status)
        erledigt = {lauf["auftrag"] for lauf in status["läufe"]}
        for auftrag in sorted((ordner / "übernahmeaufträge").glob("*.json")):
            if time.time() >= ende or len(status["läufe"]) >= 24:
                break
            if auftrag.stem in erledigt:
                continue
            eintrag = {"auftrag": auftrag.stem, "zeit": zeittext(time.time()), "status": "läuft"}
            status["läufe"].append(eintrag)
            speichern(statuspfad, status)
            try:
                eintrag.update(übernehmen(projekt, ordner, auftrag, ende))
            except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
                eintrag.update(status="Übernahme abgebrochen", ergebnis=type(exc).__name__)
            speichern(statuspfad, status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projekt", type=Path, required=True)
    parser.add_argument("--ausgabe", type=Path, required=True)
    parser.add_argument("--ende", type=zeitwert, required=True)
    args = parser.parse_args()
    ausführen(args.projekt, args.ausgabe, args.ende)


if __name__ == "__main__":
    main()

# © 2026 Erik Schauer, do1ffe@darc.de
