#!/usr/bin/env python3
"""Erneuere das Telemetrie-Zertifikat und lade es nur bei Bedarf neu."""

import argparse
import hashlib
import socket
import ssl
import subprocess
import sys
import time


def befehl_ausführen(argumente, zeitlimit=60):
    return subprocess.run(
        argumente, check=True, capture_output=True, timeout=zeitlimit,
    ).stdout


def server_fingerabdruck(einstellungen):
    """Prüfe Zertifikatskette und Hostname am lokalen TLS-Endpunkt."""

    kontext = ssl.create_default_context()
    with socket.create_connection(
        ("127.0.0.1", einstellungen.port), timeout=5,
    ) as verbindung:
        with kontext.wrap_socket(
            verbindung, server_hostname=einstellungen.hostname,
        ) as tls:
            return hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()


def zertifikat_warten(einstellungen):
    ausgabe = befehl_ausführen([
        "docker", "exec", einstellungen.acme_container,
        "certbot", "renew", "--cert-name", einstellungen.hostname,
        "--non-interactive", "--no-random-sleep-on-renew",
    ], zeitlimit=300)
    print(ausgabe.decode("utf-8", errors="replace").strip())

    befehl_ausführen([
        "openssl", "x509", "-in", einstellungen.zertifikat,
        "-checkend", "86400", "-noout",
    ])
    zertifikat = befehl_ausführen([
        "openssl", "x509", "-in", einstellungen.zertifikat, "-outform", "DER",
    ])
    erwartet = hashlib.sha256(zertifikat).hexdigest()
    try:
        aktiv = server_fingerabdruck(einstellungen)
    except ssl.SSLCertVerificationError:
        # Ein noch geladenes, abgelaufenes Zertifikat muss ersetzt werden.
        aktiv = None
    if aktiv == erwartet:
        print("Telemetrie-Zertifikat gültig und bereits aktiv; kein Neustart.")
        return False

    befehl_ausführen(["docker", "restart", einstellungen.telemetrie_container])
    for versuch in range(10):
        time.sleep(1)
        try:
            if server_fingerabdruck(einstellungen) == erwartet:
                print("Telemetrie-Zertifikat erneuert, geladen und TLS geprüft.")
                return True
        except (OSError, ssl.SSLError):
            if versuch == 9:
                raise
    raise RuntimeError("Telemetrie-Server verwendet nicht das erneuerte Zertifikat")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", default="telemetry.do1ffe.de")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--acme-container", default="nginx-proxy-app-1")
    parser.add_argument(
        "--telemetrie-container", default="tesla_fleet-fleet-telemetry-1",
    )
    parser.add_argument(
        "--zertifikat",
        default=(
            "/root/nginx-proxy/letsencrypt/live/telemetry.do1ffe.de/fullchain.pem"
        ),
    )
    try:
        zertifikat_warten(parser.parse_args())
    except (OSError, RuntimeError, subprocess.SubprocessError) as fehler:
        print(f"Telemetrie-Zertifikatswartung fehlgeschlagen: {fehler}", file=sys.stderr)
        if isinstance(fehler, subprocess.CalledProcessError) and fehler.stderr:
            print(fehler.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

# © 2026 Erik Schauer, do1ffe@darc.de
