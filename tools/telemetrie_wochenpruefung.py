#!/usr/bin/env python3
"""Einmalige, ausschließlich lokale Auswertung der Kosten- und Fahrtprotokolle."""

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
from zoneinfo import ZoneInfo


FAHRFELDER = ("Location", "VehicleSpeed", "Gear", "GpsHeading")
PROFILE = ("live", "live_extended", "parked", "charging", "unbekannt")
PREIS_ABRUF = 4.91 / 2456
PREIS_SIGNAL = 14.80 / 2222380
BERLIN = ZoneInfo("Europe/Berlin")


def zeitwert(text):
    zeit = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if zeit.tzinfo is None:
        raise ValueError("Zeitangaben benötigen eine Zeitzone")
    return zeit.timestamp()


def zeittext(zeit):
    return datetime.fromtimestamp(zeit, BERLIN).isoformat(timespec="seconds")


def protokollzeilen(ordner, stamm, start, fehler):
    """Lese rotierte Dateien chronologisch, einschließlich eines Tages Vorlauf."""
    dateien = sorted(ordner.glob(stamm + "*"), key=lambda p: (
        p.name == stamm, p.name,
    ))
    for pfad in dateien:
        if not pfad.is_file():
            continue
        suffix = pfad.name[len(stamm):]
        if suffix:
            try:
                rotation = datetime.strptime(suffix[1:9], "%Y%m%d").replace(
                    tzinfo=timezone.utc,
                ).timestamp()
            except ValueError:
                continue
            if rotation < start - 86400:
                continue
        fehler["dateien"].append(str(pfad))
        try:
            with (gzip.open(pfad, "rt", encoding="utf-8")
                  if pfad.suffix == ".gz" else pfad.open(encoding="utf-8")) as datei:
                yield from datei
        except (OSError, EOFError, UnicodeError) as exc:
            fehler["lesefehler"].append(f"{pfad.name}: {type(exc).__name__}")


def fenster_anhängen(fenster, start, ende, profil):
    if ende <= start:
        return
    if fenster and fenster[-1][1] == start and fenster[-1][2] == profil:
        fenster[-1] = (fenster[-1][0], ende, profil)
    else:
        fenster.append((start, ende, profil))


def nutzungsfenster(ereignisse, start, ende):
    """Verbinde Profil, Fahrzustand und Fahrerbelegung ohne neue Datenabfrage."""
    profil, cache, fahrer = "unbekannt", None, None
    cachezeit, vorher = 0, start
    fahrten, heizung = [], []
    profildauer = Counter()
    unbelegt = 0.0
    sortiert = sorted(ereignisse, key=lambda e: (e[0], e[1]))
    for zeit, art, wert in sortiert + [(ende, 3, None)]:
        links, rechts = max(start, vorher), min(ende, zeit)
        if rechts > links:
            profildauer[profil] += rechts - links
            gültig_bis = min(rechts, cachezeit + 300)
            unbelegt += rechts - max(links, gültig_bis)
            if cache and gültig_bis > links:
                state, gang, tempo, empfang, tempozeit = cache
                fährt = (
                    gang in {"D", "R"}
                    and isinstance(tempo, (int, float)) and tempo > 0.5
                )
                if state == "online" and fährt:
                    fenster_anhängen(fahrten, links, gültig_bis, profil)
                if state == "online" and empfang <= links:
                    frisch_bis = min(gültig_bis, empfang + 20)
                    if fährt and tempozeit <= links:
                        frisch_bis = min(frisch_bis, tempozeit + 15)
                    elif gang != "P" or fahrer is not True:
                        frisch_bis = links
                    fenster_anhängen(heizung, links, frisch_bis, "heizung")
        if art == 0:
            profil = wert if wert in PROFILE else "unbekannt"
        elif art == 1:
            cache, cachezeit = wert, zeit
        elif art == 2:
            fahrer = wert
        vorher = zeit
    return fahrten, heizung, dict(profildauer), unbelegt


def modellabrufe(fenster, abstand):
    """Modelliere den früheren Fünfsekunden-Worker ohne angenommene HTTP-Erfolge."""
    zuletzt, anzahl = 0, 0
    for start, ende, _ in fenster:
        zeit = math.ceil(max(start, zuletzt + abstand) / 5) * 5
        while zeit < ende:
            anzahl += 1
            zuletzt, zeit = zeit, zeit + abstand
    return anzahl


