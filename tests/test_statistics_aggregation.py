import importlib
import pathlib
from datetime import datetime


def _write_trip(path):
    content = """1700000000000,0,0,30
1700000005000,0,1,45
"""
    path.write_text(content, encoding="utf-8")


def test_monthly_rebuild(monkeypatch, tmp_path):
    db_path = tmp_path / "stats.db"
    monkeypatch.setenv("STATISTICS_DB_PATH", str(db_path))

    import app

    importlib.reload(app)

    conn = app._statistics_conn()
    app._ensure_statistics_tables(conn)

    app._write_daily_row(
        conn,
        "2024-01-01",
        {
            "online": 50.0,
            "offline": 30.0,
            "asleep": 20.0,
            "km": 10.0,
            "speed": 20.0,
            "energy": 5.0,
            "park_energy_pct": 1.0,
            "park_km": 2.0,
        },
    )
    app._write_daily_row(
        conn,
        "2024-01-02",
        {
            "online": 60.0,
            "offline": 25.0,
            "asleep": 15.0,
            "km": 15.0,
            "speed": 30.0,
            "energy": 7.5,
            "park_energy_pct": 1.5,
            "park_km": 1.0,
        },
    )

    app._rebuild_monthly_scope(conn)
    monthly = app._load_monthly_statistics()
    conn.close()

    january = monthly.get("2024-01")
    assert january is not None
    assert january["online"] == 55.0
    assert january["km"] == 25.0
    assert january["speed"] == 30.0
    assert january["energy"] == 12.5


def test_api_statistics_includes_new_trip(monkeypatch, tmp_path):
    db_path = tmp_path / "stats.db"
    monkeypatch.setenv("STATISTICS_DB_PATH", str(db_path))

    import app

    importlib.reload(app)
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(app, "_default_vehicle_id", "1")

    app._statistics_aggregation_tick()

    trip_folder = pathlib.Path(app.trip_dir("1"))
    today = datetime.now(app.LOCAL_TZ).date()
    trip_path = trip_folder / f"trip_{today.strftime('%Y%m%d')}.csv"
    _write_trip(trip_path)

    expected_km = round(app._trip_distance(trip_path), 2)
    expected_speed = int(round(app._trip_max_speed(trip_path)))

    app._statistics_aggregation_tick()

    client = app.app.test_client()
    resp = client.get("/api/statistik")
    payload = resp.get_json()

    today_row = next((row for row in payload["rows"] if row["date"] == today.isoformat()), None)

    assert today_row is not None
    assert today_row["km"] == expected_km
    assert today_row["speed"] == expected_speed
