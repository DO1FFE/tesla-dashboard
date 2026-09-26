"""Neue Fleet-Messwerte, GPS-Plausibilität und unverfälschte Diagnoseverläufe."""

import math
import os
import sqlite3
import time


FELDNAMEN = {
    "260": "GpsAccuracyMeters",
    "261": "LifetimeEnergyChargedKwh",
    "262": "BrickSocMinPercent",
    "263": "NominalFullPackEnergyKwh",
    "264": "GradeEstimatePercent",
    "265": "MaxSpeedToReachDestinationMph",
    "266": "SoftwareUpdateAvailable",
    "267": "SoftwareUpdateInProgress",
    "268": "RemoteStartActive",
}
BOOL_FELDER = {
    "SoftwareUpdateAvailable", "SoftwareUpdateInProgress", "RemoteStartActive",
}
INTERVALLE = {
    # Live/Live+, geparkt, ladend. None schließt das Feld im Profil aus.
    "GpsAccuracyMeters": (1, 60, 60),
    "LifetimeEnergyChargedKwh": (300, 300, 60),
    "BrickSocMinPercent": (30, 60, 30),
    "NominalFullPackEnergyKwh": (300, 300, 300),
    "GradeEstimatePercent": (5, None, None),
    "MaxSpeedToReachDestinationMph": (30, None, None),
    "SoftwareUpdateAvailable": (1, 1, 1),
    "SoftwareUpdateInProgress": (1, 1, 1),
    "RemoteStartActive": (10, 10, 10),
}
VERLAUFSFELDER = {
    "NominalFullPackEnergyKwh", "LifetimeEnergyChargedKwh",
    "BrickSocMinPercent", "GradeEstimatePercent",
}


def feldname(feld):
    return FELDNAMEN.get(str(feld), feld)


def profilfelder(profil):
    spalte = {"live": 0, "live_extended": 0, "parked": 1, "charging": 2}[profil]
    return {feld: werte[spalte] for feld, werte in INTERVALLE.items()
            if werte[spalte] is not None}


def zahl(wert):
    if wert is None or isinstance(wert, bool):
        return None
    try:
        ergebnis = float(wert)
    except (TypeError, ValueError):
        return None
    return ergebnis if math.isfinite(ergebnis) else None


def messwert(feld, wert):
    if feld in BOOL_FELDER:
        return wert if isinstance(wert, bool) else None
    wert = zahl(wert)
    if wert is None:
        return None
    if feld == "BrickSocMinPercent" and not 0 <= wert <= 100:
        return None
    if feld == "GradeEstimatePercent":
        return wert if -100 <= wert <= 100 else None
    if wert < 0 or (feld == "NominalFullPackEnergyKwh" and wert == 0):
        return None
    return wert


def cache_normalisieren(daten):
    """Alte Empfänger liefern Enum-Nummern; der jüngere Messpunkt gewinnt."""
    roh = daten.get("fleet_telemetry_raw", {})
    zeiten = daten.get("fleet_telemetry_field_received_at", {})
    for nummer, name in FELDNAMEN.items():
        if nummer not in roh:
            continue
        if name not in roh or (zahl(zeiten.get(nummer)) or 0) > (
            zahl(zeiten.get(name)) or 0
        ):
            roh[name] = roh[nummer]
            for schlüssel in (
                "fleet_telemetry_field_received_at",
                "fleet_telemetry_field_previous_received_at",
                "fleet_telemetry_field_interval_ms",
            ):
                werte = daten.get(schlüssel, {})
                if nummer in werte:
                    werte[name] = werte[nummer]
        roh.pop(nummer, None)


def anreichern(daten):
    cache_normalisieren(daten)
    roh = daten.get("fleet_telemetry_raw", {})
    zeiten = daten.get("fleet_telemetry_field_received_at", {})
    diagnose = {}
    for feld in INTERVALLE:
        wert = messwert(feld, roh.get(feld))
        zeit = zahl(zeiten.get(feld))
        diagnose[feld] = {
            "value": wert,
            "received_at": int(zeit) if zeit and zeit > 0 else None,
            "valid": wert is not None,
        }
    daten["telemetry_diagnostics"] = diagnose
    drive = daten.setdefault("drive_state", {})
    prognose = diagnose["MaxSpeedToReachDestinationMph"]
    zielzeit = zahl(drive.get("active_route_target_changed_at")) or 0
    if (drive.get("active_route_active") is True and prognose["valid"]
            and (prognose["received_at"] or 0) >= zielzeit - 1000):
        drive["active_route_max_speed_mph"] = prognose["value"]
        drive["active_route_max_speed_received_at"] = prognose["received_at"]
    else:
        drive.pop("active_route_max_speed_mph", None)
        drive.pop("active_route_max_speed_received_at", None)