def takt_auswerten(fenster, zeitpunkte):
    """Zähle auch ausbleibende Meldungen am Anfang und Ende einer Fahrphase."""
    ergebnis = {}
    for profil in ("live", "live_extended"):
        abschnitte = [(a, b) for a, b, p in fenster if p == profil]
        dauer = sum(b - a for a, b in abschnitte)
        felder = {}
        for feld in FAHRFELDER:
            zeiten = sorted(set(zeitpunkte.get(feld, [])))
            deltas, lücken = [], []
            abgedeckt, meldungen = 0.0, 0
            for start, ende in abschnitte:
                werte = zeiten[bisect_left(zeiten, start):bisect_left(zeiten, ende)]
                meldungen += len(werte)
                deltas.extend(b - a for a, b in zip(werte, werte[1:]))
                grenzen = [start, *werte, ende]
                for a, b in zip(grenzen, grenzen[1:]):
                    if b - a > 5:
                        lücken.append((b - a, a, b))
                abgedeckt += sum(
                    min(2, b - a) for a, b in zip(werte, [*werte[1:], ende])
                )
            sortiert = sorted(deltas)
            felder[feld] = {
                "meldungen": meldungen,
                "intervalle": len(deltas),
                "median_s": statistics.median(deltas) if deltas else None,
                "p95_s": (
                    sortiert[math.ceil(len(sortiert) * .95) - 1]
                    if deltas else None
                ),
                "anteil_05_bis_15_s_prozent": (
                    100 * sum(.5 <= d <= 1.5 for d in deltas) / len(deltas)
                    if deltas else None
                ),
                "frischeabdeckung_prozent": (
                    100 * abgedeckt / dauer if dauer else None
                ),
                "lücken_über_5_s": len(lücken),
                "lücken_ab_8_s": sum(d >= 8 for d, _, _ in lücken),
                "größte_lücken": [
                    {"dauer_s": round(d, 3), "von": zeittext(a), "bis": zeittext(b)}
                    for d, a, b in sorted(lücken, reverse=True)[:10]
                ],
            }
        hauptfelder = [felder[f] for f in ("Location", "VehicleSpeed")]
        if dauer < 30 or any(f["intervalle"] < 10 for f in hauptfelder):
            bewertung = "nicht beurteilbar: zu wenige Fahrdaten"
        elif all(.5 <= f["median_s"] <= 1.5 and f["p95_s"] <= 2
                 and f["frischeabdeckung_prozent"] >= 90
                 and not f["lücken_über_5_s"] for f in hauptfelder):
            bewertung = "Sekundentakt in den protokollierten Fahrphasen belegt"
        else:
            bewertung = "Auffälligkeiten: Sekundentakt nicht durchgehend belegt"
        ergebnis[profil] = {
            "fahrtstunden": dauer / 3600, "bewertung": bewertung, "felder": felder,
        }
    return ergebnis


def journal_auswerten(start, ende):
    muster = {
        "heizungsfehler": "Lenkradheizung konnte nicht abgeglichen werden",
        "ersatzabfrage_fehlerpause": "Ersatzabfragen für",
        "alte_positionsfehler": (
            "Position bei Stream-Wiederherstellung nicht verfügbar"
        ),
        "alte_vollabfragefehler": (
            "Vollständige vehicle_data bei Stream-Wiederherstellung nicht verfügbar"
        ),
        "abrechnungssperre": "EXCEEDED_LIMIT",
    }
    try:
        antwort = subprocess.run([
            "/usr/bin/journalctl", "-u", "tesla-dashboard.service",
            "--since", f"@{int(start)}", "--until", f"@{int(ende)}",
            "--no-pager", "--output=cat",
        ], capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"verfügbar": False, "hinweis": type(exc).__name__}
    return {
        "verfügbar": antwort.returncode == 0,
        "hinweis": "Nur vorhandene Meldungen; kein vollständiges Abruf- oder Abrechnungsjournal.",
        "anzahl": {name: antwort.stdout.count(text) for name, text in muster.items()},
    }


