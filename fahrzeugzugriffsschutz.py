"""Befristete oder ausdrücklich unbefristete Abfragesperre für Dienstneustarts."""

from datetime import datetime
import math
import os
import time
from urllib.parse import unquote, urlsplit


STARTZEIT = time.time()
_ende = None
_profil_freigegeben = False
_installiert = False
_proxy = None


class FahrzeugabfrageGesperrt(RuntimeError):
    """Eine Abfrage wurde vor jedem HTTP-Versand verhindert."""


def konfigurieren(ende, proxy):
    """Ungültige Schutzkonfiguration verhindert den Start, statt freizugeben."""
    global _ende, _proxy
    if ende == "unbefristet":
        zeitpunkt = math.inf
    else:
        zeit = datetime.fromisoformat(ende.replace("Z", "+00:00"))
        if zeit.tzinfo is None or not math.isfinite(zeit.timestamp()):
            raise ValueError("Schutzende benötigt eine gültige Zeitzone")
        zeitpunkt = zeit.timestamp()
    url = urlsplit(proxy)
    if (url.scheme != "https" or not url.hostname or url.username
            or url.password or url.query or url.fragment or url.path not in {"", "/"}):
        raise ValueError("Ungültige Adresse des Fahrzeug-Proxys")
    _ende = zeitpunkt
    _proxy = (url.scheme, url.hostname, url.port or 443)


def aktiv():
    return _ende is not None and time.time() < _ende


def profil_freigeben(daten):
    """Alte Start-Caches/Retained-Werte geben keine Profilübertragung frei."""
    global _profil_freigegeben
    if not aktiv():
        return True
    if not _profil_freigegeben and isinstance(daten, dict):
        try:
            zeit = float(daten.get("fleet_telemetry_received_at") or 0) / 1000
        except (TypeError, ValueError):
            zeit = 0
        jetzt = time.time()
        if STARTZEIT < zeit <= jetzt and jetzt - STARTZEIT >= 15:
            _profil_freigegeben = True
    return _profil_freigegeben


def anfrage_prüfen(methode, adresse):
    """Sperre Tesla-Daten, Befehle und Wake-ups auch bei direkten SDK-Aufrufen."""
    if not aktiv():
        return
    url = urlsplit(adresse)
    host = (url.hostname or "").lower().rstrip(".")
    ursprung = (url.scheme, host, url.port or (443 if url.scheme == "https" else 80))
    pfad = unquote(url.path)
    ist_tesla = host == "tesla.com" or host.endswith(".tesla.com")
    ist_tesla = ist_tesla or host == "tesla.cn" or host.endswith(".tesla.cn")
    if not (ist_tesla or ursprung == _proxy or "/api/1/" in pfad):
        return
    if url.username or url.password or url.query or url.fragment:
        raise FahrzeugabfrageGesperrt("Fahrzeugzugriff während Überwachung gesperrt")
    if (methode.upper() == "POST" and ursprung == ("https", "auth.tesla.com", 443)
            and pfad == "/oauth2/v3/token"):
        return
    if (methode.upper() == "POST" and ursprung == _proxy and _profil_freigegeben
            and pfad == "/api/1/vehicles/fleet_telemetry_config"):
        return
    raise FahrzeugabfrageGesperrt("Fahrzeugzugriff während Überwachung gesperrt")


def installieren():
    """Sichere den gemeinsamen Requests-Transport einschließlich TeslaPy ab."""
    global _installiert
    if _installiert:
        return
    import requests.adapters

    original = requests.adapters.HTTPAdapter.send

    def geschützt(adapter, request, *args, **kwargs):
        anfrage_prüfen(request.method, request.url)
        return original(adapter, request, *args, **kwargs)

    requests.adapters.HTTPAdapter.send = geschützt
    _installiert = True


def aus_umgebung_starten():
    ende = os.environ.get("TESLA_DASHBOARD_ABFRAGESPERRE_BIS")
    if ende:
        konfigurieren(ende, os.environ.get(
            "TESLA_FLEET_VEHICLE_COMMAND_URL", "https://127.0.0.1:4443",
        ))
        installieren()


# © 2026 Erik Schauer, do1ffe@darc.de
