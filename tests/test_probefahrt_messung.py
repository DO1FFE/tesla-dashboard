import importlib.util
from pathlib import Path


MODULPFAD = Path(__file__).resolve().parents[1] / "tools" / "probefahrt_messung.py"
SPEZIFIKATION = importlib.util.spec_from_file_location(
    "probefahrt_messung",
    MODULPFAD,
)
probefahrt_messung = importlib.util.module_from_spec(SPEZIFIKATION)
SPEZIFIKATION.loader.exec_module(probefahrt_messung)


def test_mqtt_zeile_lesen_erkennt_fleet_feld():
    eintrag = probefahrt_messung.mqtt_zeile_lesen(
        '100.250\ttesla/VIN123/v/Location\t{"latitude":51.0,"longitude":7.0}'
    )

    assert eintrag["empfangen"] == 100.25
    assert eintrag["vin"] == "VIN123"
    assert eintrag["typ"] == "v"
    assert eintrag["feld"] == "Location"
    assert eintrag["wert"]["latitude"] == 51.0


def test_messdaten_auswerten_ermittelt_luecken_und_status():
    zeilen = [
        '100.000\ttesla/VIN123/connectivity\t{"Status":"CONNECTED"}',
        '101.000\ttesla/VIN123/v/Location\t{"latitude":51.0,"longitude":7.0}',
        '102.500\ttesla/VIN123/v/Location\t{"latitude":51.1,"longitude":7.1}',
        '104.000\ttesla/VIN123/v/VehicleSpeed\t50',
    ]

    auswertung = probefahrt_messung.messdaten_auswerten(
        zeilen,
        start=100.0,
        ende=105.0,
    )

    assert auswertung["gesamt"] == 4
    assert auswertung["dauer_s"] == 5.0
    assert auswertung["vins"] == ["VIN123"]
    assert auswertung["verbindungen"][0]["status"] == "CONNECTED"
    assert auswertung["felder"]["Location"]["anzahl"] == 2
    assert auswertung["felder"]["Location"]["max_luecke_s"] == 1.5
    assert auswertung["felder"]["VehicleSpeed"]["letzter_wert"] == 50


def test_messdaten_auswerten_erkennt_getrennte_quelle():
    zeilen = [
        '200.000\ttesla/VIN123/connectivity\t{"Status":"DISCONNECTED"}',
    ]

    auswertung = probefahrt_messung.messdaten_auswerten(
        zeilen,
        start=200.0,
        ende=260.0,
    )

    assert "getrennt" in auswertung["entscheidung"]
    assert "vor der App" in auswertung["entscheidung"]


def test_bericht_enthaelt_live_ansicht_bereiche_und_bewertung():
    auswertung = probefahrt_messung.messdaten_auswerten(
        [
            '100.000\ttesla/VIN123/v/Location\t{"latitude":51.0,"longitude":7.0}',
            '101.000\ttesla/VIN123/v/VehicleSpeed\t50',
        ],
        start=100.0,
        ende=102.0,
    )

    bericht = probefahrt_messung.bericht_erstellen(auswertung, ("bewegung",))

    assert "Live-Ansicht bewegung:" in bericht
    assert "Location: 1" in bericht
    assert "VehicleSpeed: 1" in bericht
    assert "Bewertung:" in bericht


def test_bereiche_auswahl_nutzt_live_ansicht_begriffe():
    assert probefahrt_messung.bereiche_auswahl(
        ["bewegung", "karte", "instrumente"]
    ) == ("bewegung", "karte", "instrumente")