def auswerten(ordner, start, ende):
    if ende <= start:
        raise ValueError("Das Ende muss nach dem Anfang liegen")
    fehler = {"dateien": [], "lesefehler": [], "ungültige_zeilen": 0}
    ereignisse, profilpunkte = [], []
    rest = defaultdict(set)
    cacheanzahl = 0
    for zeile in protokollzeilen(ordner, "fahrtstatus.ndjson", start, fehler):
        try:
            daten = json.loads(zeile)
            zeit = zeitwert(daten["beobachtet_am_utc"])
            if not start - 86400 <= zeit < ende:
                continue
            if daten.get("quelle") == "profil":
                profil = daten.get("current") or "unbekannt"
                ereignisse.append((zeit, 0, profil))
                profilpunkte.append((zeit, profil))
            elif daten.get("quelle") == "cache":
                drive = daten.get("drive") or {}
                ereignisse.append((zeit, 1, (
                    daten.get("state"), drive.get("shift_state"), drive.get("speed"),
                    (daten.get("telemetrie_empfangen_am") or 0) / 1000,
                    ((daten.get("feld_empfangen_am") or {}).get("VehicleSpeed") or 0) / 1000,
                )))
                if zeit >= start:
                    cacheanzahl += 1
                    for feld, wert in (daten.get("rest_abgleich") or {}).items():
                        if isinstance(wert, (int, float)) and start <= wert / 1000 < ende:
                            rest[feld].add(wert)
        except (ValueError, KeyError, TypeError, AttributeError):
            fehler["ungültige_zeilen"] += 1
    profilpunkte.sort()
    profilzeiten = [t for t, _ in profilpunkte]
    gültig, ungültig, tpms = Counter(), Counter(), Counter()
    fahrzeiten = defaultdict(list)
    vorher = {}
    fahrzeuge = set()
    mqtt_erster, mqtt_letzter = None, None
    for zeile in protokollzeilen(ordner, "fleet-mqtt.tsv", start, fehler):
        try:
            textzeit, topic, payload = zeile.rstrip("\n").split("\t", 2)
            zeit = float(textzeit)
            if not math.isfinite(zeit) or not start - 86400 <= zeit < ende:
                continue
            teile = topic.split("/")
            if len(teile) != 4 or teile[2] != "v":
                continue
            wert = json.loads(payload)
            feld = teile[-1]
            if feld == "DriverSeatOccupied":
                ereignisse.append((zeit, 2, wert))
            if zeit < start:
                vorher[(teile[1], feld)] = wert
                continue
            fahrzeuge.add(teile[1])
            mqtt_erster = zeit if mqtt_erster is None else min(mqtt_erster, zeit)
            mqtt_letzter = zeit if mqtt_letzter is None else max(mqtt_letzter, zeit)
            index = bisect_right(profilzeiten, zeit) - 1
            profil = profilpunkte[index][1] if index >= 0 else "unbekannt"
            if wert is None or isinstance(wert, dict) and wert.get("invalid") is True:
                ungültig[profil] += 1
            else:
                gültig[profil] += 1
                if feld in FAHRFELDER:
                    fahrzeiten[feld].append(zeit)
                if feld.startswith("Tpms") and vorher.get((teile[1], feld)) == wert:
                    tpms[profil] += 1
            vorher[(teile[1], feld)] = wert
        except (ValueError, TypeError):
            fehler["ungültige_zeilen"] += 1
    fahrten, heizung, profildauer, unbelegt = nutzungsfenster(ereignisse, start, ende)
    warnungen = list(fehler["lesefehler"])
    if cacheanzahl == 0 or mqtt_erster is None:
        warnungen.append("Cache- oder MQTT-Daten fehlen; keine belastbare Bestätigung möglich.")
    if len(fahrzeuge) > 1:
        warnungen.append(
            "Mehrere Fahrzeuge im MQTT-Protokoll: Zuordnung nicht eindeutig; "
            "kein Taktbeleg."
        )
    if unbelegt > 300:
        warnungen.append(
            "Längere Cache-Protokolllücken: Schlaf und fehlende Aufzeichnung "
            "nicht sicher unterscheidbar."
        )
    if fehler["ungültige_zeilen"]:
        warnungen.append("Ungültige Protokollzeilen wurden übersprungen.")
    takt = takt_auswerten(fahrten, fahrzeiten)
    if len(fahrzeuge) > 1:
        for wert in takt.values():
            wert["bewertung"] = "nicht beurteilbar: mehrere Fahrzeuge"
    return {
        "von": zeittext(start), "bis": zeittext(ende), "tage": (ende - start) / 86400,
        "cache_einträge": cacheanzahl, "mqtt_erster": mqtt_erster, "mqtt_letzter": mqtt_letzter,
        "profilstunden": {p: s / 3600 for p, s in profildauer.items()},
        "gültige_signale": dict(gültig), "ungültige_signale": dict(ungültig),
        "tpms_unveränderte_gültige_signale": dict(tpms),
        "heizungsbedarf_stunden": sum(b - a for a, b, _ in heizung) / 3600,
        "modellabrufe_30s": modellabrufe(heizung, 30),
        "modellabrufe_60s": modellabrufe(heizung, 60),
        "rest_zeitpunkte": {f: len(t) for f, t in rest.items()},
        "fahrtstunden_ohne_liveprofil": sum(
            b - a for a, b, p in fahrten if p not in {"live", "live_extended"}
        ) / 3600,
        "takt": takt, "journal": journal_auswerten(start, ende),
        "quellen": fehler, "warnungen": warnungen,
    }


