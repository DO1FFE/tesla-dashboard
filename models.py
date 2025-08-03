from datetime import datetime, timezone
import re
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


def _slugify(value: str) -> str:
    """Return a lowercase slug consisting of ``a-z0-9`` and hyphen."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    username_slug = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(16), default="user")
    subscription = db.Column(db.String(16), default="free")
    is_ham_operator = db.Column(db.Boolean, default=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.username and not self.username_slug:
            self.username_slug = _slugify(self.username)

    def set_username(self, username: str) -> None:
        self.username = username
        self.username_slug = _slugify(username)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def init_db():
    db.create_all()
