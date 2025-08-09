import os
import sys
import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app import app, db, User


def create_user(username, **kwargs):
    user = User(
        username=username,
        username_slug=username,
        email=f"{username}@example.com",
        subscription="basic",
        **kwargs,
    )
    user.set_password("pw")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def client():
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SECRET_KEY="test",
    )
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def login(client, username):
    return client.post(
        "/login", data={"username": username, "password": "pw"}, follow_redirects=True
    )


def test_sms_route_absent(client):
    create_user("user")
    resp = client.get("/user/sms")
    assert resp.status_code == 404


def test_sms_api_requires_admin(client):
    create_user("user")
    login(client, "user")
    resp = client.post("/api/sms", json={"message": "hi"})
    assert resp.status_code == 403


def test_aprs_requires_ham_or_admin(client):
    create_user("alice")
    login(client, "alice")
    resp = client.post("/alice/config", data={"aprs_callsign": "TEST"})
    assert resp.status_code == 403


def test_aprs_allowed_for_ham(client):
    create_user("ham", is_ham_operator=True)
    login(client, "ham")
    resp = client.post("/ham/config", data={"aprs_callsign": "TEST"})
    assert resp.status_code == 200
