#!/usr/bin/env python3
"""Befristete Logüberwachung ohne Fahrzeugzugriff oder Änderungen am Dashboard."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

try:
    from . import telemetrie_wochenpruefung as auswertung
except ImportError:
    import telemetrie_wochenpruefung as auswertung


DIENSTE = (
    "tesla-dashboard.service",
    "tesla-dashboard-status-monitor.service",
    "tesla-dashboard-mqtt-monitor.service",
)
GRENZEN = (
    "Die Diagnose liest nur lokale Dateien und Journale; keine Fahrzeugabfragen, Wake-ups, "
    "Profilübertragungen oder Dashboard-Neustarts.",
    "Befunde sind Diagnosehinweise, keine automatisch bewiesenen Codefehler. "
    "Getrennte Korrekturprüfung und erneute netzlose Tests vor automatischer Übernahme. "
    "Neustarts nur mit zeitlich begrenzter Fahrzeug-Abfragesperre; Profilwechsel bleiben möglich.",
    "RouteLine und Ziel werden im Cache geprüft. Die tatsächliche Darstellung "
    "in einem entfernten Browser ist aus diesen Logs nicht nachweisbar.",
    "Stillstand, Schlaf und unveränderte Werte belegen keinen fehlenden Sekundentakt. "
    "Ohne Fahrdaten bleibt Live/Live+ nicht beurteilbar.",
)


def json_laden(pfad):
    with pfad.open(encoding="utf-8") as datei:
        daten = json.load(datei)
    if not isinstance(daten, dict):
        raise ValueError("JSON-Objekt erwartet")
    return daten


def speichern(pfad, daten):
    auswertung.atomar_speichern(
        pfad, json.dumps(daten, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )


def zahl(wert):
    return (
        isinstance(wert, (int, float)) and not isinstance(wert, bool)
        and math.isfinite(wert)
    )


def frisch(wert, jetzt, alter):
    return zahl(wert) and 0 <= jetzt - wert / 1000 <= alter


def objekt(daten, schlüssel):
    wert = daten.get(schlüssel)
    if wert is not None and not isinstance(wert, dict):
        raise ValueError("Ungültige lokale Datenstruktur")
    return wert or {}


def dienststatus():
    antwort = subprocess.run([
        "/usr/bin/systemctl", "show", *DIENSTE, "--property=Id",
        "--property=ActiveState", "--property=SubState", "--property=NRestarts",
    ], capture_output=True, text=True, timeout=15, check=True)
    ergebnis = {}
    for abschnitt in antwort.stdout.strip().split("\n\n"):
        felder = dict(zeile.split("=", 1) for zeile in abschnitt.splitlines() if "=" in zeile)
        if felder.get("Id") in DIENSTE:
            ergebnis[felder["Id"]] = felder
    if set(ergebnis) != set(DIENSTE):
        raise ValueError("Dienststatus unvollständig")
    return ergebnis


def journalfehler(start, ende):
    antwort = subprocess.run([
        "/usr/bin/journalctl", "-q", "-u", "tesla-dashboard.service",
        "--since", f"@{int(start)}", "--until", f"@{int(ende)}",
        "--no-pager", "--output=json",
    ], capture_output=True, text=True, timeout=30, check=True)
    muster = {
        "Python-Ausnahme": r"Traceback \(most recent call last\)|Exception in",
        "Fehlermeldung": r"\bERROR\b|\bCRITICAL\b|\bError:\s",
        "Abrechnungssperre": r"EXCEEDED_LIMIT",
        "Authentifizierung": r"\bHTTP(?:Error)?[^\n]*\b(?:401|403)\b|invalid_grant",
    }
    zähler = Counter()
    for zeile in antwort.stdout.splitlines():
        eintrag = json.loads(zeile)
        meldung = eintrag.get("MESSAGE", "")
        if not isinstance(meldung, str):
            continue
        for name, regex in muster.items():
            if re.search(regex, meldung):
                zähler[name] += 1
        if str(eintrag.get("PRIORITY")) in {"0", "1", "2", "3"}:
            zähler["Journal-Priorität Fehler"] += 1
    # Keine Rohmeldungen versenden: Sie könnten Tokens, Ziele oder Positionen enthalten.
    return dict(zähler)


def momentbefunde(cache, profil, dienste, jetzt):
    befunde = {}
    for name, daten in dienste.items():
        if daten.get("ActiveState") != "active" or daten.get("SubState") != "running":
            befunde[f"dienst:{name}"] = (f"Dienst {name} läuft nicht regulär.", 0)
    drive = objekt(cache, "drive_state")
    klima = objekt(cache, "climate_state")
    charge = objekt(cache, "charge_state")
    zeiten = objekt(cache, "fleet_telemetry_field_received_at")
    empfang_frisch = frisch(cache.get("fleet_telemetry_received_at"), jetzt, 60)
    fährt = (
        drive.get("shift_state") in {"D", "R"}
        and zahl(drive.get("speed")) and drive["speed"] > .5
        and frisch(zeiten.get("VehicleSpeed"), jetzt, 15)
    )
    lädt = charge.get("charging_state") == "Charging" and frisch(
        zeiten.get("ChargeState"), jetzt, 60,
    )
    if (fährt or lädt) and cache.get("state") != "online":
        befunde["zustand"] = ("Frische Fahrt-/Ladedaten, aber Cache nicht online.", 60)
    if fährt and profil.get("current") not in {"live", "live_extended"}:
        befunde["fahrprofil"] = ("Bewegung bei einem anderen Profil als Live/Live+.", 30)
    if empfang_frisch and cache.get("state") == "online":
        seit = profil.get("target_since")
        aktuell, ziel = profil.get("current"), profil.get("target")
        # Live+ ist eine bestätigte Erweiterung des übergeordneten Ziels Live.
        passend = aktuell in {"live", "live_extended", "charging", "parked"} and (
            aktuell == ziel or aktuell == "live_extended" and ziel == "live"
        )
        unbestätigt = (
            not passend
            or profil.get("config_synced") is not True
            or profil.get("config_sync_profile") != aktuell
        )
        if zahl(seit) and jetzt - seit > 120 and unbestätigt:
            befunde["profilbestätigung"] = ("Profil seit über 120 s nicht passend bestätigt.", 60)
        camp = str(klima.get("climate_keeper_mode", "")).lower() == "camp"
        if camp and profil.get("current") not in {"live", "live_extended"}:
            befunde["campprofil"] = ("Camp-Mode aktiv, aber kein Live-/Live+-Profil.", 120)
        if lädt and profil.get("current") == "parked":
            befunde["ladeprofil"] = ("Frische Lademeldung bei Profil parked.", 120)
        if drive.get("active_route_active") is True:
            if not isinstance(drive.get("active_route_line"), str) or not drive["active_route_line"].strip():
                befunde["routeline"] = (
                    "Navigation aktiv, aber keine RouteLine im Cache; eine Luftlinie ist möglich.", 120,
                )
            lat, lon = drive.get("active_route_latitude"), drive.get("active_route_longitude")
            if not (zahl(lat) and zahl(lon) and -90 <= lat <= 90 and -180 <= lon <= 180
                    and (lat != 0 or lon != 0)):
                befunde["navigationsziel"] = ("Aktive Navigation ohne plausible Zielkoordinaten.", 120)
        roh = objekt(cache, "fleet_telemetry_raw")
        türen = roh.get("DoorState") or {}
        fahrzeug = objekt(cache, "vehicle_state")
        if isinstance(türen, dict) and frisch(zeiten.get("DoorState"), jetzt, 30):
            for feld, tür in (("df", "DriverFront"), ("dr", "DriverRear"),
                              ("pf", "PassengerFront"), ("pr", "PassengerRear"),
                              ("ft", "TrunkFront"), ("rt", "TrunkRear")):
                if (isinstance(türen.get(tür), bool) and fahrzeug.get(feld) in (0, 1)
                        and bool(fahrzeug[feld]) != türen[tür]):
                    befunde[f"tür:{feld}"] = (f"Türwert {feld} widerspricht frischer Rohmeldung.", 60)
        for feld, fenster in (("fd_window", "FdWindow"), ("fp_window", "FpWindow"),
                              ("rd_window", "RdWindow"), ("rp_window", "RpWindow")):
            wert = roh.get(fenster)
            if (wert == "WindowStateClosed" and frisch(zeiten.get(fenster), jetzt, 30)
                    and zahl(fahrzeug.get(feld)) and fahrzeug[feld] > 0):
                befunde[f"fenster:{feld}"] = (f"Fenster {feld} offen trotz frischer Geschlossen-Meldung.", 60)
    return befunde


def takt_befunde(daten):
    befunde = {}
    for profil, wert in daten["takt"].items():
        if wert["fahrtstunden"] * 3600 < 30 or "mehrere Fahrzeuge" in wert["bewertung"]:
            continue
        for feld in ("Location", "VehicleSpeed"):
            messung = wert["felder"][feld]
            if (messung["lücken_ab_8_s"] or
                    messung["intervalle"] >= 10 and messung["p95_s"] > 2):
                befunde[f"takt:{profil}:{feld}"] = (
                    f"{profil}, {feld}: Empfangsabstände während protokollierter Bewegung auffällig; "
                    "Fahrzeug, Mobilfunk und Aufzeichnung als Ursache unterscheiden.", 0,
                )
    if daten["fahrtstunden_ohne_liveprofil"] * 3600 > 30:
        befunde["fahrt_ohne_live"] = ("Über 30 s Bewegung ohne Live-/Live+-Profil protokolliert.", 0)
    return befunde


def befunde_fortschreiben(zustand, kandidaten, jetzt):
    historisch = zustand.setdefault("befunde", {})
    ereignisse = []
    for kennung, (text, wartezeit) in kandidaten.items():
        eintrag = historisch.setdefault(kennung, {"anzahl": 0})
        if eintrag.get("seit") is None:
            eintrag["seit"] = jetzt
        eintrag["zuletzt"] = jetzt
        eintrag["text"] = text
        if not eintrag.get("aktiv") and jetzt - eintrag["seit"] >= wartezeit:
            eintrag["aktiv"] = True
            eintrag["anzahl"] += 1
            ereignisse.append({"kennung": kennung, "status": "neu", "text": text})
    for kennung, eintrag in historisch.items():
        if kennung not in kandidaten:
            if eintrag.get("aktiv"):
                ereignisse.append({"kennung": kennung, "status": "nicht_mehr_beobachtet", "text": eintrag["text"]})
            eintrag["aktiv"] = False
            eintrag["seit"] = None
    return ereignisse


def berichttext(zustand):
    zeilen = ["Tesla-Dashboard: passive 48-Stunden-Prüfung", "",
              f"Beginn: {zustand['von']}", f"Geplantes Ende: {zustand['bis']}",
              f"Letzte Prüfung: {zustand['geprüft_am']}",
              f"Status: {'abgeschlossen' if zustand['abgeschlossen'] else 'läuft'}", ""]
    for eintrag in zustand.get("befunde", {}).values():
        if eintrag["anzahl"]:
            status = "weiterhin beobachtet" if eintrag.get("aktiv") else "zuletzt nicht mehr beobachtet"
            zeilen.append(f"- {eintrag['text']} ({status}; {eintrag['anzahl']} Auftreten)")
    if not any(b["anzahl"] for b in zustand.get("befunde", {}).values()):
        zeilen.append("Bisher keine bestätigten Prüfbefunde; das ist kein Vollständigkeitsnachweis.")
    daten = zustand.get("auswertung") or {}
    zeilen += ["", "Live/Live+ im ausgewerteten Zeitraum:"]
    zeitraum = zustand.get("auswertungszeitraum")
    if zeitraum:
        zeilen.append(f"Zeitraum: {zeitraum['von']} bis {zeitraum['bis']}")
    for profil, wert in daten.get("takt", {}).items():
        zeilen.append(f"{profil}: {wert['bewertung']} ({wert['fahrtstunden']:.3f} Fahrstunden)")
        for feld in ("Location", "VehicleSpeed"):
            messung = wert["felder"][feld]
            median = f"{messung['median_s']:.3f} s" if messung["median_s"] is not None else "nicht messbar"
            p95 = f"{messung['p95_s']:.3f} s" if messung["p95_s"] is not None else "nicht messbar"
            zeilen.append(f"  {feld}: Median {median}, P95 {p95}, "
                          f"Lücken ab 8 s: {messung['lücken_ab_8_s']}")
    vergleich = zustand.get("vergleich")
    if vergleich:
        zeilen += ["", "Kostenmodell, vor Steuern und kein Rechnungsnachweis:"]
        zeitraum = zustand.get("vergleichszeitraum")
        zeilen.append(
            f"Zeitraum: {zeitraum['von']} bis {zeitraum['bis']}"
            if zeitraum else
            "Älterer Vergleich ohne gespeichertes Zeitfenster; kein aktueller Gesamtvergleich."
        )
        zeilen += [
            "Entfallener Heizungsabgleich: "
            f"{vergleich['heizungsersparnis_modell_euro_pro_30_tage']} EUR / 30 Tage.",
            "Profilbereinigte Signal-Kostendifferenz: "
            f"{vergleich['streamdifferenz_profilbereinigt_euro_pro_30_tage']} EUR / 30 Tage.",
            vergleich["einschränkung"],
        ]
    korrekturen = zustand.get("korrekturprüfung") or {}
    zeilen += ["", "Automatische Korrekturprüfung:"]
    for eintrag in korrekturen.get("läufe", []):
        zeilen.append(f"- {eintrag['zeit']}: {eintrag['status']}; {eintrag.get('ergebnis', '')}")
    if not korrekturen.get("läufe"):
        zeilen.append("Keine Korrekturprüfung ausgeführt.")
    zeilen += ["", "Prüfgrenzen:", *GRENZEN,
               *daten.get("warnungen", []), "", "© 2026 Erik Schauer, do1ffe@darc.de"]
    return "\n".join(zeilen) + "\n"


def mail_einreihen(ordner, zustand, tag):
    if tag not in {1, 2}:
        return
    name = f"tagesbericht-{tag}.json"
    if any((ordner / teil / name).exists()
           for teil in ("postausgang", "versendet", "mail-fehlgeschlagen")):
        return
    betreff = f"Tagesbericht {tag}/2 der 48-Stunden-Prüfung"
    inhalt = {"betreff": betreff, "text": berichttext(zustand), "daten": zustand}
    speichern(ordner / "postausgang" / name, inhalt)


def prüfschritt(args, jetzt):
    statuspfad = args.ausgabe / "status.json"
    zustand = json_laden(statuspfad) if statuspfad.exists() else {"befunde": {}, "prüfungen": 0}
    abgeschlossen = jetzt >= args.ende
    bis = min(jetzt, args.ende)
    tag = min(2, int((bis - args.start) // 86400))
    tagesbericht = tag > zustand.get("berichtstag", 0)
    von = args.start if abgeschlossen or tagesbericht else max(args.start, bis - 600)
    kandidaten = {}
    daten = None
    try:
        daten = auswertung.auswerten(args.projekt / "data/monitoring", von, bis)
        kandidaten.update(takt_befunde(daten))
        if daten["quellen"]["lesefehler"]:
            kandidaten["log_lesefehler"] = ("Protokolldateien nicht vollständig lesbar.", 0)
        if not daten["journal"].get("verfügbar"):
            kandidaten["journalzugriff"] = ("Dashboard-Journal nicht lesbar.", 0)
        # Der Tagesvergleich darf historische, bereits erledigte Fehler nicht
        # erneut als aktuelle Störung an die Korrekturprüfung übergeben.
        fehler = journalfehler(max(args.start, bis - 600), bis)
        for name, anzahl in fehler.items():
            if anzahl:
                kandidaten[f"journal:{name}"] = (f"{name} im Dashboard-Journal; siehe lokalen Prüfzeitraum.", 0)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        kandidaten["auswertung"] = (f"Logauswertung unvollständig: {type(exc).__name__}.", 0)
    try:
        cache = json_laden(args.projekt / "data/default/cache.json")
        profil = json_laden(args.projekt / "data/tesla_fleet/telemetry_profile_status.json")
        dienste = dienststatus()
        kandidaten.update(momentbefunde(cache, profil, dienste, jetzt))
        for name, wert in dienste.items():
            vorher = (zustand.get("dienste") or {}).get(name, {})
            if int(wert.get("NRestarts", 0)) > int(vorher.get("NRestarts", 0)):
                kandidaten[f"neustart:{name}"] = (f"Automatischer Neustart von {name} beobachtet.", 0)
        zustand["dienste"] = dienste
        # Frische MQTT-Daten bei länger stehendem Cache-Protokoll sind eine Aufzeichnungslücke.
        statuslog = args.projekt / "data/monitoring/fahrtstatus.ndjson"
        if (frisch(cache.get("fleet_telemetry_received_at"), jetzt, 30)
                and jetzt - statuslog.stat().st_mtime > 120):
            kandidaten["statusprotokoll"] = ("Frische Telemetrie bei stehendem Cache-Protokoll.", 60)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        kandidaten["statuszugriff"] = (f"Lokaler Cache-/Dienststatus nicht prüfbar: {type(exc).__name__}.", 0)
    ereignisse = befunde_fortschreiben(zustand, kandidaten, jetzt)
    zustand.update({"von": auswertung.zeittext(args.start), "bis": auswertung.zeittext(args.ende),
                    "geprüft_am": auswertung.zeittext(jetzt), "abgeschlossen": abgeschlossen,
                    "prüfungen": zustand["prüfungen"] + 1, "auswertung": daten,
                    "auswertungszeitraum": {"von": auswertung.zeittext(von),
                                            "bis": auswertung.zeittext(bis)},
                    "grenzen": GRENZEN, "zusätzliche_fahrzeugabfragen": 0})
    if (abgeschlossen or tagesbericht) and daten:
        try:
            zustand["vergleich"] = auswertung.vergleichen(json_laden(args.referenz), daten)
            zustand["vergleichszeitraum"] = dict(zustand["auswertungszeitraum"])
        except (OSError, ValueError, TypeError, KeyError):
            daten["warnungen"].append("Kostenvergleich nicht möglich: Referenz nicht auswertbar.")
    # Ereignisse und Postausgang vor dem Abschlussmarker schreiben, damit ein Neustart nachholt.
    if ereignisse:
        with (args.ausgabe / "ereignisse.ndjson").open("a", encoding="utf-8") as datei:
            for eintrag in ereignisse:
                datei.write(json.dumps({"zeit": zustand["geprüft_am"], **eintrag}, ensure_ascii=False) + "\n")
    neue = [e for e in ereignisse if e["status"] == "neu"]
    if neue and not abgeschlossen:
        auftrag = {
            "zeit": zustand["geprüft_am"], "ende": zustand["bis"], "befunde": neue,
        }
        kennung = hashlib.sha256(json.dumps(auftrag, sort_keys=True).encode()).hexdigest()
        warteschlange = args.ausgabe / "korrekturaufträge"
        warteschlange.mkdir(exist_ok=True)
        speichern(warteschlange / f"{kennung}.json", auftrag)
    reparaturen = args.ausgabe / "korrekturstatus.json"
    if reparaturen.exists():
        zustand["korrekturprüfung"] = json_laden(reparaturen)
    else:
        zustand["korrekturprüfung"] = {"läufe": []}
    übernahmen = args.ausgabe / "übernahmestatus.json"
    if übernahmen.exists():
        korrekturprüfung = zustand.setdefault("korrekturprüfung", {"läufe": []})
        korrekturprüfung["läufe"].extend(json_laden(übernahmen).get("läufe", []))
    if tagesbericht:
        mail_einreihen(args.ausgabe, zustand, tag)
        zustand["berichtstag"] = tag
    auswertung.atomar_speichern(args.ausgabe / "bericht.txt", berichttext(zustand))
    speichern(statuspfad, zustand)
    if abgeschlossen:
        speichern(args.ausgabe / "abschluss.json", zustand)
    print(f"Passive Prüfung {zustand['geprüft_am']}: {len(ereignisse)} Änderungen; "
          f"abgeschlossen={abgeschlossen}.", flush=True)
    return abgeschlossen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projekt", type=Path, required=True)
    parser.add_argument("--ausgabe", type=Path, required=True)
    parser.add_argument("--referenz", type=Path, required=True)
    parser.add_argument("--start", type=auswertung.zeitwert, required=True)
    parser.add_argument("--ende", type=auswertung.zeitwert, required=True)
    parser.add_argument("--einmal", action="store_true")
    args = parser.parse_args()
    if not 0 < args.ende - args.start <= 48 * 3600:
        parser.error("Überwachung muss auf höchstens 48 Stunden begrenzt sein")
    os.umask(0o077)
    args.ausgabe.mkdir(parents=True, exist_ok=True)
    (args.ausgabe / "postausgang").mkdir(exist_ok=True)
    with (args.ausgabe / "prüfung.lock").open("a") as sperre:
        fcntl.flock(sperre, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while not (args.ausgabe / "abschluss.json").exists():
            jetzt = datetime.now(timezone.utc).timestamp()
            if jetzt > args.start and prüfschritt(args, jetzt):
                break
            if args.einmal:
                break
            time.sleep(max(.1, min(60, args.ende - time.time())))


if __name__ == "__main__":
    main()

# © 2026 Erik Schauer, do1ffe@darc.de
