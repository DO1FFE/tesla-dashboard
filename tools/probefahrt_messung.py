#!/usr/bin/env python3
"""Messe frische Fleet-Telemetrie direkt am MQTT-Broker."""

import argparse
import json
import os
import selectors
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


MESSPROFILE = {
    "bewegung": (
        "Location",
        "VehicleSpeed",
        "Gear",
        "GpsHeading",
        "PedalPosition",
        "PackCurrent",
        "PackVoltage",
    ),
    "navigation": (
        "DestinationLocation",
        "DestinationName",
        "ExpectedEnergyPercentAtTripArrival",
        "MilesToArrival",
        "MinutesToArrival",
        "RouteTrafficMinutesDelay",
        "RouteLine",
    ),
    "laden": (
        "ChargeState",
        "DetailedChargeState",
        "BatteryLevel",
        "Soc",
        "ChargeRateMilePerHour",
        "ChargerPower",
        "ChargePort",
    ),
    "basis": (
        "InsideTemp",
        "OutsideTemp",
        "Odometer",
        "Locked",
        "DoorState",
        "CenterDisplay",
    ),
}

KRITISCHE_BEWEGUNGSFELDER = {
    "Location",
    "VehicleSpeed",
    "Gear",
    "GpsHeading",
}


def zeitstempel():
    """Erzeuge einen UTC-Zeitstempel für Dateinamen."""

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def payload_lesen(payload):
    """Dekodiere MQTT-Nutzdaten, falls sie JSON enthalten."""

    try:
        return json.loads(payload)
    except Exception:
        return payload


def mqtt_zeile_lesen(zeile, topic_basis="tesla"):
    """Lese eine mosquitto_sub-Ausgabezeile mit Zeit, Topic und Payload."""

    teile = zeile.rstrip("\n").split("\t", 2)
    if len(teile) != 3:
        return None
    zeit_roh, topic, payload = teile
    try:
        empfangen = float(zeit_roh)
    except ValueError:
        return None

    topic_teile = topic.strip("/").split("/")
    if len(topic_teile) < 3 or topic_teile[0] != topic_basis:
        return None

    typ = topic_teile[2]
    eintrag = {
        "empfangen": empfangen,
        "topic": topic,
        "vin": topic_teile[1],
        "typ": typ,
        "payload": payload,
        "wert": payload_lesen(payload),
    }
    if typ == "v" and len(topic_teile) >= 4:
        eintrag["feld"] = "/".join(topic_teile[3:])
    return eintrag


def luecken_berechnen(zeiten):
    """Berechne die größte Lücke zwischen frischen MQTT-Nachrichten."""

    if len(zeiten) < 2:
        return None
    return max(zeiten[index] - zeiten[index - 1] for index in range(1, len(zeiten)))


def messdaten_auswerten(zeilen, topic_basis="tesla", start=None, ende=None):
    """Werte die gemessenen MQTT-Zeilen nach Feldern und Lücken aus."""

    ereignisse = []
    for zeile in zeilen:
        eintrag = mqtt_zeile_lesen(zeile, topic_basis=topic_basis)
        if eintrag is not None:
            ereignisse.append(eintrag)

    if start is None and ereignisse:
        start = min(eintrag["empfangen"] for eintrag in ereignisse)
    if ende is None and ereignisse:
        ende = max(eintrag["empfangen"] for eintrag in ereignisse)
    if start is None:
        start = time.time()
    if ende is None:
        ende = start

    felder = defaultdict(list)
    letzte_werte = {}
    verbindungen = []
    vins = set()

    for eintrag in ereignisse:
        vins.add(eintrag["vin"])
        if eintrag["typ"] == "v" and "feld" in eintrag:
            feld = eintrag["feld"]
            felder[feld].append(eintrag["empfangen"])
            letzte_werte[feld] = eintrag["wert"]
        elif eintrag["typ"] == "connectivity":
            wert = eintrag["wert"]
            status = None
            if isinstance(wert, dict):
                status = wert.get("Status") or wert.get("status")
            verbindungen.append({
                "empfangen": eintrag["empfangen"],
                "sekunde": round(eintrag["empfangen"] - start, 3),
                "status": status,
                "wert": wert,
            })

    feld_summary = {}
    for feld, zeiten in sorted(felder.items()):
        zeiten.sort()
        feld_summary[feld] = {
            "anzahl": len(zeiten),
            "erste_sekunde": round(zeiten[0] - start, 3),
            "letzte_sekunde": round(zeiten[-1] - start, 3),
            "max_luecke_s": (
                None if luecken_berechnen(zeiten) is None
                else round(luecken_berechnen(zeiten), 3)
            ),
            "letzter_wert": letzte_werte.get(feld),
        }

    return {
        "start": start,
        "ende": ende,
        "dauer_s": round(max(0.0, ende - start), 3),
        "gesamt": len(ereignisse),
        "vins": sorted(vins),
        "felder": feld_summary,
        "verbindungen": verbindungen,
        "entscheidung": entscheidung_bilden(feld_summary, verbindungen, len(ereignisse)),
    }


