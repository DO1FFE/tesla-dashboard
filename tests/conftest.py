import os
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# Schon während der Test-Sammlung darf kein produktiver Datenpfad entstehen.
_import_daten = tempfile.TemporaryDirectory(prefix="tesla-dashboard-tests-")
os.environ["TESLA_DASHBOARD_DATA_DIR"] = _import_daten.name
os.environ["STATISTICS_DB_PATH"] = str(pathlib.Path(_import_daten.name) / "statistics.db")
os.environ["DISABLE_STATISTICS_AGGREGATION"] = "1"

import app


@pytest.fixture(autouse=True)
def isolierte_laufzeitdaten(monkeypatch, tmp_path):
    """Verhindere Zugriffe auf produktive Laufzeitdaten in Tests."""

    monkeypatch.setenv("TESLA_DASHBOARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STATISTICS_DB_PATH", str(tmp_path / "statistics.db"))
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(app, "STAT_FILE", str(tmp_path / "statistics.json"))
    monkeypatch.setattr(app, "STATISTICS_DB", str(tmp_path / "statistics.db"))
    monkeypatch.setattr(app, "DISABLE_STATISTICS_AGGREGATION", True)
    monkeypatch.setattr(app, "_aggregation_thread", None)
    datenbankpfad = tmp_path / "v2l-test.db"
    monkeypatch.setattr(app, "_v2l_datenbankpfad", lambda: str(datenbankpfad))
    monkeypatch.setattr(app, "_v2l_aktive_fahrzeuge", set())
    monkeypatch.setattr(app, "_v2l_status_datenbankpfad", None)
    monkeypatch.setattr(app, "PARKTIME_FILE", str(tmp_path / "parktime.json"))
    monkeypatch.setattr(app, "park_start_ms", None)
    monkeypatch.setattr(app, "last_shift_state", None)
    monkeypatch.setattr(
        app, "_telemetrie_diagnose_datenbankpfad",
        lambda: str(tmp_path / "telemetrie-diagnose.sqlite"),
    )


# © 2026 Erik Schauer, do1ffe@darc.de