def vergleichen(vorher, nachher):
    faktor = 30 / nachher["tage"]
    belegbar = nachher["cache_einträge"] > 0 and nachher["mqtt_erster"] is not None
    heizung = (
        nachher["modellabrufe_60s"] * PREIS_ABRUF * faktor if belegbar else None
    )
    streamdifferenz = 0.0
    fehlende_profile = []
    for profil, stunden in nachher["profilstunden"].items():
        basis = vorher["profilstunden"].get(profil, 0)
        if basis <= 0 or profil == "unbekannt":
            if stunden > 0:
                fehlende_profile.append(profil)
            continue
        erwartet = vorher["gültige_signale"].get(profil, 0) / basis * stunden
        streamdifferenz += erwartet - nachher["gültige_signale"].get(profil, 0)
    stream_euro = streamdifferenz * PREIS_SIGNAL * faktor
    return {
        "preisgrundlage": (
            "Nutzer-Screenshot vom 23.10.2026; vor Steuern; "
            "kein neuer Abrechnungsabruf"
        ),
        "euro_pro_abruf": PREIS_ABRUF, "euro_pro_signal": PREIS_SIGNAL,
        "heizungsersparnis_modell_euro_pro_30_tage": heizung,
        "heizung_schätzung_7_bis_9_euro_erreicht": (
            7 <= heizung <= 9 if heizung is not None else None
        ),
        "streamdifferenz_profilbereinigt_euro_pro_30_tage": (
            stream_euro if belegbar and not fehlende_profile else None
        ),
        "nicht_vergleichbare_profile": fehlende_profile,
        "abrechnungsgenau_belegt": False,
        "einschränkung": (
            "REST-Erfolge der Heizungsabfragen wurden nicht vollständig protokolliert. "
            "Entfallene Abrufe sind ein Modell, kein Rechnungsnachweis. Signalzahlen sind "
            "lokale MQTT-Meldungen, keine bestätigten Abrechnungseinheiten. Profilbereinigung "
            "gleicht Profilzeiten aus, nicht Fahrgeschwindigkeit, Klima oder "
            "Mobilfunkbedingungen. "
            "Fehlerantworten werden nicht als kostenpflichtige Abrufe angerechnet."
        ),
    }


