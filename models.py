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
    stripe_subscription_id = db.Column(db.String(64))
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


class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    vehicle_id = db.Column(db.String, nullable=False)
    vin = db.Column(db.String)
    model = db.Column(db.String)
    display_name = db.Column(db.String)
    active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("user_id", "vehicle_id", name="uix_user_vehicle"),
    )


class VehicleState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"), nullable=False)
    state = db.Column(db.String(32), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class EnergyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"), nullable=False)
    added_energy = db.Column(db.Float, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TripEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"), nullable=False)
    started_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ended_at = db.Column(db.DateTime(timezone=True))
    distance_km = db.Column(db.Float, default=0.0)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ConfigOption(db.Model):
    """Configurable option that may depend on a subscription level."""

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    label = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)


class ConfigVisibility(db.Model):
    """Visibility rules for a configuration option."""

    id = db.Column(db.Integer, primary_key=True)
    config_option_id = db.Column(
        db.Integer, db.ForeignKey("config_option.id"), nullable=False
    )
    required_subscription = db.Column(db.String(16), default="free")
    always_active = db.Column(db.Boolean, default=False)

    config_option = db.relationship(
        "ConfigOption", backref=db.backref("visibility", uselist=False)
    )


class UserConfig(db.Model):
    """User specific value for a configuration option."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    config_option_id = db.Column(
        db.Integer, db.ForeignKey("config_option.id"), nullable=False
    )
    value = db.Column(db.String)

    __table_args__ = (
        db.UniqueConstraint("user_id", "config_option_id", name="uix_user_config"),
    )

    user = db.relationship("User", backref="configs")
    config_option = db.relationship("ConfigOption")


def init_db():
    db.create_all()
