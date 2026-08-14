import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


@pytest.fixture(autouse=True)
def isolierte_v2l_datenbank(monkeypatch, tmp_path):
    """Verhindere Zugriffe auf produktive V2L-Sitzungen in Tests."""

    datenbankpfad = tmp_path / "v2l-test.db"
    monkeypatch.setattr(app, "_v2l_datenbankpfad", lambda: str(datenbankpfad))
    monkeypatch.setattr(app, "_v2l_aktive_fahrzeuge", set())
    monkeypatch.setattr(app, "_v2l_status_datenbankpfad", None)