def frischer_wert(daten, feld, jetzt_ms, max_alter_ms):
    punkt = daten.get("telemetry_diagnostics", {}).get(feld, {})
    zeit = zahl(punkt.get("received_at"))
    if zeit is None or not -1000 <= jetzt_ms - zeit <= max_alter_ms:
        return None
    return punkt.get("value") if punkt.get("valid") else None


def software_signale(daten, jetzt_ms=None):
    """Separate Hinweise statt Überschreiben des REST-/Fortschrittsstatus."""
    jetzt_ms = jetzt_ms if jetzt_ms is not None else time.time() * 1000
    vehicle = daten.setdefault("vehicle_state", {})
    software = vehicle.setdefault("software_update", {})
    software.pop("telemetry_status", None)
    software.pop("telemetry_status_received_at", None)
    software.pop("telemetry_version_received_at", None)
    verfügbar = frischer_wert(daten, "SoftwareUpdateAvailable", jetzt_ms, 120000)
    läuft = frischer_wert(daten, "SoftwareUpdateInProgress", jetzt_ms, 120000)
    diagnose = daten.get("telemetry_diagnostics", {})
    keine_aktualisierung = all(
        diagnose.get(feld, {}).get("value") is False
        and diagnose.get(feld, {}).get("valid")
        for feld in ("SoftwareUpdateAvailable", "SoftwareUpdateInProgress")
    )
    # Bestätigte Rücksetzungen gelten bis zum nächsten neueren Stand.
    if keine_aktualisierung:
        verfügbar, läuft = False, False
    if verfügbar is None and läuft is None:
        return
    zeiten = [
        diagnose[feld]["received_at"] for feld in BOOL_FELDER
        if feld.startswith("Software") and diagnose.get(feld, {}).get("valid")
    ]
    zeiten = [zeit for zeit in zeiten if zeit and jetzt_ms - zeit >= -1000
              and (keine_aktualisierung or jetzt_ms - zeit <= 120000)]
    if keine_aktualisierung and len(zeiten) != 2:
        return
    letzter_rest = max(zahl(daten.get(feld)) or 0 for feld in (
        "fleet_vehicle_data_received_at", "fleet_telemetry_park_reconciled_at",
    ))
    if not zeiten or min(zeiten) < letzter_rest:
        return
    zielzeit = zahl(daten.get("fleet_telemetry_field_received_at", {}).get(
        "SoftwareUpdateVersion")) or 0
    if min(zeiten) < zielzeit - 1000:
        return
    status = None
    if läuft is True:
        # Das Bool-Signal allein unterscheidet Download und Installation nicht.
        status = "updating"
        rohzeiten = daten.get("fleet_telemetry_field_received_at", {})
        for feld, attribut, phase in (
            ("SoftwareUpdateInstallationPercentComplete", "install_perc", "installing"),
            ("SoftwareUpdateDownloadPercentComplete", "download_perc", "downloading"),
        ):
            zeit = zahl(rohzeiten.get(feld)) or 0
            fortschritt = zahl(software.get(attribut))
            downloadzeit = zahl(rohzeiten.get(
                "SoftwareUpdateDownloadPercentComplete")) or 0
            installationsbeginn = (
                phase == "installing" and fortschritt == 1
                and zahl(software.get("download_perc")) == 100
                and 0 <= jetzt_ms - downloadzeit <= 120000
                and downloadzeit >= zielzeit - 1000
            )
            if (0 <= jetzt_ms - zeit <= 120000 and zeit >= zielzeit - 1000
                    and fortschritt is not None
                    and (installationsbeginn or (
                        0 < fortschritt < 100
                        and (phase == "downloading" or fortschritt > 1)
                    ))):
                status = phase
                break
    elif verfügbar is True:
        if software.get("status") in {None, "", "none", "available"}:
            status = "available"
    elif verfügbar is False and läuft is False:
        fortschrittszeiten = daten.get("fleet_telemetry_field_received_at", {})
        neuester_fortschritt = max(
            zahl(fortschrittszeiten.get(feld)) or 0 for feld in (
                "SoftwareUpdateDownloadPercentComplete",
                "SoftwareUpdateInstallationPercentComplete",
            )
        )
        if min(zeiten) >= neuester_fortschritt:
            status = "none"
    if status:
        software["telemetry_status"] = status
        software["telemetry_status_received_at"] = min(zeiten)
        software["telemetry_version_received_at"] = zielzeit


def entfernung(a, b):
    breite1, breite2 = math.radians(a[0]), math.radians(b[0])
    dlat = breite2 - breite1
    dlon = math.radians(b[1] - a[1])
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(breite1) * math.cos(breite2) * math.sin(dlon / 2) ** 2
    )
    return 12742000 * math.asin(min(1, math.sqrt(h)))


