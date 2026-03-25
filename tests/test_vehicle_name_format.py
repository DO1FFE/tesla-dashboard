import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


def test_fahrzeugname_ohne_doppelte_modellangabe():
    ergebnis = app._formatierter_fahrzeugname("Model Y", "modely", "awd")
    assert ergebnis == "Model Y (AWD)"


def test_bereits_erweiterter_name_bleibt_unveraendert():
    name = "Model Y (Model Y AWD)"
    ergebnis = app._formatierter_fahrzeugname(name, "modely", "awd")
    assert ergebnis == name


def test_fehlende_felder_lassen_name_unveraendert():
    name = "Model Y"
    assert app._formatierter_fahrzeugname(name, "modely", None) == name
    assert app._formatierter_fahrzeugname(name, None, "awd") == name
