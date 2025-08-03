import os
import json
import queue
import threading
import time
import logging
from flask import (
    Flask,
    render_template,
    jsonify,
    Response,
    request,
    abort,
    url_for,
    redirect,
    g,
    Blueprint,
)
from extensions import db
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from taximeter import Taximeter
import requests
from dotenv import load_dotenv
from version import get_version
import qrcode
from io import BytesIO
import base64
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import stripe
import click

try:
    import teslapy
except ImportError:
    teslapy = None

try:
    import aprslib
except ImportError:
    aprslib = None

try:
    import phonenumbers
except ImportError:
    phonenumbers = None

load_dotenv()
app = Flask(__name__)
app.config.from_object("config")
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

from models import (  # noqa: E402  pylint: disable=wrong-import-position
    User,
    ConfigOption,
    ConfigVisibility,
    Vehicle,
    TeslaToken,
    VehicleState,
    EnergyLog,
    SmsLog,
    ApiLog,
    TripEntry,
    StatisticsEntry,
    TaximeterRide,
)
from functools import wraps
from views.auth import auth_bp


def tesla_token_required(func):
    @wraps(func)
    @login_required
    def wrapper(*args, **kwargs):
        token = TeslaToken.query.filter_by(user_id=current_user.id).first()
        if token is None:
            return redirect(url_for("auth.oauth_start"))
        return func(*args, **kwargs)

    return wrapper