def position_plausibel(daten, latitude, longitude, zeit):
    """Einzelne Sprünge abfangen, kohärente neue GPS-Fixes wieder zulassen."""
    lat, lon = zahl(latitude), zahl(longitude)
    if (lat is None or lon is None
            or not -90 <= lat <= 90 or not -180 <= lon <= 180):
        return False
    drive = daten.get("drive_state", {})
    vorher = (zahl(drive.get("latitude")), zahl(drive.get("longitude")))
    vorherzeit = zahl(drive.get("gps_as_of"))
    if vorherzeit and vorherzeit < 1e12:
        vorherzeit *= 1000
    if vorherzeit and zeit < vorherzeit:
        return False
    genauigkeit = frischer_wert(daten, "GpsAccuracyMeters", zeit, 30000)
    if (None in vorher or not vorherzeit or zeit - vorherzeit > 120000
            or genauigkeit is None):
        daten.pop("fleet_gps_candidate", None)
        return True
    sekunden = max(0, (zeit - vorherzeit) / 1000)
    tempo = max(60, (zahl(drive.get("speed")) or 0) * 0.44704 + 15)
    toleranz = max(100, min(genauigkeit, 100) * 3) + tempo * sekunden
    if entfernung(vorher, (lat, lon)) <= toleranz:
        daten.pop("fleet_gps_candidate", None)
        return True
    kandidat = daten.get("fleet_gps_candidate", {})
    anzahl = 1
    if kandidat and 0 < zeit - kandidat["time"] <= 10000:
        erreichbar = 100 + tempo * (zeit - kandidat["time"]) / 1000
        if entfernung(kandidat["position"], (lat, lon)) <= erreichbar:
            anzahl = kandidat["count"] + 1
    if anzahl >= 3 and genauigkeit <= 50:
        daten.pop("fleet_gps_candidate", None)
        return True
    daten["fleet_gps_candidate"] = {
        "position": [lat, lon], "time": zeit, "count": anzahl,
    }
    daten["fleet_gps_rejected_at"] = zeit
    return False


def _verbindung(pfad):
    os.makedirs(os.path.dirname(os.path.abspath(pfad)), exist_ok=True)
    conn = sqlite3.connect(pfad, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS telemetry_measurements (
        vehicle TEXT NOT NULL, field TEXT NOT NULL, bucket INTEGER NOT NULL,
        received_at INTEGER NOT NULL, value REAL NOT NULL,
        PRIMARY KEY (vehicle, field, bucket)
    )""")
    return conn


def verlauf_speichern(pfad, fahrzeug, daten):
    """Akku stündlich, Steigung minutenweise; nur echte gültige Messungen."""
    punkte = []
    diagnose = daten.get("telemetry_diagnostics", {})
    for feld in VERLAUFSFELDER:
        punkt = diagnose.get(feld, {})
        zeit = zahl(punkt.get("received_at"))
        wert = messwert(feld, punkt.get("value"))
        if not punkt.get("valid") or wert is None or not zeit or zeit <= 0:
            continue
        if zeit > time.time() * 1000 + 1000:
            continue
        raster = 3600000
        if feld == "GradeEstimatePercent":
            gang = daten.get("drive_state", {}).get("shift_state")
            if gang not in {"D", "R", "N"}:
                continue
            raster = 60000
        punkte.append((str(fahrzeug), feld, int(zeit) // raster, int(zeit), wert))
    if not punkte:
        return
    conn = _verbindung(pfad)
    try:
        with conn:
            conn.executemany("""INSERT INTO telemetry_measurements VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(vehicle, field, bucket) DO UPDATE SET
                received_at=excluded.received_at, value=excluded.value
                WHERE excluded.received_at > telemetry_measurements.received_at""", punkte)
    finally:
        conn.close()


def verlauf_laden(pfad, fahrzeug, feld="NominalFullPackEnergyKwh", limit=1000,
                 täglich=False):
    if feld not in VERLAUFSFELDER or not os.path.exists(pfad):
        return []
    conn = _verbindung(pfad)
    try:
        if täglich:
            return [dict(zeile) for zeile in conn.execute("""
                SELECT received_at, value FROM (
                    SELECT received_at, value, ROW_NUMBER() OVER (
                        PARTITION BY received_at / 86400000 ORDER BY received_at DESC
                    ) AS rang FROM telemetry_measurements WHERE vehicle=? AND field=?
                ) WHERE rang=1 ORDER BY received_at
            """, (str(fahrzeug), feld))]
        return [dict(zeile) for zeile in conn.execute("""
            SELECT received_at, value FROM (
                SELECT received_at, value FROM telemetry_measurements
                WHERE vehicle=? AND field=? ORDER BY received_at DESC LIMIT ?
            ) ORDER BY received_at
        """, (str(fahrzeug), feld, max(1, min(int(limit), 10000))))]
    finally:
        conn.close()


# © 2026 Erik Schauer, do1ffe@darc.de
