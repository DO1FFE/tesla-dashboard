import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


def test_tesla_fleet_public_key_wird_ausgeliefert(monkeypatch, tmp_path):
    public_key = tmp_path / "com.tesla.3p.public-key.pem"
    public_key.write_text(
        "-----BEGIN PUBLIC KEY-----\n"
        "TEST\n"
        "-----END PUBLIC KEY-----\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(app, "TESLA_FLEET_PUBLIC_KEY_PATH", str(public_key))

    response = app.app.test_client().get(
        "/.well-known/appspecific/com.tesla.3p.public-key.pem"
    )

    assert response.status_code == 200
    assert response.mimetype == "application/x-pem-file"
    assert response.data == public_key.read_bytes()


def test_tesla_fleet_public_key_fehlt(monkeypatch, tmp_path):
    monkeypatch.setattr(
        app,
        "TESLA_FLEET_PUBLIC_KEY_PATH",
        str(tmp_path / "fehlt.pem"),
    )

    response = app.app.test_client().get(
        "/.well-known/appspecific/com.tesla.3p.public-key.pem"
    )

    assert response.status_code == 404
