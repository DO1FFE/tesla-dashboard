#!/usr/bin/env python3
"""Versende ausschließlich vorbereitete Prüfberichte über den lokalen SMTP-Relay."""

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


def versenden(ordner):
    os.umask(0o077)
    archiv = ordner / "versendet"
    archiv.mkdir(exist_ok=True)
    fehlgeschlagen = ordner / "mail-fehlgeschlagen"
    fehlgeschlagen.mkdir(exist_ok=True)
    with (ordner / "mail.lock").open("a") as sperre:
        fcntl.flock(sperre, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for pfad in sorted((ordner / "postausgang").glob("*.json")):
            if (archiv / pfad.name).exists():
                pfad.unlink()
                continue
            versuchspfad = fehlgeschlagen / (pfad.stem + ".versuche")
            versuche = int(versuchspfad.read_text()) if versuchspfad.exists() else 0
            if versuche >= 3:
                pfad.replace(fehlgeschlagen / pfad.name)
                print(f"Versand nach drei Versuchen gestoppt: {pfad.name}", flush=True)
                continue
            temporär = versuchspfad.with_suffix(".tmp")
            temporär.write_text(str(versuche + 1), encoding="utf-8")
            temporär.replace(versuchspfad)
            daten = json.loads(pfad.read_text(encoding="utf-8"))
            nachricht = EmailMessage(policy=SMTP)
            nachricht["From"] = "Tesla-Dashboard <no-reply@do1ffe.de>"
            nachricht["To"] = "do1ffe@darc.de"
            nachricht["Subject"] = "Tesla-Dashboard: " + daten["betreff"]
            nachricht["Date"] = format_datetime(datetime.now(timezone.utc))
            signatur = hashlib.sha256(pfad.read_bytes()).hexdigest()
            nachricht["Message-ID"] = f"<tesla-passiv-{signatur}@do1ffe.de>"
            nachricht["Auto-Submitted"] = "auto-generated"
            nachricht.set_content(daten["text"], charset="utf-8")
            nachricht.add_attachment(daten["text"], subtype="plain", charset="utf-8", filename="bericht.txt")
            nachricht.add_attachment(
                json.dumps(daten["daten"], ensure_ascii=False, indent=2).encode("utf-8"),
                maintype="application", subtype="json", filename="bericht.json",
            )
            try:
                subprocess.run(
                    ["/usr/sbin/sendmail", "-i", "-f", "no-reply@do1ffe.de", "do1ffe@darc.de"],
                    input=nachricht.as_bytes(), capture_output=True, timeout=90, check=True,
                )
            except subprocess.TimeoutExpired:
                # Bei unklarer Annahme nicht blind erneut zustellen.
                pfad.replace(fehlgeschlagen / pfad.name)
                print(f"Unklarer Mailstatus nach Zeitüberschreitung: {pfad.name}", flush=True)
                continue
            pfad.replace(archiv / pfad.name)
            print(f"Mail {nachricht['Message-ID']} an lokalen Relay übergeben.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ausgabe", type=Path, required=True)
    versenden(parser.parse_args().ausgabe)


if __name__ == "__main__":
    main()

# © 2026 Erik Schauer, do1ffe@darc.de
