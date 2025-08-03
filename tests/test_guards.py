import os
import sys
import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app import app, db, User


@pytest.fixture
def client():
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        TESTING=True,
        WTF_CSRF_ENABLED=False,
    )
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def create_user(username, role="user", ham=False):
    user = User(username=username, email=f"{username}@example.com", role=role, is_ham_operator=ham)
    user.set_password("pw")
    db.session.add(user)
    db.session.commit()
    return user


def login(client, email):
    return client.post("/login", data={"email": email, "password": "pw"}, follow_redirects=True)


def logout(client):
    client.get("/logout", follow_redirects=True)


def test_sms_admin_only(client):
    with app.app_context():
        admin = create_user("admin", role="admin")
        user = create_user("user")
        slug = user.username_slug
    login(client, "user@example.com")
    resp = client.post("/api/sms", json={"message": "hi"})
    assert resp.status_code == 403
    logout(client)
    login(client, "admin@example.com")
    resp = client.post("/api/sms", json={"message": "hi"})
    assert resp.status_code != 403
    resp = client.post(f"/{slug}/api/sms", json={"message": "hi"})
    assert resp.status_code == 404


def test_aprs_guard_and_registration(client):
    with app.app_context():
        ham = create_user("ham", ham=True)
        nonham = create_user("nonham")
        ham_slug = ham.username_slug
        nonham_slug = nonham.username_slug
    # registration cannot set ham operator flag
    client.post(
        "/register",
        data={
            "username": "new",
            "email": "new@example.com",
            "password": "pw",
            "is_ham_operator": "1",
        },
        follow_redirects=True,
    )
    with app.app_context():
        new_user = User.query.filter_by(email="new@example.com").first()
        assert new_user is not None
        assert not new_user.is_ham_operator
    logout(client)
    # non-ham user blocked
    login(client, "nonham@example.com")
    resp = client.get(f"/{nonham_slug}/config")
    assert resp.status_code == 403
    assert "ham operators" in resp.get_data(as_text=True)
    logout(client)
    # ham operator allowed
    login(client, "ham@example.com")
    resp = client.get(f"/{ham_slug}/config")
    assert resp.status_code == 200
