#!/usr/bin/env python3
"""Versende den abgeschlossenen Wochenbericht über den lokalen Mailserver."""

import argparse
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess


ABSENDER = "no-reply@do1ffe.de"
EMPFÄNGER = "do1ffe@darc.de"


def nachricht_erstellen(ordner):
    """Verwende nur fertige Berichte, niemals Referenz- oder Fahrzeugrohdaten."""
    text = (ordner / "bericht.txt").read_text(encoding="utf-8")
    jsondaten = (ordner / "bericht.json").read_bytes()
    daten = json.loads(jsondaten)
    if not text.strip() or not isinstance(daten, dict) or not all(
        isinstance(daten.get(feld), dict)
        for feld in ("vorher", "nachher", "vergleich")
    ):
        raise ValueError("Kein vollständiger Wochenbericht vorhanden")
    ende = datetime.fromisoformat(daten["nachher"]["bis"])
    if ende.tzinfo is None or ende > datetime.now(timezone.utc):
        raise ValueError("Der Prüfzeitraum ist noch nicht abgeschlossen")

    prüfsumme = hashlib.sha256(text.encode("utf-8") + jsondaten).hexdigest()
    nachricht = EmailMessage(policy=SMTP)
    nachricht["From"] = f"Tesla-Dashboard <{ABSENDER}>"
    nachricht["To"] = EMPFÄNGER
    nachricht["Subject"] = (
        f"Tesla-Dashboard: Wochenprüfung vom {ende:%d.%m.%Y}"
    )
    nachricht["Date"] = format_datetime(datetime.now(timezone.utc))
    nachricht["Message-ID"] = f"<tesla-wochenbericht-{prüfsumme}@do1ffe.de>"
    nachricht["Auto-Submitted"] = "auto-generated"
    nachricht.set_content(
        "Die geplante Logprüfung ist abgeschlossen. Der Bericht steht unten "
        "und ist zusätzlich als Text- und JSON-Datei angehängt.\n\n" + text
    )
    nachricht.add_attachment(
        text, subtype="plain", charset="utf-8", filename="bericht.txt",
    )
    nachricht.add_attachment(
        jsondaten, maintype="application", subtype="json", filename="bericht.json",
    )
    return nachricht, prüfsumme


def versenden(ordner, probe=False):
    """Sperre parallele Übergaben und markiere erst die erfolgreiche Annahme."""
    os.umask(0o077)
    statuspfad = ordner / "mail-versand.json"
    with (ordner / "mail-versand.lock").open("a", encoding="utf-8") as sperre:
        fcntl.flock(sperre, fcntl.LOCK_EX)
        if statuspfad.exists():
            print("Bericht wurde bereits an den lokalen Mailserver übergeben.")
            return False
        nachricht, prüfsumme = nachricht_erstellen(ordner)
        if probe:
            (ordner / "mail-vorschau.eml").write_bytes(nachricht.as_bytes())
            print("Nur Mailvorschau gespeichert; keine E-Mail versendet.")
            return False
        subprocess.run(
            ["/usr/sbin/sendmail", "-i", "-f", ABSENDER, EMPFÄNGER],
            input=nachricht.as_bytes(), check=True, timeout=90,
            capture_output=True,
        )
        status = {
            "status": "an_lokalen_mailserver_übergeben",
            "empfänger": EMPFÄNGER,
            "absender": ABSENDER,
            "message_id": str(nachricht["Message-ID"]),
            "bericht_sha256": prüfsumme,
            "übergeben_am": datetime.now(timezone.utc).isoformat(),
        }
        temporär = statuspfad.with_suffix(".json.tmp")
        with temporär.open("w", encoding="utf-8") as datei:
            json.dump(status, datei, ensure_ascii=False, indent=2)
            datei.write("\n")
            datei.flush()
            os.fsync(datei.fileno())
        temporär.replace(statuspfad)
        print(f"Wochenbericht an den lokalen Mailserver für {EMPFÄNGER} übergeben.")
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--berichtordner", type=Path, required=True)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    versenden(args.berichtordner, probe=args.probe)


if __name__ == "__main__":
    main()

# © 2026 Erik Schauer, do1ffe@darc.de
