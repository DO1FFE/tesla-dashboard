import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


@pytest.fixture(autouse=True)
def isolierte_laufzeitdaten(monkeypatch, tmp_path):
    """Verhindere Zugriffe auf produktive Laufzeitdaten in Tests."""

    datenbankpfad = tmp_path / "v2l-test.db"
    monkeypatch.setattr(app, "_v2l_datenbankpfad", lambda: str(datenbankpfad))
    monkeypatch.setattr(app, "_v2l_aktive_fahrzeuge", set())
    monkeypatch.setattr(app, "_v2l_status_datenbankpfad", None)
    monkeypatch.setattr(app, "PARKTIME_FILE", str(tmp_path / "parktime.json"))
    monkeypatch.setattr(app, "park_start_ms", None)
    monkeypatch.setattr(app, "last_shift_state", None)