def berichttext(vorher, nachher, vergleich):
    heizung = vergleich["heizungsersparnis_modell_euro_pro_30_tage"]
    heizungstext = f"{heizung:.2f} EUR" if heizung is not None else "nicht beurteilbar"
    erwartet = vergleich["heizung_schätzung_7_bis_9_euro_erreicht"]
    erwartungstext = {True: "ja", False: "nein", None: "nicht beurteilbar"}[erwartet]
    zeilen = [
        "Tesla-Telemetrie: einmalige Wochenprüfung", "",
        f"Referenz: {vorher['von']} bis {vorher['bis']}",
        f"Nachher: {nachher['von']} bis {nachher['bis']}",
        "Nur vorhandene lokale Logs gelesen. Keine Fahrzeugabfragen oder Profiländerungen.", "",
        "Einsparungen (vor Steuern, auf 30 Tage hochgerechnet):",
        f"- Heizungsabgleich 60 s entfällt, Modell: {heizungstext}.",
        f"- Erwartete 7 bis 9 EUR im Modell erreicht: {erwartungstext}.",
        f"- Relevante Nutzung: {nachher['heizungsbedarf_stunden']:.2f} h; "
        f"modellierte entfallene Abrufe: {nachher['modellabrufe_60s']}.",
    ]
    stream = vergleich["streamdifferenz_profilbereinigt_euro_pro_30_tage"]
    zeilen.append("- Signal-Kostendifferenz bei vergleichbarer Profilnutzung: " + (
        f"{stream:.2f} EUR weniger." if stream is not None
        else "nicht beurteilbar (fehlende Daten oder Profilreferenz)."
    ))
    zeilen += ["", vergleich["einschränkung"], "", "Live-Takt während protokollierter Bewegung:"]
    for profil, daten in nachher["takt"].items():
        zeilen.append(f"{profil}: {daten['bewertung']} ({daten['fahrtstunden']:.2f} h)")
        for feld, messung in daten["felder"].items():
            median = messung["median_s"]
            p95 = messung["p95_s"]
            mediantext = f"{median:.3f} s" if median is not None else "nicht messbar"
            p95text = f"{p95:.3f} s" if p95 is not None else "nicht messbar"
            zeilen.append(
                f"  {feld}: {messung['meldungen']} Meldungen; Median {mediantext}; "
                f"P95 {p95text}; Lücken >5 s: {messung['lücken_über_5_s']}; "
                f"davon >=8 s: {messung['lücken_ab_8_s']}."
            )
            for lücke in messung["größte_lücken"][:3]:
                zeilen.append(f"    {lücke['von']} bis {lücke['bis']}: {lücke['dauer_s']} s")
    zeilen += [
        f"Bewegung ohne Live/Live+: {nachher['fahrtstunden_ohne_liveprofil']:.3f} h.",
        "Maßstab: Median 0,5-1,5 s, P95 <=2 s, Frischeabdeckung >=90 %, keine Lücke >5 s.",
        "Stillstand und Camp-Mode ohne Bewegung beweisen keinen Sekundentakt: "
        "unveränderte Werte dürfen ausbleiben.",
        "Ein Empfangslücken-Befund unterscheidet nicht sicher Fahrzeug-, "
        "Mobilfunk- und Monitorfehler.",
        "", "Protokollierte REST-Abgleiche (keine vollständige Abrufzählung):",
        f"Referenz: {vorher['rest_zeitpunkte']}", f"Nachher: {nachher['rest_zeitpunkte']}",
        f"Fehlermeldungen: {nachher['journal']}", "", "Datenqualität:",
        *[f"- Referenz: {w}" for w in vorher["warnungen"]],
        *[f"- Nachher: {w}" for w in nachher["warnungen"]],
        "Vollständige Kennzahlen und Quellen stehen in bericht.json.", "",
        "© 2026 Erik Schauer, do1ffe@darc.de",
    ]
    return "\n".join(zeilen) + "\n"


def atomar_speichern(pfad, inhalt):
    temporär = pfad.with_suffix(pfad.suffix + ".tmp")
    with temporär.open("w", encoding="utf-8") as datei:
        datei.write(inhalt)
        datei.flush()
        os.fsync(datei.fileno())
    temporär.replace(pfad)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--start", type=zeitwert, required=True)
    parser.add_argument("--ende", type=zeitwert, required=True)
    parser.add_argument("--ausgabe", type=Path, required=True)
    parser.add_argument("--referenz", type=Path)
    args = parser.parse_args()
    if args.ende > datetime.now(timezone.utc).timestamp() + 1:
        parser.error("Ein noch nicht vergangener Zeitraum darf nicht als geprüft gelten")
    os.umask(0o077)
    args.ausgabe.mkdir(parents=True, exist_ok=True)
    ziel = args.ausgabe / ("bericht.json" if args.referenz else "referenz.json")
    if ziel.exists():
        print(f"Bereits abgeschlossen: {ziel}")
        return
    daten = auswerten(args.logs, args.start, args.ende)
    if args.referenz:
        with args.referenz.open(encoding="utf-8") as datei:
            vorher = json.load(datei)
        vergleich = vergleichen(vorher, daten)
        atomar_speichern(args.ausgabe / "bericht.txt", berichttext(vorher, daten, vergleich))
        daten = {"vorher": vorher, "nachher": daten, "vergleich": vergleich}
    # JSON wird zuletzt geschrieben und dient dem Timer als Abschlussnachweis.
    atomar_speichern(ziel, json.dumps(daten, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(f"Gespeichert: {ziel}")


if __name__ == "__main__":
    main()

# © 2026 Erik Schauer, do1ffe@darc.de
