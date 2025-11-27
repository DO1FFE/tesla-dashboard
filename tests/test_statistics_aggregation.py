import importlib


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
