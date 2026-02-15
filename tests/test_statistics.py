import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


def test_compute_statistics_nutzt_beobachtete_zeit(monkeypatch, tmp_path):
    statistik_datei = tmp_path / "statistics.json"

    monkeypatch.setattr(app, "STAT_FILE", str(statistik_datei))
    monkeypatch.setattr(app, "_default_vehicle_id", "demo")
    monkeypatch.setattr(app, "default_vehicle_id", lambda: "demo")
    monkeypatch.setattr(app, "_load_existing_statistics", lambda filename=None: {})
    monkeypatch.setattr(app, "_load_state_entries", lambda vehicle_id=None: [])
    monkeypatch.setattr(
        app,
        "_compute_state_stats",
        lambda entries: {"2026-01-01": {"online": 3600.0, "offline": 0.0, "asleep": 0.0}},
    )
    monkeypatch.setattr(app, "_compute_energy_stats", lambda vehicle_id=None: {})
    monkeypatch.setattr(app, "_compute_parking_losses", lambda vehicle_id=None: {})
    monkeypatch.setattr(app, "_get_trip_files", lambda: [])

    ergebnis = app.compute_statistics()
    tag = ergebnis["2026-01-01"]

    assert tag["observed_seconds"] == 3600.0
    assert tag["online"] == 100.0
    assert tag["offline"] == 0.0
    assert tag["asleep"] == 0.0


def test_normalisierung_blaeht_offline_nicht_systematisch_auf():
    online, offline, asleep = app._normalize_state_percentages(66.66, 16.67, 16.66)

    assert online == 66.67
    assert offline == 16.67
    assert asleep == 16.66
    assert round(online + offline + asleep, 2) == 100.0
