import hashlib
import ssl
import subprocess
from types import SimpleNamespace

import pytest

from tools import telemetrie_zertifikat_warten as wartung


@pytest.fixture
def umgebung(monkeypatch):
    einstellungen = SimpleNamespace(
        hostname="telemetry.example.org", port=8443,
        acme_container="acme", telemetrie_container="telemetrie",
        zertifikat="/test/fullchain.pem",
    )
    aufrufe = []

    def ausführen(argumente, zeitlimit=60):
        aufrufe.append(argumente)
        return b"zertifikat" if "DER" in argumente else b""

    monkeypatch.setattr(wartung, "befehl_ausführen", ausführen)
    monkeypatch.setattr(wartung.time, "sleep", lambda _: None)
    return einstellungen, aufrufe, hashlib.sha256(b"zertifikat").hexdigest()


def test_gültiges_aktives_zertifikat_startet_nichts_neu(monkeypatch, umgebung):
    einstellungen, aufrufe, erwartet = umgebung
    monkeypatch.setattr(wartung, "server_fingerabdruck", lambda _: erwartet)

    assert wartung.zertifikat_warten(einstellungen) is False
    assert "--cert-name" in aufrufe[0]
    assert "telemetry.example.org" in aufrufe[0]
    assert "--no-random-sleep-on-renew" in aufrufe[0]
    assert "--force-renewal" not in aufrufe[0]
    assert not any("restart" in aufruf for aufruf in aufrufe)


@pytest.mark.parametrize("abgelaufen", [False, True])
def test_neues_zertifikat_wird_geladen_und_geprüft(
    monkeypatch, umgebung, abgelaufen,
):
    einstellungen, aufrufe, erwartet = umgebung
    antworten = iter([
        ssl.SSLCertVerificationError("abgelaufen") if abgelaufen else "alt",
        ConnectionRefusedError("Server startet"), erwartet,
    ])

    def fingerprint(_):
        antwort = next(antworten)
        if isinstance(antwort, Exception):
            raise antwort
        return antwort

    monkeypatch.setattr(wartung, "server_fingerabdruck", fingerprint)
    assert wartung.zertifikat_warten(einstellungen) is True
    assert [a for a in aufrufe if "restart" in a] == [
        ["docker", "restart", "telemetrie"],
    ]


def test_verbindungsfehler_löst_keinen_neustart_aus(monkeypatch, umgebung):
    einstellungen, aufrufe, _ = umgebung

    def fingerprint(_):
        raise TimeoutError("Keine Antwort")

    monkeypatch.setattr(wartung, "server_fingerabdruck", fingerprint)
    with pytest.raises(TimeoutError):
        wartung.zertifikat_warten(einstellungen)
    assert not any("restart" in a for a in aufrufe)


def test_gescheiterte_erneuerung_lädt_keinen_unsicheren_stand(
    monkeypatch, umgebung,
):
    einstellungen, _, _ = umgebung
    aufrufe = []

    def ausführen(argumente, zeitlimit=60):
        aufrufe.append(argumente)
        raise subprocess.CalledProcessError(1, argumente)

    monkeypatch.setattr(wartung, "befehl_ausführen", ausführen)
    with pytest.raises(subprocess.CalledProcessError):
        wartung.zertifikat_warten(einstellungen)
    assert len(aufrufe) == 1


def test_falsches_zertifikat_nach_neustart_wird_gemeldet(monkeypatch, umgebung):
    einstellungen, aufrufe, _ = umgebung
    monkeypatch.setattr(wartung, "server_fingerabdruck", lambda _: "alt")

    with pytest.raises(RuntimeError, match="nicht das erneuerte Zertifikat"):
        wartung.zertifikat_warten(einstellungen)
    assert sum("restart" in a for a in aufrufe) == 1

# © 2026 Erik Schauer, do1ffe@darc.de