def entscheidung_bilden(felder, verbindungen, gesamt):
    """Leite aus der Messung eine knappe technische Bewertung ab."""

    if gesamt == 0:
        return "Keine frischen MQTT-Nachrichten im Messfenster."

    if verbindungen:
        letzter_status = str(verbindungen[-1].get("status") or "").lower()
        if letzter_status == "disconnected" and not felder:
            return "Fahrzeug/Fleet-Verbindung ist getrennt; die Verzögerung liegt vor der App."

    bewegungs_counts = {
        feld: felder.get(feld, {}).get("anzahl", 0)
        for feld in KRITISCHE_BEWEGUNGSFELDER
    }
    if sum(bewegungs_counts.values()) == 0:
        return "Keine frischen Bewegungsfelder; Browser und Flask können nichts schneller anzeigen."

    groesste_luecke = 0.0
    for feld in KRITISCHE_BEWEGUNGSFELDER:
        luecke = felder.get(feld, {}).get("max_luecke_s")
        if luecke is not None:
            groesste_luecke = max(groesste_luecke, luecke)
    if groesste_luecke > 5.0:
        return f"Bewegungsdaten kommen an, aber mit großen MQTT-Lücken bis {groesste_luecke:.1f} s."
    if groesste_luecke > 2.5:
        return f"Bewegungsdaten kommen an, aber nicht durchgehend echtzeitnah: Lücken bis {groesste_luecke:.1f} s."
    return "MQTT-Bewegungsdaten sehen echtzeitnah aus; bei Browserverzug danach App/SSE prüfen."


def wert_kurz(wert):
    """Kürze lange Werte für die Konsolenausgabe."""

    text = json.dumps(wert, ensure_ascii=False, sort_keys=True)
    if len(text) > 80:
        return text[:77] + "..."
    return text


def bericht_erstellen(auswertung, profile):
    """Erzeuge einen kompakten Messbericht für die Konsole."""

    zeilen = [
        f"Messdauer: {auswertung['dauer_s']:.1f} s",
        f"Frische MQTT-Nachrichten: {auswertung['gesamt']}",
        f"VINs: {', '.join(auswertung['vins']) if auswertung['vins'] else '-'}",
    ]
    if auswertung["verbindungen"]:
        zeilen.append("Connectivity:")
        for eintrag in auswertung["verbindungen"][-8:]:
            status = eintrag.get("status") or "unbekannt"
            zeilen.append(f"  +{eintrag['sekunde']:.1f}s {status}")

    felder = auswertung["felder"]
    for profil in profile:
        profil_felder = MESSPROFILE[profil]
        zeilen.append(f"Profil {profil}:")
        for feld in profil_felder:
            daten = felder.get(feld)
            if not daten:
                zeilen.append(f"  {feld}: 0")
                continue
            luecke = daten["max_luecke_s"]
            luecken_text = "-" if luecke is None else f"{luecke:.1f}s"
            zeilen.append(
                f"  {feld}: {daten['anzahl']} | letzte +{daten['letzte_sekunde']:.1f}s "
                f"| max. Lücke {luecken_text} | Wert {wert_kurz(daten['letzter_wert'])}"
            )

    zeilen.append(f"Bewertung: {auswertung['entscheidung']}")
    return "\n".join(zeilen)


def profile_auswahl(rohdaten):
    """Lese die gewünschten Auswertungsprofile aus der Kommandozeile."""

    if "alle" in rohdaten:
        return tuple(MESSPROFILE)
    gewaehlt = []
    for profil in rohdaten:
        if profil not in MESSPROFILE:
            raise SystemExit(f"Unbekanntes Profil: {profil}")
        if profil not in gewaehlt:
            gewaehlt.append(profil)
    return tuple(gewaehlt)


