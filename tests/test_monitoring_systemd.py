from pathlib import Path


PROJEKT = Path(__file__).resolve().parents[1]
SYSTEMD = PROJEKT / "systemd"


def test_mqtt_monitor_ist_rebootfest_und_schreibt_persistent():
    inhalt = (SYSTEMD / "tesla-dashboard-mqtt-monitor.service").read_text(
        encoding="utf-8"
    )

    assert "WantedBy=multi-user.target" in inhalt
    assert "Restart=always" in inhalt
    assert "data/monitoring/fleet-mqtt.tsv" in inhalt
    assert "/tmp/" not in inhalt
    assert '"%%U\\t%%t\\t%%p"' in inhalt


def test_status_monitor_ist_unbegrenzt_und_schreibt_persistent():
    inhalt = (SYSTEMD / "tesla-dashboard-status-monitor.service").read_text(
        encoding="utf-8"
    )

    assert "WantedBy=multi-user.target" in inhalt
    assert "Restart=always" in inhalt
    assert "--dauer 0" in inhalt
    assert "data/monitoring/fahrtstatus.ndjson" in inhalt
    assert "/tmp/" not in inhalt


def test_monitoring_logs_werden_begrenzt_aufbewahrt():
    inhalt = (SYSTEMD / "tesla-dashboard-monitoring.logrotate").read_text(
        encoding="utf-8"
    )

    assert "maxsize 100M" in inhalt
    assert "rotate 14" in inhalt
    assert "compress" in inhalt
    assert "copytruncate" in inhalt