class _AdminIndex(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == "admin"

    def inaccessible_callback(self, name, **kwargs):
        abort(403)


class _AdminModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == "admin"

    def inaccessible_callback(self, name, **kwargs):
        abort(403)


class UserAdmin(_AdminModelView):
    column_list = ("email", "role", "subscription", "is_ham_operator")
    form_columns = ("email", "role", "subscription", "is_ham_operator")
    column_searchable_list = ("email", "role", "subscription")
    can_view_details = True


class VehicleAdmin(_AdminModelView):
    pass


admin_site = Admin(
    app, index_view=_AdminIndex(url="/admin"), template_mode="bootstrap3"
)
admin_site.add_view(
    UserAdmin(User, db.session, endpoint="users", url="/admin/users")
)
admin_site.add_view(
    VehicleAdmin(Vehicle, db.session, endpoint="vehicles", url="/admin/vehicles")
)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
__version__ = get_version()
CURRENT_YEAR = datetime.now(ZoneInfo("Europe/Berlin")).year
GA_TRACKING_ID = os.getenv("GA_TRACKING_ID")

SUBSCRIPTION_LEVELS = {"free": 0, "basic": 1, "pro": 2}
PLAN_PRICES = {
    os.getenv("STRIPE_BASIC_PRICE_ID", ""): "basic",
    os.getenv("STRIPE_PRO_PRICE_ID", ""): "pro",
}


def _get_visibility(key):
    """Return visibility settings for a config option ``key``."""
    return (
        ConfigVisibility.query.join(ConfigOption)
        .filter(ConfigOption.key == key)
        .first()
    )


def requires_subscription(level):
    """Ensure the current user has at least ``level`` subscription."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            visibility = _get_visibility(func.__name__)
            if visibility and visibility.always_active:
                return func(*args, **kwargs)
            required = level
            if visibility:
                required = visibility.required_subscription or level
            user_level = getattr(current_user, "subscription", "free")
            if SUBSCRIPTION_LEVELS.get(user_level, 0) < SUBSCRIPTION_LEVELS.get(
                required, 0
            ):
                abort(403)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def admin_only(func):
    """Allow access only to logged-in admin users."""
    @wraps(func)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return func(*args, **kwargs)
    return wrapper


def ham_only(func):
    """Restrict access to ham operators or the root dashboard."""
    @wraps(func)
    @login_required
    def wrapper(*args, **kwargs):
        kwargs.pop("username_slug", None)
        if hasattr(g, "username_slug") and not (
            current_user.role == "admin" or current_user.is_ham_operator
        ):
            abort(403, description="APRS only available to ham operators")
        return func(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_ga_id():
    """Add Google Analytics tracking ID to all templates."""
    return {"ga_id": GA_TRACKING_ID}


# Ensure data paths are relative to this file regardless of the
# current working directory.  This allows running the application
# from any location while still finding the trip files and caches.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)


def vehicle_dir(vehicle_id):
    """Return directory for a specific vehicle."""
    if vehicle_id is None:
        raise ValueError("vehicle_id required")
    path = os.path.join(DATA_DIR, str(vehicle_id))
    os.makedirs(path, exist_ok=True)
    return path


def migrate_legacy_files():
    """Move files from the old layout to per-vehicle directories."""
    try:
        for fname in os.listdir(DATA_DIR):
            if fname.startswith("cache_") and fname.endswith(".json"):
                vid = fname[len("cache_"):-5]
                src = os.path.join(DATA_DIR, fname)
                dst = os.path.join(vehicle_dir(vid), "cache.json")
                if not os.path.exists(dst):
                    os.rename(src, dst)
            if fname.startswith("last_energy_") and fname.endswith(".txt"):
                vid = fname[len("last_energy_"):-4]
                src = os.path.join(DATA_DIR, fname)
                dst = os.path.join(vehicle_dir(vid), "last_energy.txt")
                if not os.path.exists(dst):
                    os.rename(src, dst)
        old_trip_dir = os.path.join(DATA_DIR, "trips")
        if os.path.isdir(old_trip_dir):
            # Trip files without a vehicle_id cannot be migrated automatically
            pass
    except Exception:
        pass


migrate_legacy_files()

CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
APRS_HOST = "euro.aprs2.net"
APRS_PORT = 14580
LOCAL_TZ = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")
MILES_TO_KM = 1.60934
api_logger = logging.getLogger("api_logger")
if not api_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(message)s")
    handler.setFormatter(formatter)
    api_logger.addHandler(handler)
    api_logger.setLevel(logging.INFO)
    for name in ("teslapy", "urllib3"):
        lib_logger = logging.getLogger(name)
        lib_logger.addHandler(handler)
        lib_logger.setLevel(logging.DEBUG)
    try:
        import http.client as http_client
        http_client.HTTPConnection.debuglevel = 1
    except Exception:
        pass

state_logger = logging.getLogger("state_logger")
if not state_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(message)s")
    formatter.converter = lambda ts: datetime.fromtimestamp(ts, LOCAL_TZ).timetuple()
    handler.setFormatter(formatter)
    state_logger.addHandler(handler)
    state_logger.setLevel(logging.INFO)

energy_logger = logging.getLogger("energy_logger")
if not energy_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(message)s")
    formatter.converter = lambda ts: datetime.fromtimestamp(ts, LOCAL_TZ).timetuple()
    handler.setFormatter(formatter)
    energy_logger.addHandler(handler)
    energy_logger.setLevel(logging.INFO)

sms_logger = logging.getLogger("sms_logger")
if not sms_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(message)s")
    formatter.converter = lambda ts: datetime.fromtimestamp(ts, LOCAL_TZ).timetuple()
    handler.setFormatter(formatter)
    sms_logger.addHandler(handler)
    sms_logger.setLevel(logging.INFO)

import models
with app.app_context():
    models.init_db()

def _load_last_state(filename=os.path.join(DATA_DIR, "state.log")):
    """Load the last logged state for each vehicle.

    File access is disabled; always return an empty dict."""
    return {}



# Tools to build an aggregated list of API keys ------------------------------


def _collect_keys(data, prefix="", keys=None):
    """Recursively gather dotted key names from the given data."""
    if keys is None:
        keys = set()
    if isinstance(data, dict):
        for k, v in data.items():
            key = f"{prefix}.{k}" if prefix else k
            keys.add(key)
            _collect_keys(v, key, keys)
    elif isinstance(data, list):
        for item in data:
            _collect_keys(item, prefix, keys)
    return keys


def _collect_key_values(data, prefix="", result=None):
    """Recursively gather key/value pairs in the order provided by the API."""
    if result is None:
        result = []
    if isinstance(data, dict):
        for k, v in data.items():
            key = f"{prefix}.{k}" if prefix else k
            _collect_key_values(v, key, result)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            key = f"{prefix}[{i}]"
            _collect_key_values(item, key, result)
    else:
        result.append((prefix, data))
    return result


def _merge_data(existing, new):
    """Recursively merge ``new`` into ``existing`` without removing keys."""
    if isinstance(existing, dict) and isinstance(new, dict):
        for k, v in new.items():
            if k in existing:
                existing[k] = _merge_data(existing[k], v)
            else:
                existing[k] = v
        return existing
    if isinstance(existing, list) and isinstance(new, list):
        for i, item in enumerate(new):
            if i < len(existing):
                existing[i] = _merge_data(existing[i], item)
            else:
                existing.append(item)
        return existing
    return new


def _update_api_json(data, filename=os.path.join(DATA_DIR, "api-liste.json")):
    """Update ``api-liste.json`` while preserving existing keys (disabled)."""
    return

def update_api_list(data, filename=os.path.join(DATA_DIR, "api-liste.txt")):
    """Update ``api-liste.txt`` with key/value pairs in API order (disabled)."""
    return

def log_api_data(endpoint, data):
    """Persist API communication to the database."""
    try:
        veh_id = data.get("vehicle_id") or data.get("id") if isinstance(data, dict) else None
        veh = Vehicle.query.filter_by(vehicle_id=str(veh_id)).first() if veh_id else None
        if veh:
            entry = ApiLog(
                user_id=veh.user_id,
                vehicle_id=veh.id,
                endpoint=endpoint,
                data=json.dumps(data),
            )
            db.session.add(entry)
            db.session.commit()
    except Exception:
        db.session.rollback()


STAT_FILE = os.path.join(DATA_DIR, "statistics.json")
PARKTIME_FILE = os.path.join(DATA_DIR, "parktime.json")

# In-memory state used across requests. These variables were previously
# referenced without being initialised which caused ``NameError`` at runtime
# as soon as the respective helper functions were invoked.  Initialising them
# here keeps the application start-up simple while avoiding those errors.
api_errors = []
api_errors_lock = threading.Lock()
state_lock = threading.Lock()
last_vehicle_state = {}
latest_data = {}
subscribers = {}

# Variables tracking the current trip and parking status.  They are shared
# between helper functions and therefore need module level defaults.
trip_path = []
drive_pause_ms = None
park_start_ms = None
last_shift_state = None

# Elements on the dashboard that can be toggled via the config page
CONFIG_ITEMS = [
    {"id": "map", "desc": "Karte"},
    {"id": "lock-status", "desc": "Verriegelungsstatus"},
    {"id": "user-presence", "desc": "Anwesenheit Fahrer"},
    {"id": "gear-shift", "desc": "Ganghebel"},
    {"id": "battery-indicator", "desc": "Batteriestand"},
    {"id": "speedometer", "desc": "Tacho"},
    {"id": "thermometers", "desc": "Temperaturen"},
    {"id": "climate-indicator", "desc": "Klimaanlage"},
    {"id": "tpms-indicator", "desc": "Reifendruck"},
    {"id": "openings-indicator", "desc": "Türen/Fenster"},
    {"id": "blue-openings", "desc": "Türen/Fenster blau einfärben", "default": False},
    {"id": "heater-indicator", "desc": "Heizungsstatus"},
    {"id": "charging-info", "desc": "Ladeinformationen"},
    {"id": "v2l-infos", "desc": "V2L-Hinweis"},
    {"id": "announcement-box", "desc": "Hinweistext"},
    {"id": "page-menu", "desc": "Seitenmenü"},
    {"id": "menu-dashboard", "desc": "Dashboard im Seitenmenü"},
    {"id": "menu-statistik", "desc": "Statistik im Seitenmenü"},
    {"id": "menu-history", "desc": "History im Seitenmenü"},
    {"id": "nav-bar", "desc": "Navigationsleiste"},
    {"id": "media-player", "desc": "Medienwiedergabe"},
]


def load_config():
    """Load configuration (file access removed)."""
    return {}


def save_config(cfg):
    """Persist configuration (disabled)."""
    return

def get_taximeter_tariff():
    cfg = load_config()
    default = {
        "base": 4.40,
        "rate_1_2": 2.70,
        "rate_3_4": 2.60,
        "rate_5_plus": 2.40,
        "wait_per_10s": 0.10,
    }
    tariff = cfg.get("taximeter_tariff")
    if isinstance(tariff, dict):
        for key in default:
            val = tariff.get(key)
            if isinstance(val, (int, float)):
                default[key] = float(val)
    return default


def get_taxi_company():
    cfg = load_config()
    return cfg.get("taxi_company", "Taxi Schauer")


def get_taxi_slogan():
    cfg = load_config()
    return cfg.get("taxi_slogan", "Wir lassen Sie nicht im Regen stehen.")


def format_receipt(company, breakdown, distance=0.0, slogan=""):
    lines = []
    if company:
        lines.append(company)
        if slogan:
            lines.append(slogan)
        lines.append("")
    lines.append(f"Grundpreis:{breakdown['base']:>7.2f} €")
    if breakdown.get('km_1_2', 0) > 0:
        lines.append(
            f"{breakdown['km_1_2']:.2f} km x {breakdown['rate_1_2']:.2f} € ={breakdown['cost_1_2']:>7.2f} €"
        )
    if breakdown.get('km_3_4', 0) > 0:
        lines.append(
            f"{breakdown['km_3_4']:.2f} km x {breakdown['rate_3_4']:.2f} € ={breakdown['cost_3_4']:>7.2f} €"
        )
    if breakdown.get('km_5_plus', 0) > 0:
        lines.append(
            f"{breakdown['km_5_plus']:.2f} km x {breakdown['rate_5_plus']:.2f} € ={breakdown['cost_5_plus']:>7.2f} €"
        )
    if breakdown.get('wait_cost', 0) > 0:
        lines.append(
            f"Standzeit {int(breakdown['wait_time'])}s ={breakdown['wait_cost']:>7.2f} €"
        )
    lines.append("--------------------")
    lines.append(f"Gesamt:{breakdown['total']:>9.2f} €")
    lines.append(f"Fahrstrecke: {distance:.2f} km")
    return "\n".join(lines)


def get_news_events_info():
    """Return the current state of the news/events toggles via the API."""
    tesla = get_tesla()
    if tesla is None:
        return ""

    try:
        data = tesla.api("NOTIFICATIONS_GET_NEWS_AND_EVENTS_TOGGLES")
        log_api_data("NOTIFICATIONS_GET_NEWS_AND_EVENTS_TOGGLES", data)
        if isinstance(data, dict):
            pairs = [f"{k}={v}" for k, v in data.items()]
            return "Toggles: " + ", ".join(pairs)
    except Exception as exc:
        _log_api_error(exc)
    return ""


def _load_parktime():
    """Load the last park timestamp (file access removed)."""
    return None


def _save_parktime(ts):
    """Persist the park timestamp (disabled)."""
    return

def _delete_parktime():
    """Remove the stored park timestamp (disabled)."""
    return

def track_park_time(vehicle_data):
    """Track when the vehicle was first seen parked."""
    global park_start_ms, last_shift_state
    drive = (
        vehicle_data.get("drive_state", {}) if isinstance(vehicle_data, dict) else {}
    )
    shift = drive.get("shift_state")
    ts = drive.get("timestamp") or drive.get("gps_as_of")
    if ts and ts < 1e12:
        ts = int(ts * 1000)
    if shift in (None, "P"):
        if park_start_ms is None or last_shift_state not in (None, "P"):
            park_start_ms = int(ts) if ts is not None else None
            if park_start_ms is not None:
                _save_parktime(park_start_ms)
    else:
        park_start_ms = None
        _delete_parktime()
    last_shift_state = shift


def park_duration_string(start_ms):
    """Return human readable parking duration for ``start_ms``."""
    if start_ms is None:
        return None
    diff = int(time.time() * 1000) - start_ms
    hours = diff // 3600000
    minutes = (diff % 3600000) // 60000
    parts = []
    if hours > 0:
        parts.append(f"{hours} {'Stunde' if hours == 1 else 'Stunden'}")
    parts.append(f"{minutes} {'Minute' if minutes == 1 else 'Minuten'}")
    return " ".join(parts)


def _log_trip_point(
    ts, lat, lon, speed=None, power=None, heading=None, gear=None, filename=None
):
    """Append a GPS point to a trip history CSV (disabled)."""
    return

def track_drive_path(vehicle_data):
    """Maintain the current trip path in memory."""
    global trip_path, drive_pause_ms
    drive = vehicle_data.get("drive_state", {}) if isinstance(vehicle_data, dict) else {}
    shift = drive.get("shift_state")
    lat = drive.get("latitude")
    lon = drive.get("longitude")
    ts = drive.get("timestamp") or drive.get("gps_as_of")
    if ts and ts < 1e12:
        ts = int(ts * 1000)
    if shift in (None, "P"):
        if drive_pause_ms is None:
            drive_pause_ms = ts if ts is not None else int(time.time() * 1000)
            if lat is not None and lon is not None:
                point = [lat, lon]
                if not trip_path or trip_path[-1] != point:
                    trip_path.append(point)
        else:
            if ts is None:
                ts = int(time.time() * 1000)
            if ts - drive_pause_ms > 600000:
                trip_path = []
                drive_pause_ms = None
        return
    if drive_pause_ms is not None:
        if ts is None:
            ts = int(time.time() * 1000)
        if ts - drive_pause_ms > 600000:
            trip_path = []
        drive_pause_ms = None
    if lat is not None and lon is not None:
        if ts is None:
            ts = int(time.time() * 1000)
        point = [lat, lon]
        if not trip_path or trip_path[-1] != point:
            trip_path.append(point)


def _log_api_error(exc):
    """Store API error messages with timestamp for later retrieval."""
    ts = time.time()
    msg = str(exc)
    with api_errors_lock:
        api_errors.append({"timestamp": ts, "message": msg})
        if len(api_errors) > 50:
            api_errors.pop(0)


def log_vehicle_state(vehicle_id, state):
    """Persist vehicle state changes in the database."""
    try:
        with state_lock:
            if last_vehicle_state.get(vehicle_id) != state:
                last_vehicle_state[vehicle_id] = state
                veh = Vehicle.query.filter_by(vehicle_id=str(vehicle_id)).first()
                if veh:
                    entry = VehicleState(
                        user_id=veh.user_id, vehicle_id=veh.id, state=state
                    )
                    db.session.add(entry)
                    db.session.commit()
    except Exception:
        db.session.rollback()


def _last_logged_energy(vehicle_id):
    """Return the last logged energy value for ``vehicle_id`` or ``None``."""
    veh = Vehicle.query.filter_by(vehicle_id=str(vehicle_id)).first()
    if not veh:
        return None
    entry = (
        EnergyLog.query.filter_by(user_id=veh.user_id, vehicle_id=veh.id)
        .order_by(EnergyLog.created_at.desc())
        .first()
    )
    return float(entry.added_energy) if entry else None


def _log_energy(vehicle_id, amount):
    """Store the last added energy value in the database."""
    try:
        last = _last_logged_energy(vehicle_id)
        if last is None or abs(last - amount) > 0.001:
            veh = Vehicle.query.filter_by(vehicle_id=str(vehicle_id)).first()
            if veh:
                entry = EnergyLog(
                    user_id=veh.user_id, vehicle_id=veh.id, added_energy=amount
                )
                db.session.add(entry)
                db.session.commit()
    except Exception:
        db.session.rollback()


def _log_sms(message, success, vehicle_id=None):
    """Append SMS information to the database."""
    try:
        veh = None
        if vehicle_id is not None:
            veh = Vehicle.query.filter_by(vehicle_id=str(vehicle_id)).first()
        if veh:
            entry = SmsLog(
                user_id=veh.user_id,
                vehicle_id=veh.id,
                message=message,
                success=bool(success),
            )
            db.session.add(entry)
            db.session.commit()
    except Exception:
        db.session.rollback()


def _cache_file(vehicle_id):
    """Return filename for cached data of a vehicle."""
    return os.path.join(vehicle_dir(vehicle_id), "cache.json")


def _load_cached(vehicle_id):
    """Load cached vehicle data (disabled)."""
    return None

def _save_cached(vehicle_id, data):
    """Write vehicle data cache (disabled)."""
    return

def _last_energy_file(vehicle_id):
    """Return filename for the last added energy of a vehicle."""
    return os.path.join(vehicle_dir(vehicle_id), "last_energy.txt")


def _load_last_energy(vehicle_id):
    """Load the last added energy value (disabled)."""
    return None

def _save_last_energy(vehicle_id, value):
    """Persist the last added energy value for a vehicle (disabled)."""
    return

def send_aprs(vehicle_data):
    """Transmit a position packet via APRS-IS using aprslib."""
    if aprslib is None:
        return
    if (
        isinstance(vehicle_data, dict)
        and vehicle_data.get("state") == "offline"
        and not occupant_present
    ):
        return

    cfg = load_config()
    callsign = cfg.get("aprs_callsign")
    passcode = cfg.get("aprs_passcode")
    wx_callsign = cfg.get("aprs_wx_callsign")
    wx_enabled = cfg.get("aprs_wx_enabled", True)
    comment_cfg = cfg.get("aprs_comment", "")
    if not callsign or not passcode:
        return

    drive = (
        vehicle_data.get("drive_state", {}) if isinstance(vehicle_data, dict) else {}
    )
    climate = (
        vehicle_data.get("climate_state", {}) if isinstance(vehicle_data, dict) else {}
    )
    lat = drive.get("latitude")
    lon = drive.get("longitude")
    if lat is None or lon is None:
        return

    temp_in = climate.get("inside_temp")
    temp_out = climate.get("outside_temp")
    vid_raw = vehicle_data.get("id_s") or vehicle_data.get("vehicle_id")
    if vid_raw is None:
        raise ValueError("vehicle_id required")
    vid = str(vid_raw)
    now = time.time()
    last = _last_aprs_info.get(vid)
    changed = last is None
    if last is not None:
        if abs(lat - last.get("lat", 0)) > 1e-5 or abs(lon - last.get("lon", 0)) > 1e-5:
            changed = True
        if temp_out != last.get("temp_out") or temp_in != last.get("temp_in"):
            changed = True
        if now - last.get("time", 0) >= 600:
            changed = True
        if now - last.get("time", 0) < 30:
            return
    if not changed:
        return

    comment_parts = []
    if comment_cfg:
        comment_parts.append(comment_cfg)
    if temp_out is not None:
        comment_parts.append(f"Temp out: {temp_out:.1f}C")
    if temp_in is not None:
        comment_parts.append(f"Temp in: {temp_in:.1f}C")
    comment = " - ".join(comment_parts)

    try:
        aprs = aprslib.IS(
            callsign, passwd=str(passcode), host=APRS_HOST, port=APRS_PORT
        )
        aprs.connect()

        from aprslib.util import latitude_to_ddm, longitude_to_ddm

        lat_ddm = latitude_to_ddm(lat)
        lon_ddm = longitude_to_ddm(lon)

        # Standard-Positionspaket mit Kommentar
        body = f"!{lat_ddm}/{lon_ddm}>{comment}"
        packet = f"{callsign}>APRS:{body}"
        aprs.sendall(packet)
        aprs.close()

        # Zusätzliches WX-Paket senden (nur Außentemperatur, extra Rufzeichen)
        if wx_enabled and wx_callsign and temp_out is not None:
            last_wx = _last_wx_info.get(vid)
            wx_changed = last_wx is None
            if last_wx is not None:
                if temp_out != last_wx.get("temp_out"):
                    wx_changed = True
                if now - last_wx.get("time", 0) >= 600:
                    wx_changed = True
                if now - last_wx.get("time", 0) < 30:
                    wx_changed = False
            if wx_changed:
                aprs_wx = aprslib.IS(
                    wx_callsign, passwd=str(passcode), host=APRS_HOST, port=APRS_PORT
                )
                aprs_wx.connect()
                temp_f = int(round(temp_out * 9 / 5 + 32))
                wx_body = f"!{lat_ddm}/{lon_ddm}_g000t{temp_f:03d}"
                wx_packet = f"{wx_callsign}>APRS:{wx_body}{comment_cfg}"
                aprs_wx.sendall(wx_packet)
                aprs_wx.close()
                _last_wx_info[vid] = {
                    "temp_out": temp_out,
                    "time": now,
                }

        _last_aprs_info[vid] = {
            "lat": lat,
            "lon": lon,
            "temp_out": temp_out,
            "temp_in": temp_in,
            "time": now,
        }

    except Exception as exc:
        _log_api_error(exc)


def _get_trip_files(vehicle_id=None):
    """Return an empty list (legacy trip files removed)."""
    return []


def _get_trip_periods():
    """Return sorted lists of available weeks and months from the database."""
    weeks = set()
    months = set()
    for trip in TripEntry.query.all():
        day = trip.started_at.astimezone(LOCAL_TZ).date()
        iso_year, iso_week, _ = day.isocalendar()
        weeks.add(f"{iso_year}-W{iso_week:02d}")
        months.add(day.strftime("%Y-%m"))
    return sorted(weeks), sorted(months)


def _load_trip_period(prefix, key):
    """Load trip points for a given period (disabled)."""
    return []


def _load_trip(filename):
    """Load trip data (file access removed)."""
    return []


def _bearing(p1, p2):
    """Compute heading in degrees from p1 to p2."""
    from math import atan2, cos, sin, radians, degrees

    lat1, lon1 = radians(p1[0]), radians(p1[1])
    lat2, lon2 = radians(p2[0]), radians(p2[1])
    dlon = lon2 - lon1
    y = sin(dlon) * cos(lat2)
    x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    brng = degrees(atan2(y, x))
    return (brng + 360) % 360


def _haversine(lat1, lon1, lat2, lon2):
    """Compute distance in kilometers between two lat/lon points."""
    from math import radians, sin, cos, atan2, sqrt

    r = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


def _trip_distance(filename):
    """Return total distance in km for a trip CSV file."""
    points = _load_trip(filename)
    dist = 0.0
    for i in range(1, len(points)):
        lat1, lon1 = points[i - 1][:2]
        lat2, lon2 = points[i][:2]
        dist += _haversine(lat1, lon1, lat2, lon2)
    return dist


def _trip_max_speed(filename):
    """Return the maximum speed recorded in a trip CSV file in km/h."""
    points = _load_trip(filename)
    max_speed = 0.0
    for p in points:
        speed = p[2]
        if speed is not None and speed > max_speed:
            max_speed = speed
    return max_speed * MILES_TO_KM


def _split_trip_segments(filename):
    """Split a trip CSV into individual rides based on gear transitions.

    A new segment starts when shifting from P to R, N or D and ends when
    returning to P from any of these gears.
    """
    points = _load_trip(filename)
    segments = []
    current = []
    prev_gear = None
    for p in points:
        gear = p[6]
        if current:
            current.append(p)
            if gear == "P" and prev_gear in ("R", "N", "D"):
                segments.append(current)
                current = []
        else:
            if gear in ("R", "N", "D") and (prev_gear == "P" or prev_gear is None):
                current.append(p)
        prev_gear = gear
    if current:
        segments.append(current)

    result = []
    for seg in segments:
        if not seg:
            continue
        dist = 0.0
        wait = 0.0
        for i in range(1, len(seg)):
            lat1, lon1 = seg[i - 1][:2]
            lat2, lon2 = seg[i][:2]
            dist += _haversine(lat1, lon1, lat2, lon2)
            speed = seg[i - 1][2]
            t1 = seg[i - 1][4]
            t2 = seg[i][4]
            if (
                speed is not None
                and speed < 5
                and t1 is not None
                and t2 is not None
                and t2 > t1
            ):
                wait += (t2 - t1) / 1000.0
        start_ts = seg[0][4]
        end_ts = seg[-1][4]
        if start_ts is not None and start_ts > 1e12:
            start_ts /= 1000.0
        if end_ts is not None and end_ts > 1e12:
            end_ts /= 1000.0
        result.append({"start": start_ts, "end": end_ts, "distance": dist, "wait": wait})
    return result


def _period_distance(prefix, key):
    """Return distance in km for a week or month selection from ``TripEntry``."""
    dist = 0.0
    for trip in TripEntry.query.all():
        day = trip.started_at.astimezone(LOCAL_TZ).date()
        iso_year, iso_week, _ = day.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        month_key = day.strftime("%Y-%m")
        if prefix == "week" and week_key != key:
            continue
        if prefix == "month" and month_key != key:
            continue
        dist += float(trip.distance_km or 0.0)
    return dist


def _parse_log_time(ts_str):
    """Return a timezone-aware datetime parsed from a log line."""
    for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts_str, fmt).replace(tzinfo=LOCAL_TZ)
        except Exception:
            continue
    return None


def _load_state_entries():
    """Return log entries from the database as ``(timestamp, state)`` tuples."""
    entries = []
    for e in VehicleState.query.order_by(VehicleState.created_at).all():
        ts = e.created_at.replace(tzinfo=UTC).timestamp()
        entries.append((ts, e.state))
    return entries


def _compute_state_stats(entries):
    """Return per-day seconds spent in each state."""
    stats = {}
    if not entries:
        return stats
    entries.sort(key=lambda x: x[0])
    entries.append((time.time(), entries[-1][1]))
    for (start, state), (end, _next_state) in zip(entries, entries[1:]):
        t = start
        while t < end:
            day = datetime.fromtimestamp(t, LOCAL_TZ).date()
            next_day = datetime.combine(
                day + timedelta(days=1), datetime.min.time(), LOCAL_TZ
            ).timestamp()
            segment_end = min(end, next_day)
            dur = segment_end - t
            d = stats.setdefault(
                day.isoformat(), {"online": 0.0, "offline": 0.0, "asleep": 0.0}
            )
            key = state if state in d else "offline"
            d[key] += dur
            t = segment_end
    return stats


def _compute_energy_stats():
    """Return per-day added energy in kWh based on ``EnergyLog`` entries."""
    energy = {}
    last_vals = {}
    for e in EnergyLog.query.order_by(EnergyLog.created_at).all():
        day = e.created_at.astimezone(LOCAL_TZ).date().isoformat()
        last = last_vals.get(e.vehicle_id)
        if last is not None and abs(last - e.added_energy) < 0.001:
            continue
        last_vals[e.vehicle_id] = e.added_energy
        energy[day] = energy.get(day, 0.0) + float(e.added_energy)
    return energy


def compute_statistics():
    """Compute daily statistics using database entries."""
    stats = _compute_state_stats(_load_state_entries())
    energy = _compute_energy_stats()
    for trip in TripEntry.query.all():
        day = trip.started_at.astimezone(LOCAL_TZ).date().isoformat()
        stats.setdefault(day, {"online": 0.0, "offline": 0.0, "asleep": 0.0})
        stats[day]["km"] = stats[day].get("km", 0.0) + float(trip.distance_km or 0.0)
        stats[day].setdefault("speed", 0.0)
    for day, val in energy.items():
        stats.setdefault(day, {"online": 0.0, "offline": 0.0, "asleep": 0.0})
        stats[day]["energy"] = round(val, 2)
    for day, val in stats.items():
        total = 24 * 3600
        online = round(val.get("online", 0.0) / total * 100, 2)
        offline = round(val.get("offline", 0.0) / total * 100, 2)
        asleep = round(val.get("asleep", 0.0) / total * 100, 2)
        diff = round(100.0 - (online + offline + asleep), 2)
        offline = round(offline + diff, 2)
        val["online"] = online
        val["offline"] = offline
        val["asleep"] = asleep
        val.setdefault("km", 0.0)
        val.setdefault("speed", 0.0)
        val.setdefault("energy", 0.0)
    return stats

def compute_trip_summaries():
    """Return weekly and monthly distance summaries from ``TripEntry``."""
    weekly = {}
    monthly = {}
    for trip in TripEntry.query.all():
        day = trip.started_at.astimezone(LOCAL_TZ).date()
        km = float(trip.distance_km or 0.0)
        iso_year, iso_week, _ = day.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        weekly[week_key] = round(weekly.get(week_key, 0.0) + km, 2)
        month_key = day.strftime("%Y-%m")
        monthly[month_key] = round(monthly.get(month_key, 0.0) + km, 2)
    return weekly, monthly


def get_tesla():
    """Return an authenticated Tesla object for the current user."""
    if teslapy is None or not current_user.is_authenticated:
        return None

    token = TeslaToken.query.filter_by(user_id=current_user.id).first()
    if token is None:
        return None

    if token.expires_at <= datetime.utcnow():
        try:
            resp = requests.post(
                "https://auth.tesla.com/oauth2/v3/token",
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": token.refresh_token,
                    "client_id": app.config["TESLA_CLIENT_ID"],
                },
                headers={"User-Agent": app.config["TESLA_USER_AGENT"]},
                timeout=10,
            )
            data = resp.json()
            token.access_token = data.get("access_token", token.access_token)
            token.refresh_token = data.get("refresh_token", token.refresh_token)
            token.expires_at = datetime.utcnow() + timedelta(
                seconds=data.get("expires_in", 0)
            )
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            _log_api_error(exc)
            return None

    tesla = teslapy.Tesla(
        current_user.email, app_user_agent=app.config.get("TESLA_USER_AGENT", "Tesla-Dashboard")
    )
    tesla.sso_token = {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
    }
    try:
        tesla.refresh_token()
    except Exception as exc:
        _log_api_error(exc)
        return None
    return tesla


def sanitize(data):
    """Remove personally identifiable fields from the vehicle data."""
    if isinstance(data, dict):
        if "vin" in data:
            data.pop("vin", None)
        for value in data.values():
            sanitize(value)
    elif isinstance(data, list):
        for item in data:
            sanitize(item)
    return data


def _cached_vehicle_list(tesla, ttl=86400):
    """Return vehicle list with basic time-based caching."""
    global _vehicle_list_cache, _vehicle_list_cache_ts
    now = time.time()
    with _vehicle_list_lock:
        if not _vehicle_list_cache or now - _vehicle_list_cache_ts > ttl:
            try:
                _vehicle_list_cache = tesla.vehicle_list()
                _vehicle_list_cache_ts = now
                log_api_data(
                    "vehicle_list", sanitize([v.copy() for v in _vehicle_list_cache])
                )
            except Exception as exc:
                _log_api_error(exc)
                return []
        return _vehicle_list_cache


def _refresh_state(vehicle, times=2):
    """Query the vehicle state multiple times and return the last value."""
    state = None
    for _ in range(times):
        vehicle.get_vehicle_summary()
        state = vehicle.get("state") or vehicle["state"]
        log_vehicle_state(vehicle["id_s"], state)
        log_api_data("get_vehicle_summary", {"state": state})
        if state == "online":
            return state

    if state == "asleep":
        try:
            vehicle.sync_wake_up(timeout=10)
            state = vehicle.get("state") or vehicle["state"]
            log_vehicle_state(vehicle["id_s"], state)
            log_api_data("wake_up_retry", {"state": state})
        except Exception:
            pass
    return state


def get_vehicle_state(vehicle_id):
    """Return the current vehicle state without waking the car."""
    if vehicle_id is None:
        raise ValueError("vehicle_id required")
    vid = str(vehicle_id)
    state = last_vehicle_state.get(vid)

    tesla = get_tesla()
    if tesla is None:
        return {"error": "Missing Tesla credentials or teslapy not installed"}

    vehicles = _cached_vehicle_list(tesla)
    if not vehicles:
        return {"error": "No vehicles found"}

    vehicle = next((v for v in vehicles if str(v["id_s"]) == str(vehicle_id)), None)
    if vehicle is None:
        return {"error": "Vehicle not found"}

    try:
        state = _refresh_state(vehicle)
    except Exception as exc:
        _log_api_error(exc)
        log_vehicle_state(vehicle["id_s"], "offline")
        return {"error": "Vehicle unavailable", "state": "offline"}

    cached = _load_cached(vid)
    service_mode = None
    service_mode_plus = None
    if isinstance(cached, dict):
        vs = cached.get("vehicle_state", {})
        service_mode = vs.get("service_mode")
        service_mode_plus = vs.get("service_mode_plus")

    return {
        "state": state,
        "service_mode": service_mode,
        "service_mode_plus": service_mode_plus,
    }


def get_vehicle_data(vehicle_id=None, state=None):
    """Fetch vehicle data for a given vehicle id."""
    tesla = get_tesla()
    if tesla is None:
        return {"error": "Missing Tesla credentials or teslapy not installed"}

    vehicles = _cached_vehicle_list(tesla)
    if not vehicles:
        return {"error": "No vehicles found"}

    vehicle = None
    if vehicle_id is not None:
        vehicle = next((v for v in vehicles if str(v["id_s"]) == str(vehicle_id)), None)
    if vehicle is None:
        vehicle = vehicles[0]

    if state is None:
        try:
            state = _refresh_state(vehicle)
        except Exception as exc:
            _log_api_error(exc)
            log_vehicle_state(vehicle["id_s"], "offline")
            return {"error": "Vehicle unavailable", "state": "offline"}

    if state != "online":
        if occupant_present and state in ("asleep", "offline"):
            try:
                vehicle.sync_wake_up()
                state = vehicle.get("state") or vehicle["state"]
                log_vehicle_state(vehicle["id_s"], state)
                log_api_data("wake_up", {"state": state})
            except Exception as exc:
                _log_api_error(exc)
                return {"error": str(exc), "state": state}
            if state != "online":
                return {"state": state}
        else:
            return {"state": state}

    try:
        vehicle_data = vehicle.get_vehicle_data()
    except Exception as exc:
        _log_api_error(exc)
        return {"error": str(exc), "state": state}
    track_park_time(vehicle_data)
    track_drive_path(vehicle_data)
    sanitized = sanitize(vehicle_data)
    sanitized["state"] = state
    try:
        v_state = sanitized.get("vehicle_state", {})
        v_config = sanitized.get("vehicle_config", {})
        name = v_state.get("vehicle_name")
        car_type = v_config.get("car_type")
        trim = v_config.get("trim_badging")
        if name and car_type and trim:
            car_map = {
                "models": "Model S",
                "modelx": "Model X",
                "model3": "Model 3",
                "modely": "Model Y",
                "roadster": "Roadster",
                "cybertruck": "Cybertruck",
            }
            car_desc = car_map.get(str(car_type).lower(), car_type)
            v_state["vehicle_name"] = f"{name} ({car_desc} {trim.upper()})"
    except Exception:
        pass
    log_api_data("get_vehicle_data", sanitized)
    sanitized["park_start"] = park_start_ms
    sanitized["park_duration"] = park_duration_string(park_start_ms)
    sanitized["path"] = trip_path
    sanitized["_live"] = True
    return sanitized


def get_vehicle_list():
    """Return a list of available vehicles without exposing VIN."""
    tesla = get_tesla()
    if tesla is None:
        return []
    vehicles = _cached_vehicle_list(tesla)
    sanitized = []
    for idx, v in enumerate(vehicles, start=1):
        name = v.get("display_name")
        if not name:
            name = f"Fahrzeug {idx}"
        sanitized.append({"id": v["id_s"], "display_name": name})
    return sanitized


def reverse_geocode(lat, lon):
    """Return address information for given coordinates using OpenStreetMap."""

    headers = {"User-Agent": "TeslaDashboard/1.0"}
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"lat": lat, "lon": lon, "format": "jsonv2"}
        r = requests.get(url, params=params, headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        return {"address": data.get("display_name"), "raw": data}
    except Exception as exc:
        _log_api_error(exc)
        try:
            url = "https://photon.komoot.io/reverse"
            params = {"lat": lat, "lon": lon}
            r = requests.get(url, params=params, headers=headers, timeout=5)
            r.raise_for_status()
            data = r.json()
            features = data.get("features")
            if features:
                props = features[0].get("properties", {})
                parts = []
                street = props.get("street")
                if street:
                    if props.get("housenumber"):
                        street += f" {props['housenumber']}"
                    parts.append(street)
                city = props.get("city") or props.get("locality")
                district = props.get("district")
                if props.get("postcode") and city:
                    city_text = city
                    if district and district != city:
                        city_text += f"-{district}"
                    parts.append(f"{props['postcode']} {city_text}")
                elif city:
                    parts.append(city)
                if not parts and props.get("name"):
                    parts.append(props["name"])
                label = ", ".join(parts)
                if label:
                    return {"address": label, "raw": data}
        except Exception as exc2:
            _log_api_error(exc2)
        return {}


def _fetch_data_once(vehicle_id):
    """Return current data or cached values based on vehicle state."""
    if vehicle_id is None:
        raise ValueError("vehicle_id required")
    vid = vehicle_id
    cache_id = vehicle_id

    cached = _load_cached(cache_id)

    state = last_vehicle_state.get(vid)
    # Always refresh the vehicle state so transitions from offline/asleep
    # are detected even when no occupant is present.
    state_info = get_vehicle_state(vid)
    state = state_info.get("state") if isinstance(state_info, dict) else state

    data = None
    live = False
    if state == "online" or occupant_present:
        data = get_vehicle_data(vid, state=state)
        if (
            isinstance(data, dict)
            and not data.get("error")
            and data.get("state") == "online"
        ):
            live = True
        else:
            cached = _load_cached(cache_id)
            if cached is not None:
                data = cached
                if isinstance(data, dict):
                    data["state"] = state
            else:
                data = {"state": state}
    else:
        cached = _load_cached(cache_id)
        if cached is not None:
            data = cached
            if isinstance(data, dict):
                data["state"] = state
        else:
            data = {"state": state}

    if isinstance(data, dict):
        last_val = None
        start_val = None
        if isinstance(cached, dict):
            last_val = cached.get("last_charge_energy_added")
            start_val = cached.get("charging_start_energy")
        if last_val is None:
            last_val = _load_last_energy(cache_id)

        charge = data.get("charge_state", {})
        val = charge.get("charge_energy_added")
        saved_val = last_val

        if val is not None:
            if last_val is not None and val < last_val:
                # Finish previous session before counter resets
                if start_val is not None:
                    added = last_val - start_val
                    if added > 0:
                        _log_energy(cache_id, added)
                _save_last_energy(cache_id, last_val)
                saved_val = last_val
                start_val = val
            if charge.get("charging_state") == "Charging" and start_val is None:
                start_val = val

            last_val = val

            end_state = charge.get("charging_state")
            if end_state in ("Complete", "Disconnected"):
                if start_val is not None:
                    added = last_val - start_val
                    if added > 0:
                        _log_energy(cache_id, added)
                _save_last_energy(cache_id, last_val)
                saved_val = last_val
                start_val = None
        elif charge.get("charging_state") in ("Complete", "Disconnected") and last_val is not None:
            if start_val is not None:
                added = last_val - start_val
                if added > 0:
                    _log_energy(cache_id, added)
            _save_last_energy(cache_id, last_val)
            saved_val = last_val
            start_val = None

        if saved_val is not None:
            data["last_charge_energy_added"] = saved_val
        if start_val is not None:
            data["charging_start_energy"] = start_val
        else:
            data.pop("charging_start_energy", None)

    if isinstance(data, dict):
        data["_live"] = live
    latest_data[cache_id] = data
    if isinstance(data, dict):
        try:
            cached_copy = dict(data)
            cached_copy.pop("_live", None)
            _save_cached(cache_id, cached_copy)
        except Exception:
            pass
        for q in subscribers.get(cache_id, []):
            q.put(data)
    return data


def _sleep_idle(seconds):
    """Sleep up to ``seconds`` but return early when occupant presence is detected."""
    remaining = seconds
    while remaining > 0:
        time.sleep(min(1, remaining))
        remaining -= 1
        if occupant_present:
            break


def _fetch_loop(vehicle_id, interval=3):
    """Continuously fetch data for a vehicle and notify subscribers."""
    idle_interval = 30
    while True:
        cfg = load_config()
        try:
            interval = int(cfg.get("api_interval", interval))
        except Exception:
            pass
        try:
            idle_interval = int(cfg.get("api_interval_idle", idle_interval))
        except Exception:
            pass
        data = _fetch_data_once(vehicle_id)
        if isinstance(data, dict) and data.get("_live"):
            try:
                send_aprs(data)
            except Exception:
                pass
        # Use the normal interval whenever someone is in the vehicle, any
        # opening is not fully closed or a drive gear is engaged.  Otherwise
        # fall back to the idle interval so the car can go to sleep.
        door_open = False
        window_open = False
        trunk_open = False
        unlocked = False
        gear_active = False
        charging = False
        present = occupant_present
        if isinstance(data, dict):
            v_state = data.get("vehicle_state", {})
            d_state = data.get("drive_state", {})
            c_state = data.get("charge_state", {})
            door_open = any(v_state.get(k) for k in ["df", "dr", "pf", "pr"])
            window_open = any(
                v_state.get(k) for k in [
                    "fd_window",
                    "rd_window",
                    "fp_window",
                    "rp_window",
                ]
            )
            trunk_open = any(v_state.get(k) for k in ["ft", "rt"])
            unlocked = v_state.get("locked") is False
            present = present or v_state.get("is_user_present")
            gear_active = d_state.get("shift_state") in ("R", "N", "D")
            charging = c_state.get("charging_state") == "Charging"

        if (
            present
            or gear_active
            or door_open
            or window_open
            or trunk_open
            or unlocked
            or charging
        ):
            time.sleep(interval)
        else:
            _sleep_idle(idle_interval)


def _start_thread(vehicle_id):
    """Start background fetching thread for the given vehicle."""
    if vehicle_id in threads:
        return
    t = threading.Thread(target=_fetch_loop, args=(vehicle_id,), daemon=True)
    threads[vehicle_id] = t
    t.start()


# Taximeter instance using the existing fetch function and config-based tariff
taximeter = Taximeter(_fetch_data_once, get_taximeter_tariff)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not username or not email or not password:
            return render_template("register.html", error="Alle Felder sind erforderlich")
        existing = User.query.filter(
            (User.email == email) | (User.username == username)
        ).first()
        if existing:
            return render_template("register.html", error="Benutzer existiert bereits")
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("index"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            args = {}
            if user.subscription == "free":
                args["inactive"] = 1
            return redirect(url_for("index", **args))
        return render_template("login.html", error="Ungültige Zugangsdaten")
    return render_template("login.html", inactive=request.args.get("inactive"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/abo/checkout", methods=["POST"])
@login_required
def subscription_checkout():
    data = request.get_json() or {}
    plan = data.get("plan", "").lower()
    price_id = {
        "basic": os.getenv("STRIPE_BASIC_PRICE_ID"),
        "pro": os.getenv("STRIPE_PRO_PRICE_ID"),
    }.get(plan)
    if not price_id:
        return jsonify({"error": "invalid plan"}), 400
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=url_for("index", _external=True),
        cancel_url=url_for("index", _external=True),
        customer_email=current_user.email,
        metadata={"user_id": current_user.id},
        subscription_data={"metadata": {"user_id": current_user.id}},
    )
    return jsonify({"checkout_url": session.url})


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception:
        return "", 400
    event_type = event.get("type")
    data = event["data"]["object"]
    metadata = data.get("metadata", {})
    user_id = metadata.get("user_id")
    if not user_id and data.get("subscription"):
        try:
            subscription = stripe.Subscription.retrieve(data["subscription"])
            user_id = subscription.get("metadata", {}).get("user_id")
            data = subscription
            event_type = "customer.subscription.updated"
        except Exception:
            return "", 200
    if not user_id:
        return "", 200
    user = User.query.get(int(user_id))
    if not user:
        return "", 200
    if event_type == "invoice.payment_succeeded":
        lines = event["data"]["object"].get("lines", {}).get("data", [])
        price_id = lines[0].get("price", {}).get("id") if lines else None
        user.stripe_subscription_id = event["data"]["object"].get("subscription")
        level = PLAN_PRICES.get(price_id)
        if level:
            user.subscription = level
    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        items = data.get("items", {}).get("data", [])
        price_id = items[0].get("price", {}).get("id") if items else None
        level = PLAN_PRICES.get(price_id)
        if event_type == "customer.subscription.deleted" or data.get("status") == "canceled":
            user.subscription = "free"
            user.stripe_subscription_id = None
        else:
            if level:
                user.subscription = level
            user.stripe_subscription_id = data.get("id")
    db.session.commit()
    return "", 200


@app.route("/account/delete", methods=["POST"])
@login_required
def delete_account():
    cancel_now = bool((request.get_json() or {}).get("immediately"))
    sub_id = current_user.stripe_subscription_id
    if sub_id:
        try:
            if cancel_now:
                stripe.Subscription.delete(sub_id)
            else:
                stripe.Subscription.modify(sub_id, cancel_at_period_end=True)
        except Exception:
            pass
    db.session.delete(current_user)
    db.session.commit()
    logout_user()
    return jsonify({"status": "deleted"})


@app.route("/")
def index():
    admin = User.query.filter_by(role="admin").first()
    cfg = load_config()
    prefix = f"/{g.username_slug}" if hasattr(g, "username_slug") else ""
    inactive = bool(request.args.get("inactive"))
    if current_user.is_authenticated and current_user.subscription == "free":
        inactive = True
    return render_template(
        "index.html",
        version=__version__,
        year=CURRENT_YEAR,
        config=cfg,
        show_banner=not current_user.is_authenticated,
        admin=admin,
        prefix=prefix,
        inactive=inactive,
    )


@app.route("/map")
def map_only():
    """Display only the map without additional modules."""
    prefix = f"/{g.username_slug}" if hasattr(g, "username_slug") else ""
    return render_template("map.html", version=__version__, prefix=prefix)


@app.route("/history")
def trip_history():
    """Show recorded trips and allow selecting a trip to display."""
    paths = _get_trip_files()
    files = [os.path.relpath(p, DATA_DIR) for p in paths]
    weeks, months = _get_trip_periods()
    selected = request.args.get("file")
    path = []
    if selected:
        if selected.startswith("week:"):
            path = _load_trip_period("week", selected.split("week:", 1)[1])
        elif selected.startswith("month:"):
            path = _load_trip_period("month", selected.split("month:", 1)[1])
        else:
            if selected not in files and files:
                selected = files[-1]
            path = _load_trip(os.path.join(DATA_DIR, selected)) if selected else []
    elif files:
        selected = files[-1]
        path = _load_trip(os.path.join(DATA_DIR, selected))
    heading = 0.0
    if path:
        first = path[0]
        if len(first) >= 6 and first[5] is not None:
            heading = first[5]
        elif len(path) >= 2:
            heading = _bearing(path[0][:2], path[1][:2])
    weekly, monthly = compute_trip_summaries()
    cfg = load_config()
    prefix = f"/{g.username_slug}" if hasattr(g, "username_slug") else ""
    return render_template(
        "history.html",
        path=path,
        heading=heading,
        files=files,
        weeks=weeks,
        months=months,
        selected=selected,
        weekly=weekly,
        monthly=monthly,
        config=cfg,
        prefix=prefix,
    )


@app.route("/daten/<vehicle_id>")
@app.route("/data/<vehicle_id>")
def data_only(vehicle_id):
    """Display live or cached vehicle data without extra UI."""
    _start_thread(vehicle_id)
    data = latest_data.get(vehicle_id)
    if data is None:
        data = _fetch_data_once(vehicle_id)
    prefix = f"/{g.username_slug}" if hasattr(g, "username_slug") else ""
    return render_template("data.html", data=data, prefix=prefix)


@app.route("/api/data/<vehicle_id>")
@tesla_token_required
def api_data_vehicle(vehicle_id):
    _start_thread(vehicle_id)
    data = latest_data.get(vehicle_id)
    if data is None:
        data = _fetch_data_once(vehicle_id)
    return jsonify(data)


@app.route("/stream/<vehicle_id>")
@tesla_token_required
def stream_vehicle(vehicle_id):
    """Stream vehicle data to the client using Server-Sent Events."""
    if not vehicle_id:
        raise ValueError("vehicle_id required")
    _start_thread(vehicle_id)

    def gen():
        q = queue.Queue()
        subscribers.setdefault(vehicle_id, []).append(q)
        try:
            # Send the latest data immediately if available
            if vehicle_id in latest_data:
                yield f"data: {json.dumps(latest_data[vehicle_id])}\n\n"
            while True:
                try:
                    data = q.get(timeout=15)
                    msg = f"data: {json.dumps(data)}\n\n"
                except queue.Empty:
                    # Periodically send a comment to keep the connection alive
                    msg = ": ping\n\n"
                try:
                    yield msg
                except GeneratorExit:
                    break
        finally:
            try:
                subscribers.get(vehicle_id, []).remove(q)
            except ValueError:
                pass

    return Response(gen(), mimetype="text/event-stream")


@app.route("/api/vehicles")
@tesla_token_required
def api_vehicles():
    vehicles = get_vehicle_list()
    return jsonify(vehicles)


@app.route("/api/state/<vehicle_id>")
@tesla_token_required
def api_state(vehicle_id):
    """Return the last known state of the vehicle."""
    state_info = get_vehicle_state(vehicle_id)
    return jsonify(state_info)


@app.route("/api/version")
def api_version():
    """Return the current application version."""
    return jsonify({"version": __version__})


@app.route("/api/clients")
def api_clients():
    """Return the current number of connected streaming clients."""
    count = sum(len(v) for v in subscribers.values())
    return jsonify({"clients": count})


@app.route("/api/reverse_geocode")
def api_reverse_geocode():
    """Return address for given coordinates."""
    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"error": "Missing coordinates"}), 400
    result = reverse_geocode(lat, lon)
    return jsonify(result)


@app.route("/api/config")
def api_config():
    """Return visibility configuration as JSON."""
    return jsonify(load_config())


@app.route("/api/announcement")
def api_announcement():
    """Return the current announcement text."""
    cfg = load_config()
    text = cfg.get("announcement", "")
    info = get_news_events_info()
    if info:
        text = text + ("\n" if text else "") + info
    return jsonify({"announcement": text})


@app.route("/api/alarm_state/<vehicle_id>")
@tesla_token_required
def api_alarm_state(vehicle_id):
    """Return the current alarm state."""
    _start_thread(vehicle_id)
    data = latest_data.get(vehicle_id)
    if data is None:
        data = _fetch_data_once(vehicle_id)
    alarm = None
    if isinstance(data, dict):
        alarm = data.get("alarm_state")
        if alarm is None:
            vs = data.get("vehicle_state", {})
            alarm = vs.get("alarm_state")
    return jsonify({"alarm_state": alarm})


@app.route("/api/occupant", methods=["GET", "POST"])
def api_occupant():
    """Return or update occupant presence status."""
    global occupant_present
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        val = data.get("present")
        if isinstance(val, str):
            occupant_present = val.lower() in ("1", "true", "yes")
        else:
            occupant_present = bool(val)
    return jsonify({"present": occupant_present})


def _format_phone(phone, region="DE"):
    """Return ``phone`` normalized to E.164 or ``None`` if invalid."""
    if not phone:
        return None
    if phonenumbers is None:
        return phone if phone.startswith("+") else None
    try:
        parsed = phonenumbers.parse(phone, None if phone.startswith("+") else region)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        return None


@app.route("/api/sms", methods=["POST"])
@admin_only
def api_sms():
    """Send a short text message using the configured phone number."""
    cfg = load_config()
    if not cfg.get("sms_enabled", True):
        return jsonify({"success": False, "error": "SMS disabled"}), 400
    phone = cfg.get("phone_number")
    api_key = cfg.get("infobip_api_key")
    base_url = cfg.get("infobip_base_url", "https://api.infobip.com")
    sms_sender_id = cfg.get("sms_sender_id", "").strip()
    if not phone:
        return jsonify({"success": False, "error": "No phone number configured"}), 400
    phone = _format_phone(phone)
    if not phone:
        return jsonify({"success": False, "error": "Invalid phone number"}), 400
    if not api_key:
        return jsonify({"success": False, "error": "No API key configured"}), 400
    drive_only = cfg.get("sms_drive_only", True)
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    name = data.get("name", "").strip()
    if not message:
        return jsonify({"success": False, "error": "Missing message"}), 400
    if name:
        message = f"{name}: {message}"
    if len(message) > 160:
        return jsonify({"success": False, "error": "Message too long"}), 400
    if drive_only and last_shift_state in (None, "P"):
        now_ms = int(time.time() * 1000)
        if park_start_ms is None or now_ms - park_start_ms > 300000:
            return (
                jsonify({"success": False, "error": "SMS only allowed while driving"}),
                400,
            )
    try:
        if not base_url.startswith("http"):
            base_url = "https://" + base_url
        url = base_url.rstrip("/") + "/sms/2/text/advanced"
        sms_payload = {"destinations": [{"to": phone}], "text": message}
        if sms_sender_id:
            sms_payload["from"] = sms_sender_id
        resp = requests.post(
            url,
            json={"messages": [sms_payload]},
            headers={
                "Authorization": f"App {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=10,
        )
        success = 200 <= resp.status_code < 300
        veh = Vehicle.query.filter_by(user_id=current_user.id).first()
        ext_id = veh.vehicle_id if veh else None
        _log_sms(message, success, ext_id)
        if success:
            return jsonify({"success": True})
        try:
            error = resp.json().get("requestError", {}).get("serviceException", {}).get("text")
        except Exception:
            error = resp.text
        return jsonify({"success": False, "error": error})
    except Exception as exc:
        veh = Vehicle.query.filter_by(user_id=current_user.id).first()
        ext_id = veh.vehicle_id if veh else None
        _log_sms(message, False, ext_id)
        return jsonify({"success": False, "error": str(exc)})


@app.route("/config", methods=["GET", "POST"])
@ham_only
def config_page():
    if hasattr(g, "username_slug"):
        if current_user.role != "admin" and current_user.username_slug != g.username_slug:
            abort(403)
    cfg = load_config()
    if request.method == "POST":
        for item in CONFIG_ITEMS:
            vis = _get_visibility(item["id"])
            required = vis.required_subscription if vis else "free"
            locked = False
            if not (vis and vis.always_active):
                user_level = getattr(current_user, "subscription", "free")
                locked = SUBSCRIPTION_LEVELS.get(user_level, 0) < SUBSCRIPTION_LEVELS.get(
                    required, 0
                )
            if locked:
                continue
            cfg[item["id"]] = item["id"] in request.form
        callsign = request.form.get("aprs_callsign", "").strip()
        passcode = request.form.get("aprs_passcode", "").strip()
        wx_callsign = request.form.get("aprs_wx_callsign", "").strip()
        wx_enabled = "aprs_wx_enabled" in request.form
        aprs_comment = request.form.get("aprs_comment", "").strip()
        if current_user.role != "admin" and not (
            hasattr(g, "username_slug") and current_user.is_ham_operator
        ):
            if (
                callsign
                or passcode
                or wx_callsign
                or aprs_comment
                or "aprs_wx_enabled" in request.form
            ):
                abort(403, description="APRS configuration requires admin")
        announcement = request.form.get("announcement", "").strip()
        taxi_company = request.form.get("taxi_company", "").strip()
        taxi_slogan = request.form.get("taxi_slogan", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        if phone_number:
            phone_number = _format_phone(phone_number) or phone_number
        infobip_api_key = request.form.get("infobip_api_key", "").strip()
        infobip_base_url = request.form.get("infobip_base_url", "").strip()
        sms_sender_id = request.form.get("sms_sender_id", "").strip()
        sms_enabled = "sms_enabled" in request.form
        sms_drive_only = "sms_drive_only" in request.form
        api_interval = request.form.get("api_interval", "").strip()
        api_interval_idle = request.form.get("api_interval_idle", "").strip()
        tariff_base = request.form.get("tariff_base", "").replace(",", ".").strip()
        tariff_12 = request.form.get("tariff_12", "").replace(",", ".").strip()
        tariff_34 = request.form.get("tariff_34", "").replace(",", ".").strip()
        tariff_5 = request.form.get("tariff_5", "").replace(",", ".").strip()
        wait_price = request.form.get("wait_price", "").replace(",", ".").strip()
        if "refresh_vehicle_list" in request.form:
            tesla = get_tesla()
            if tesla is not None:
                _cached_vehicle_list(tesla, ttl=0)
        if callsign:
            cfg["aprs_callsign"] = callsign
        elif "aprs_callsign" in cfg:
            cfg.pop("aprs_callsign")
        if passcode:
            cfg["aprs_passcode"] = passcode
        elif "aprs_passcode" in cfg:
            cfg.pop("aprs_passcode")
        if wx_callsign:
            cfg["aprs_wx_callsign"] = wx_callsign
        elif "aprs_wx_callsign" in cfg:
            cfg.pop("aprs_wx_callsign")
        cfg["aprs_wx_enabled"] = wx_enabled
        if aprs_comment:
            cfg["aprs_comment"] = aprs_comment
        elif "aprs_comment" in cfg:
            cfg.pop("aprs_comment")
        if announcement:
            cfg["announcement"] = announcement
        elif "announcement" in cfg:
            cfg.pop("announcement")
        if taxi_company:
            cfg["taxi_company"] = taxi_company
        elif "taxi_company" in cfg:
            cfg.pop("taxi_company")
        if taxi_slogan:
            cfg["taxi_slogan"] = taxi_slogan
        elif "taxi_slogan" in cfg:
            cfg.pop("taxi_slogan")
        if phone_number:
            cfg["phone_number"] = phone_number
        elif "phone_number" in cfg:
            cfg.pop("phone_number")
        if infobip_api_key:
            cfg["infobip_api_key"] = infobip_api_key
        elif "infobip_api_key" in cfg:
            cfg.pop("infobip_api_key")
        if infobip_base_url:
            cfg["infobip_base_url"] = infobip_base_url
        elif "infobip_base_url" in cfg:
            cfg.pop("infobip_base_url")
        if sms_sender_id:
            cfg["sms_sender_id"] = sms_sender_id
        elif "sms_sender_id" in cfg:
            cfg.pop("sms_sender_id")
        cfg["sms_enabled"] = sms_enabled
        cfg["sms_drive_only"] = sms_drive_only

        def _to_float(val):
            try:
                return float(val)
            except ValueError:
                return None

        tariff_cfg = cfg.get("taximeter_tariff", {})
        if not isinstance(tariff_cfg, dict):
            tariff_cfg = {}
        v = _to_float(tariff_base)
        if v is not None:
            tariff_cfg["base"] = v
        v = _to_float(tariff_12)
        if v is not None:
            tariff_cfg["rate_1_2"] = v
        v = _to_float(tariff_34)
        if v is not None:
            tariff_cfg["rate_3_4"] = v
        v = _to_float(tariff_5)
        if v is not None:
            tariff_cfg["rate_5_plus"] = v
        v = _to_float(wait_price)
        if v is not None:
            tariff_cfg["wait_per_10s"] = v
        if tariff_cfg:
            cfg["taximeter_tariff"] = tariff_cfg
        elif "taximeter_tariff" in cfg:
            cfg.pop("taximeter_tariff")

        if api_interval.isdigit():
            cfg["api_interval"] = max(1, int(api_interval))
        elif "api_interval" in cfg:
            cfg.pop("api_interval")
        if api_interval_idle.isdigit():
            cfg["api_interval_idle"] = max(1, int(api_interval_idle))
        elif "api_interval_idle" in cfg:
            cfg.pop("api_interval_idle")
        save_config(cfg)
    prefix = f"/{g.username_slug}" if hasattr(g, "username_slug") else ""
    user_level = getattr(current_user, "subscription", "free")
    items = []
    for item in CONFIG_ITEMS:
        vis = _get_visibility(item["id"])
        required = vis.required_subscription if vis else "free"
        always = vis.always_active if vis else False
        locked = not always and SUBSCRIPTION_LEVELS.get(user_level, 0) < SUBSCRIPTION_LEVELS.get(
            required, 0
        )
        item_copy = item.copy()
        item_copy["required_subscription"] = required
        item_copy["locked"] = locked
        items.append(item_copy)
    return render_template("config.html", items=items, config=cfg, prefix=prefix)


@app.route("/error")
def error_page():
    """Display collected API errors."""
    with api_errors_lock:
        errors = list(api_errors)
    for e in errors:
        try:
            e["time_str"] = datetime.fromtimestamp(
                e["timestamp"], LOCAL_TZ
            ).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            e["time_str"] = str(e["timestamp"])
    return render_template("errors.html", errors=errors)


@app.route("/statistik")
def statistics_page():
    """Display statistics of vehicle state and distance."""
    stats = compute_statistics()
    current_month = datetime.now(LOCAL_TZ).strftime("%Y-%m")
    monthly = {}
    rows = []
    for day in sorted(stats.keys()):
        entry = stats[day]
        if day.startswith(current_month):
            row = {
                "date": day,
                "online": entry.get("online", 0.0),
                "offline": entry.get("offline", 0.0),
                "asleep": entry.get("asleep", 0.0),
                "km": round(entry.get("km", 0.0), 2),
                "speed": int(round(entry.get("speed", 0.0))),
                "energy": round(entry.get("energy", 0.0), 2),
            }
            total = row["online"] + row["offline"] + row["asleep"]
            diff = round(100.0 - total, 2)
            row["offline"] = round(row["offline"] + diff, 2)
            rows.append(row)
            continue
        month = day[:7]
        m = monthly.setdefault(
            month,
            {
                "online_sum": 0.0,
                "offline_sum": 0.0,
                "asleep_sum": 0.0,
                "km": 0.0,
                "speed": 0.0,
                "energy": 0.0,
                "count": 0,
            },
        )
        m["online_sum"] += entry.get("online", 0.0)
        m["offline_sum"] += entry.get("offline", 0.0)
        m["asleep_sum"] += entry.get("asleep", 0.0)
        m["km"] += entry.get("km", 0.0)
        m["energy"] += entry.get("energy", 0.0)
        m["speed"] = max(m["speed"], entry.get("speed", 0.0))
        m["count"] += 1

    monthly_rows = []
    for month in sorted(monthly.keys()):
        data = monthly[month]
        cnt = data["count"] or 1
        row = {
            "date": month,
            "online": round(data["online_sum"] / cnt, 2),
            "offline": round(data["offline_sum"] / cnt, 2),
            "asleep": round(data["asleep_sum"] / cnt, 2),
            "km": round(data["km"], 2),
            "speed": int(round(data["speed"])),
            "energy": round(data["energy"], 2),
        }
        total = row["online"] + row["offline"] + row["asleep"]
        diff = round(100.0 - total, 2)
        row["offline"] = round(row["offline"] + diff, 2)
        monthly_rows.append(row)

    rows = monthly_rows + rows
    cfg = load_config()
    prefix = f"/{g.username_slug}" if hasattr(g, "username_slug") else ""
    return render_template("statistik.html", rows=rows, config=cfg, prefix=prefix)


@app.route("/api/errors")
def api_errors_route():
    """Return collected API errors as JSON."""
    with api_errors_lock:
        return jsonify(list(api_errors))


@app.route("/apiliste")
def api_list_file():
    """Return the aggregated API key list as plain text."""
    lines = []
    for entry in ApiLog.query.order_by(ApiLog.created_at).all():
        if entry.endpoint.startswith("path[") or entry.endpoint.startswith("path:"):
            continue
        try:
            data = json.loads(entry.data) if entry.data else None
            line = json.dumps({"endpoint": entry.endpoint, "data": data})
        except Exception:
            line = entry.endpoint
        lines.append(line + "\n")
    content = "".join(lines)
    return Response(content, mimetype="text/plain")


@app.route("/state")
def state_log_page():
    """Display the vehicle state log."""
    log_lines = []
    for entry in VehicleState.query.order_by(VehicleState.created_at).all():
        veh = Vehicle.query.get(entry.vehicle_id)
        data = {"vehicle_id": veh.vehicle_id if veh else None, "state": entry.state}
        ts = entry.created_at.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
        log_lines.append(f"{ts} {json.dumps(data)}\n")
    return render_template("state.html", log_lines=log_lines)


@app.route("/apilog")
def api_log_page():
    """Display the API log."""
    log_lines = []
    for entry in ApiLog.query.order_by(ApiLog.created_at).all():
        try:
            data = json.loads(entry.data) if entry.data else None
        except Exception:
            data = None
        ts = entry.created_at.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
        line = json.dumps({"endpoint": entry.endpoint, "data": data})
        log_lines.append(f"{ts} {line}\n")
    return render_template("apilog.html", log_lines=log_lines)


@app.route("/sms")
@admin_only
def sms_log_page():
    """Display the SMS log."""
    log_lines = []
    for entry in SmsLog.query.order_by(SmsLog.created_at).all():
        veh = Vehicle.query.get(entry.vehicle_id)
        data = {"vehicle_id": veh.vehicle_id if veh else None, "message": entry.message, "success": entry.success}
        ts = entry.created_at.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
        log_lines.append(f"{ts} {json.dumps(data)}\n")
    return render_template("sms.html", log_lines=log_lines)


@app.route("/taxameter")
@admin_only
def taxameter_page():
    vehicle_id = request.args.get("vehicle_id")
    if not vehicle_id:
        abort(400)
    cfg = load_config()
    company = cfg.get("taxi_company", "Taxi Schauer")
    file_opts = []
    selected = None
    trips = []

    return render_template(
        "taxameter.html",
        company=company,
        config=cfg,
        trips=trips,
        trip_files=file_opts,
        vehicle_id=vehicle_id,
        selected_file=selected,
    )


@app.route("/api/taxameter/start", methods=["POST"])
@admin_only
def api_taxameter_start():
    vid = request.form.get("vehicle_id")
    if not vid:
        return jsonify({"error": "vehicle_id required"}), 400
    vehicle = Vehicle.query.filter_by(vehicle_id=vid).first()
    if not vehicle:
        return jsonify({"error": "vehicle not found"}), 404
    taximeter.vehicle_id = vid
    taximeter.vehicle_db_id = vehicle.id
    taximeter.user_id = current_user.id
    _start_thread(vid)
    taximeter.start()
    return jsonify(taximeter.status())


@app.route("/api/taxameter/pause", methods=["POST"])
@admin_only
def api_taxameter_pause():
    vid = request.form.get("vehicle_id")
    if not vid:
        return jsonify({"error": "vehicle_id required"}), 400
    vehicle = Vehicle.query.filter_by(vehicle_id=vid).first()
    if not vehicle:
        return jsonify({"error": "vehicle not found"}), 404
    taximeter.vehicle_id = vid
    taximeter.vehicle_db_id = vehicle.id
    taximeter.user_id = current_user.id
    taximeter.pause()
    return jsonify(taximeter.status())


@app.route("/api/taxameter/stop", methods=["POST"])
@admin_only
def api_taxameter_stop():
    vid = request.form.get("vehicle_id")
    if not vid:
        return jsonify({"error": "vehicle_id required"}), 400
    vehicle = Vehicle.query.filter_by(vehicle_id=vid).first()
    if not vehicle:
        return jsonify({"error": "vehicle not found"}), 404
    taximeter.vehicle_id = vid
    taximeter.vehicle_db_id = vehicle.id
    taximeter.user_id = current_user.id
    result = taximeter.stop()
    if result:
        company = get_taxi_company()
        slogan = get_taxi_slogan()
        ride_id = result.get("ride_id")
        if ride_id is not None:
            receipt_data = {
                "company": company,
                "slogan": slogan,
                "breakdown": result.get("breakdown", {}),
                "distance": result.get("distance", 0.0),
            }
            url = url_for("taxameter_receipt", ride_id=ride_id, _external=True)
            img = qrcode.make(url)
            buf = BytesIO()
            img.save(buf, format="PNG")
            qr_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            receipt_data["qr_code"] = f"data:image/png;base64,{qr_b64}"
            result["qr_code"] = receipt_data["qr_code"]
            result["receipt_url"] = url
            ride = TaximeterRide.query.get(ride_id)
            if ride:
                ride.receipt_json = json.dumps(receipt_data)
                db.session.commit()
        result["company"] = company
        result["slogan"] = slogan
    return jsonify(result or {"active": False})


@app.route("/api/taxameter/reset", methods=["POST"])
@admin_only
def api_taxameter_reset():
    vid = request.form.get("vehicle_id")
    if not vid:
        return jsonify({"error": "vehicle_id required"}), 400
    vehicle = Vehicle.query.filter_by(vehicle_id=vid).first()
    if not vehicle:
        return jsonify({"error": "vehicle not found"}), 404
    taximeter.vehicle_id = vid
    taximeter.vehicle_db_id = vehicle.id
    taximeter.user_id = current_user.id
    taximeter.reset()
    return jsonify({"active": False})


@app.route("/api/taxameter/status")
@admin_only
def api_taxameter_status():
    vid = request.args.get("vehicle_id")
    if not vid:
        return jsonify({"error": "vehicle_id required"}), 400
    vehicle = Vehicle.query.filter_by(vehicle_id=vid).first()
    if not vehicle:
        return jsonify({"error": "vehicle not found"}), 404
    taximeter.vehicle_id = vid
    taximeter.vehicle_db_id = vehicle.id
    taximeter.user_id = current_user.id
    return jsonify(taximeter.status())


@app.route("/api/taxameter/trips")
@admin_only
def api_taxameter_trips():
    """Return individual trips for a recorded file."""
    selected = request.args.get("file")
    if not selected or ".." in selected or not selected.endswith(".csv"):
        abort(404)
    path = os.path.join(DATA_DIR, selected)
    if not os.path.exists(path):
        abort(404)
    segments = _split_trip_segments(path)
    result = []
    for idx, seg in enumerate(segments, 1):
        if seg["start"] is None:
            continue
        start_dt = datetime.fromtimestamp(seg["start"], LOCAL_TZ)
        end_dt = datetime.fromtimestamp(seg["end"], LOCAL_TZ)
        label = f"{start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%H:%M')}"
        value = f"file={selected}&segment={idx}"
        result.append({"value": value, "label": label})
    return jsonify(result)


@app.route("/taxameter/receipt/<int:ride_id>")
def taxameter_receipt(ride_id):
    ride = TaximeterRide.query.get_or_404(ride_id)
    if not ride.receipt_json:
        abort(404)
    try:
        data = json.loads(ride.receipt_json)
    except Exception:
        abort(404)
    return render_template("taxameter_receipt.html", **data)


@app.route("/taxameter/trip_receipt")
def taxameter_trip_receipt():
    """Create a taximeter receipt for a recorded trip."""
    selected = request.args.get("file")
    if not selected:
        abort(404)
    if selected.startswith("week:"):
        key = selected.split("week:", 1)[1]
        dist = _period_distance("week", key)
        wait_time = 0.0
    elif selected.startswith("month:"):
        key = selected.split("month:", 1)[1]
        dist = _period_distance("month", key)
        wait_time = 0.0
    else:
        try:
            trip_id = int(selected)
        except ValueError:
            abort(404)
        trip = TripEntry.query.get_or_404(trip_id)
        dist = float(trip.distance_km or 0.0)
        wait_time = 0.0
    tariff = get_taximeter_tariff()
    tm = Taximeter(lambda _vid: {}, get_taximeter_tariff)
    tm.tariff = tariff
    tm.wait_time = wait_time
    tm.wait_cost = int(wait_time // 10) * tariff.get("wait_per_10s", 0.10)
    breakdown = tm._calc_breakdown(dist)
    company = get_taxi_company()
    slogan = get_taxi_slogan()
    return render_template(
        "taxameter_receipt.html",
        company=company,
        slogan=slogan,
        breakdown=breakdown,
        distance=dist,
        qr_code=None,
    )


@app.route("/debug")
def debug_info():
    """Display diagnostic information about the server."""
    env_info = {
        "teslapy_available": teslapy is not None,
        "has_email": bool(os.getenv("TESLA_EMAIL")),
        "has_password": bool(os.getenv("TESLA_PASSWORD")),
        "has_access_token": bool(os.getenv("TESLA_ACCESS_TOKEN")),
        "has_refresh_token": bool(os.getenv("TESLA_REFRESH_TOKEN")),
    }

    log_lines = []
    entries = (
        ApiLog.query.order_by(ApiLog.created_at.desc()).limit(50).all()
    )
    for entry in reversed(entries):
        try:
            data = json.loads(entry.data) if entry.data else None
        except Exception:
            data = None
        ts = entry.created_at.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
        line = json.dumps({"endpoint": entry.endpoint, "data": data})
        log_lines.append(f"{ts} {line}\n")

    return render_template(
        "debug.html", env_info=env_info, log_lines=log_lines, latest=latest_data
    )


# Blueprint for user-specific routes
user_bp = Blueprint("user", __name__, url_prefix="/<username_slug>")


@user_bp.before_request
def _ensure_user():
    slug = request.view_args.get("username_slug")
    if not slug:
        return
    normalized = slug.lower()
    if slug != normalized:
        return redirect(request.url.replace(f"/{slug}", f"/{normalized}", 1))
    User.query.filter_by(username_slug=normalized).first_or_404()
    g.username_slug = normalized


user_bp.add_url_rule("", view_func=index)
user_bp.add_url_rule("/map", view_func=map_only)
user_bp.add_url_rule("/history", view_func=trip_history)
user_bp.add_url_rule("/statistik", view_func=statistics_page)
user_bp.add_url_rule("/data/<vehicle_id>", view_func=data_only)
user_bp.add_url_rule("/daten/<vehicle_id>", view_func=data_only)
user_bp.add_url_rule("/config", view_func=config_page, methods=["GET", "POST"])
user_bp.add_url_rule("/api/data/<vehicle_id>", view_func=api_data_vehicle)
user_bp.add_url_rule("/api/vehicles", view_func=api_vehicles)
user_bp.add_url_rule("/api/state/<vehicle_id>", view_func=api_state)
user_bp.add_url_rule("/api/version", view_func=api_version)
user_bp.add_url_rule("/api/clients", view_func=api_clients)
user_bp.add_url_rule("/api/reverse_geocode", view_func=api_reverse_geocode)
user_bp.add_url_rule("/api/config", view_func=api_config)
user_bp.add_url_rule("/api/announcement", view_func=api_announcement)
user_bp.add_url_rule("/api/alarm_state/<vehicle_id>", view_func=api_alarm_state)
user_bp.add_url_rule(
    "/api/occupant", view_func=api_occupant, methods=["GET", "POST"]
)
user_bp.add_url_rule("/api/errors", view_func=api_errors_route)
user_bp.add_url_rule("/stream/<vehicle_id>", view_func=stream_vehicle)
user_bp.add_url_rule("/error", view_func=error_page)
user_bp.add_url_rule("/debug", view_func=debug_info)
user_bp.add_url_rule("/apiliste", view_func=api_list_file)
user_bp.add_url_rule("/state", view_func=state_log_page)
user_bp.add_url_rule("/apilog", view_func=api_log_page)

app.register_blueprint(user_bp)
app.register_blueprint(auth_bp)


@app.cli.command("migrate-files-to-admin")
@click.option("--admin", "admin_name", required=True, help="Admin username or email")
@click.option("--dry-run", is_flag=True, help="Do not write to the database or delete files")
def migrate_files_to_admin(admin_name, dry_run):
    """Import legacy data files into the database for the given admin user."""
    from pathlib import Path
    from collections import defaultdict
    import json
    import csv
    from sqlalchemy import or_
    from models import (
        User,
        Vehicle,
        VehicleState,
        EnergyLog,
        SmsLog,
        ApiLog,
        TripEntry,
        StatisticsEntry,
    )

    admin = (
        User.query.filter(
            or_(User.username_slug == admin_name, User.email == admin_name),
            User.role == "admin",
        ).one_or_none()
    )
    if not admin:
        raise click.ClickException("Admin user not found")

    data_dir = Path(app.static_folder) / "data"
    report = defaultdict(lambda: {"imported": 0, "skipped": 0, "deleted": 0})

    def _resolve_vehicle(ext_id):
        veh = Vehicle.query.filter_by(vehicle_id=str(ext_id)).first()
        return veh.id if veh else None

    def _upsert(model, unique_fields, obj):
        filters = {k: getattr(obj, k) for k in unique_fields}
        exists = model.query.filter_by(**filters).first()
        if exists:
            return False
        db.session.add(obj)
        return True

    def _parse_line(line):
        idx = line.find("{")
        if idx == -1:
            return None, None
        ts = line[:idx].strip()
        data = json.loads(line[idx:])
        dt = _parse_log_time(ts)
        return dt, data

    def _vehicle_from_path(path):
        rel = path.relative_to(data_dir)
        if not rel.parts:
            return None
        ext_id = rel.parts[0]
        if ext_id == "default":
            return None
        return _resolve_vehicle(ext_id)

    # state.log
    for path in data_dir.rglob("state.log"):
        stats = report["state.log"]
        vid = _vehicle_from_path(path)
        if vid is None:
            stats["skipped"] += 1
            continue
        entries = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        dt, data = _parse_line(line)
                        if dt is None:
                            continue
                        entries.append(
                            VehicleState(
                                user_id=admin.id,
                                vehicle_id=vid,
                                state=data.get("state"),
                                created_at=dt,
                            )
                        )
                    except Exception:
                        pass
        except Exception:
            stats["skipped"] += 1
            continue
        if not dry_run:
            try:
                for obj in entries:
                    if _upsert(
                        VehicleState,
                        ("user_id", "vehicle_id", "created_at", "state"),
                        obj,
                    ):
                        stats["imported"] += 1
                db.session.commit()
                path.unlink()
                stats["deleted"] += 1
            except Exception:
                db.session.rollback()
                stats["skipped"] += 1
        else:
            stats["imported"] += len(entries)

    # energy.log
    for path in data_dir.rglob("energy.log"):
        stats = report["energy.log"]
        vid = _vehicle_from_path(path)
        if vid is None:
            stats["skipped"] += 1
            continue
        entries = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        dt, data = _parse_line(line)
                        if dt is None:
                            continue
                        entries.append(
                            EnergyLog(
                                user_id=admin.id,
                                vehicle_id=vid,
                                added_energy=float(data.get("added_energy", 0.0)),
                                created_at=dt,
                            )
                        )
                    except Exception:
                        pass
        except Exception:
            stats["skipped"] += 1
            continue
        if not dry_run:
            try:
                for obj in entries:
                    if _upsert(
                        EnergyLog,
                        ("user_id", "vehicle_id", "created_at"),
                        obj,
                    ):
                        stats["imported"] += 1
                db.session.commit()
                path.unlink()
                stats["deleted"] += 1
            except Exception:
                db.session.rollback()
                stats["skipped"] += 1
        else:
            stats["imported"] += len(entries)

    # sms.log
    for path in data_dir.rglob("sms.log"):
        stats = report["sms.log"]
        vid = _vehicle_from_path(path)
        if vid is None:
            stats["skipped"] += 1
            continue
        entries = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        dt, data = _parse_line(line)
                        if dt is None:
                            continue
                        entries.append(
                            SmsLog(
                                user_id=admin.id,
                                vehicle_id=vid,
                                message=data.get("message", ""),
                                success=bool(data.get("success")),
                                created_at=dt,
                            )
                        )
                    except Exception:
                        pass
        except Exception:
            stats["skipped"] += 1
            continue
        if not dry_run:
            try:
                for obj in entries:
                    if _upsert(
                        SmsLog,
                        ("user_id", "vehicle_id", "created_at", "message"),
                        obj,
                    ):
                        stats["imported"] += 1
                db.session.commit()
                path.unlink()
                stats["deleted"] += 1
            except Exception:
                db.session.rollback()
                stats["skipped"] += 1
        else:
            stats["imported"] += len(entries)

    # api-liste.txt
    for path in data_dir.rglob("api-liste.txt"):
        stats = report["api-liste.txt"]
        vid = _vehicle_from_path(path)
        if vid is None:
            stats["skipped"] += 1
            continue
        entries = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    entries.append(
                        ApiLog(
                            user_id=admin.id,
                            vehicle_id=vid,
                            endpoint=data.get("endpoint", ""),
                            data=json.dumps(data.get("data")),
                        )
                    )
        except Exception:
            stats["skipped"] += 1
            continue
        if not dry_run:
            try:
                for obj in entries:
                    if _upsert(
                        ApiLog,
                        ("user_id", "vehicle_id", "endpoint"),
                        obj,
                    ):
                        stats["imported"] += 1
                db.session.commit()
                path.unlink()
                stats["deleted"] += 1
            except Exception:
                db.session.rollback()
                stats["skipped"] += 1
        else:
            stats["imported"] += len(entries)

    # trip files
    for path in data_dir.rglob("trips/trip_*.csv"):
        stats = report["trips/trip_*.csv"]
        vid = _vehicle_from_path(path)
        if vid is None:
            stats["skipped"] += 1
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                row = next(reader, None)
            if row is None:
                stats["skipped"] += 1
                continue
            started = datetime.fromisoformat(row.get("started_at")) if row.get("started_at") else datetime.now(timezone.utc)
            ended = datetime.fromisoformat(row.get("ended_at")) if row.get("ended_at") else None
            distance = float(row.get("distance_km", 0.0))
            obj = TripEntry(
                user_id=admin.id,
                vehicle_id=vid,
                started_at=started,
                ended_at=ended,
                distance_km=distance,
            )
        except Exception:
            stats["skipped"] += 1
            continue
        if not dry_run:
            try:
                if _upsert(
                    TripEntry,
                    ("user_id", "vehicle_id", "started_at"),
                    obj,
                ):
                    stats["imported"] += 1
                db.session.commit()
                path.unlink()
                stats["deleted"] += 1
            except Exception:
                db.session.rollback()
                stats["skipped"] += 1
        else:
            stats["imported"] += 1

    # statistik.log
    for path in data_dir.rglob("statistik.log"):
        stats = report["statistik.log"]
        vid = _vehicle_from_path(path)
        if vid is None:
            stats["skipped"] += 1
            continue
        entries = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        dt, data = _parse_line(line)
                        if dt is None:
                            continue
                        entries.append(
                            StatisticsEntry(
                                user_id=admin.id,
                                vehicle_id=vid,
                                name=data.get("name", ""),
                                value=float(data.get("value", 0.0)),
                                created_at=dt,
                            )
                        )
                    except Exception:
                        pass
        except Exception:
            stats["skipped"] += 1
            continue
        if not dry_run:
            try:
                for obj in entries:
                    if _upsert(
                        StatisticsEntry,
                        ("user_id", "vehicle_id", "created_at", "name"),
                        obj,
                    ):
                        stats["imported"] += 1
                db.session.commit()
                path.unlink()
                stats["deleted"] += 1
            except Exception:
                db.session.rollback()
                stats["skipped"] += 1
        else:
            stats["imported"] += len(entries)

    # summary
    total = {"imported": 0, "skipped": 0, "deleted": 0}
    for name, info in report.items():
        click.echo(
            f"{name}: imported={info['imported']} skipped={info['skipped']} deleted={info['deleted']}"
        )
        for k in total:
            total[k] += info[k]
    click.echo(
        f"Total: imported={total['imported']} skipped={total['skipped']} deleted={total['deleted']}"
    )
    if not dry_run:
        # remove empty directories
        for p in sorted(data_dir.rglob("*"), reverse=True):
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()


@app.cli.command("ensure-admin")
@click.argument("email")
@click.argument("username")
@click.password_option()
def ensure_admin(email, username, password):
    """Ensure that an admin user exists."""
    user = User.query.filter(
        (User.email == email) | (User.username == username)
    ).first()
    if not user:
        user = User(email=email, username=username, role="admin")
        user.set_password(password)
        db.session.add(user)
    else:
        user.role = "admin"
        if password:
            user.set_password(password)
    db.session.commit()
    click.echo("Admin ensured")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8013, debug=True)