def vorhandene_datei_auswerten(args):
    """Werte eine bereits vorhandene Messdatei erneut aus."""

    pfad = Path(args.auswerten)
    zeilen = pfad.read_text(encoding="utf-8", errors="replace").splitlines()
    auswertung = messdaten_auswerten(zeilen, topic_basis=args.topic_basis)
    print(bericht_erstellen(auswertung, profile_auswahl(args.profil)))
    if args.json_datei:
        Path(args.json_datei).write_text(
            json.dumps(auswertung, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def messung_starten(args):
    """Starte mosquitto_sub und sammle frische MQTT-Nachrichten."""

    programm = shutil.which("mosquitto_sub")
    if not programm:
        raise SystemExit("mosquitto_sub ist nicht installiert oder nicht im PATH.")

    ausgabe = Path(args.ausgabe or f"/tmp/fleet_mqtt_probefahrt_{zeitstempel()}.tsv")
    ausgabe.parent.mkdir(parents=True, exist_ok=True)
    befehl = [
        programm,
        "-h",
        args.host,
        "-p",
        str(args.port),
        "-t",
        args.topic,
        "-F",
        "%U\t%t\t%p",
    ]
    if not args.retained:
        befehl.insert(1, "-R")

    start = time.time()
    ende = start + args.dauer
    zeilen = []
    prozess = subprocess.Popen(
        befehl,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    selector = selectors.DefaultSelector()
    assert prozess.stdout is not None
    selector.register(prozess.stdout, selectors.EVENT_READ)

    try:
        with ausgabe.open("w", encoding="utf-8") as f:
            while time.time() < ende and prozess.poll() is None:
                timeout = max(0.1, min(1.0, ende - time.time()))
                for key, _mask in selector.select(timeout):
                    zeile = key.fileobj.readline()
                    if not zeile:
                        continue
                    f.write(zeile)
                    f.flush()
                    zeilen.append(zeile.rstrip("\n"))
    finally:
        if prozess.poll() is None:
            prozess.terminate()
            try:
                prozess.wait(timeout=3)
            except subprocess.TimeoutExpired:
                prozess.kill()
                prozess.wait(timeout=3)

    fehler = ""
    if prozess.stderr is not None:
        fehler = prozess.stderr.read().strip()
    auswertung = messdaten_auswerten(
        zeilen,
        topic_basis=args.topic_basis,
        start=start,
        ende=time.time(),
    )
    json_datei = Path(args.json_datei or ausgabe.with_suffix(".json"))
    json_datei.write_text(
        json.dumps(auswertung, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Messdatei: {ausgabe}")
    print(f"JSON: {json_datei}")
    if fehler:
        print(f"mosquitto_sub stderr: {fehler}", file=sys.stderr)
    print(bericht_erstellen(auswertung, profile_auswahl(args.profil)))


def parser_erstellen():
    """Erstelle den Kommandozeilenparser."""

    parser = argparse.ArgumentParser(
        description="Probefahrt-Messung für Tesla Fleet Telemetry über MQTT.",
    )
    parser.add_argument("--dauer", type=float, default=300.0, help="Messdauer in Sekunden.")
    parser.add_argument(
        "--host",
        default=os.getenv("TESLA_FLEET_TELEMETRY_MQTT_HOST", "127.0.0.1"),
        help="MQTT-Host.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("TESLA_FLEET_TELEMETRY_MQTT_PORT", "1884")),
        help="MQTT-Port.",
    )
    parser.add_argument("--topic", default="tesla/#", help="MQTT-Topic.")
    parser.add_argument("--topic-basis", default="tesla", help="Topic-Basis.")
    parser.add_argument("--ausgabe", help="TSV-Ausgabedatei.")
    parser.add_argument("--json-datei", help="JSON-Auswertung schreiben.")
    parser.add_argument(
        "--profil",
        nargs="+",
        default=["bewegung", "navigation", "laden"],
        help="Auswertungsprofile: bewegung navigation laden basis alle.",
    )
    parser.add_argument(
        "--retained",
        action="store_true",
        help="Retained MQTT-Werte einbeziehen. Standardmäßig werden nur frische Werte gemessen.",
    )
    parser.add_argument("--auswerten", help="Vorhandene TSV-Messdatei auswerten.")
    return parser


def main(argv=None):
    """Starte Messung oder Auswertung."""

    args = parser_erstellen().parse_args(argv)
    if args.auswerten:
        vorhandene_datei_auswerten(args)
    else:
        messung_starten(args)


if __name__ == "__main__":
    main()


# © 2026 Erik Schauer, do1ffe@darc.de
