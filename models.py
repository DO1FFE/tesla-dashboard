from datetime import datetime

from flask_login import UserMixin
from sqlalchemy.orm import validates
from werkzeug.security import generate_password_hash, check_password_hash

try:  # running via `python app.py`
    from __main__ import db  # type: ignore
except ImportError:  # pragma: no cover
    from app import db  # type: ignore


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    username_slug = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(5), default="user")
    subscription = db.Column(db.String(5), default="free")
    is_ham_operator = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.username and not self.username_slug:
            self.username_slug = self.username.lower()

    @validates("username")
    def _set_slug(self, key, value):  # pragma: no cover - simple setter
        self.username_slug = value.lower()
        return value

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


def init_db():
    db.create_all()
