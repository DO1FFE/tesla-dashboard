from datetime import datetime, timezone
import re
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


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


class TeslaToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    vehicle_id = db.Column(db.String, nullable=True)
    access_token = db.Column(db.String, nullable=False)
    refresh_token = db.Column(db.String, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "vehicle_id", name="uix_user_vehicle_token"),
    )


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
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"), nullable=False)
    state = db.Column(db.String(32), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "vehicle_id", "created_at", "state", name="uix_vehicle_state"
        ),
    )


class EnergyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"), nullable=False)
    added_energy = db.Column(db.Float, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "vehicle_id", "created_at", name="uix_energy_log"
        ),
    )


class TripEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"), nullable=False)
    started_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ended_at = db.Column(db.DateTime(timezone=True))
    distance_km = db.Column(db.Float, default=0.0)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "vehicle_id", "started_at", name="uix_trip_entry"
        ),
    )


class SmsLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"))
    message = db.Column(db.Text, nullable=False)
    success = db.Column(db.Boolean, default=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "vehicle_id", "created_at", "message", name="uix_sms_log"
        ),
    )


class ApiLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"))
    endpoint = db.Column(db.String(120), nullable=False)
    data = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "vehicle_id", "created_at", "endpoint", name="uix_api_log"
        ),
    )


class StatisticsEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    value = db.Column(db.Float, default=0.0)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "vehicle_id", "created_at", "name", name="uix_stat_entry"
        ),
    )


class TaximeterRide(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(16), nullable=False, default="ready")
    started_at = db.Column(db.DateTime(timezone=True))
    ended_at = db.Column(db.DateTime(timezone=True))
    duration_s = db.Column(db.Float)
    distance_m = db.Column(db.Float)
    wait_time_s = db.Column(db.Float)
    cost_base = db.Column(db.Float)
    cost_distance = db.Column(db.Float)
    cost_wait = db.Column(db.Float)
    cost_total = db.Column(db.Float)
    tariff_snapshot_json = db.Column(db.Text)
    receipt_json = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"), nullable=False)
    points = db.relationship("TaximeterPoint", backref="ride")


class TaximeterPoint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ride_id = db.Column(db.Integer, db.ForeignKey("taximeter_ride.id"), nullable=False)
    ts = db.Column(db.DateTime(timezone=True))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)
    speed_kph = db.Column(db.Float)
    heading_deg = db.Column(db.Float)
    odo_m = db.Column(db.Float)
    is_pause = db.Column(db.Boolean, default=False)
    is_wait = db.Column(db.Boolean, default=False)


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
