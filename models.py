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


class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    vehicle_id = db.Column(db.String, nullable=False)
    vin = db.Column(db.String(17))
    model = db.Column(db.String(32))
    display_name = db.Column(db.String(128))
    active = db.Column(db.Boolean, default=True)

    __table_args__ = (db.UniqueConstraint("user_id", "vehicle_id"),)


class VehicleState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(
        db.String, db.ForeignKey("vehicle.vehicle_id"), nullable=False
    )
    data = db.Column(db.JSON)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)


class EnergyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(
        db.String, db.ForeignKey("vehicle.vehicle_id"), nullable=False
    )
    energy = db.Column(db.Float)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)


class TripEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(
        db.String, db.ForeignKey("vehicle.vehicle_id"), nullable=False
    )
    started_at = db.Column(db.DateTime)
    ended_at = db.Column(db.DateTime)
    distance = db.Column(db.Float)


class ConfigOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    label = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255))


class ConfigVisibility(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    config_option_id = db.Column(
        db.Integer, db.ForeignKey("config_option.id"), nullable=False
    )
    required_subscription = db.Column(db.String(5), nullable=False, default="free")
    always_active = db.Column(db.Boolean, default=False)

    config_option = db.relationship("ConfigOption", backref="visibility", uselist=False)


class UserConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    config_option_id = db.Column(
        db.Integer, db.ForeignKey("config_option.id"), nullable=False
    )
    value = db.Column(db.String)

    __table_args__ = (db.UniqueConstraint("user_id", "config_option_id"),)

    option = db.relationship("ConfigOption")


def init_db():
    db.create_all()
