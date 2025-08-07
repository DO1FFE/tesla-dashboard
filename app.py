import os
import json
import queue
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
from flask import (
    Flask,
    render_template,
    jsonify,
    Response,
    request,
    send_from_directory,
    abort,
    url_for,
)
from taximeter import Taximeter
import requests
from functools import wraps
from dotenv import load_dotenv
from version import get_version
import qrcode
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
__version__ = get_version()
CURRENT_YEAR = datetime.now(ZoneInfo("Europe/Berlin")).year
GA_TRACKING_ID = os.getenv("GA_TRACKING_ID")


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
    dir_name = str(vehicle_id) if vehicle_id is not None else "default"
    path = os.path.join(DATA_DIR, dir_name)
    os.makedirs(path, exist_ok=True)
    return path


def trip_dir(vehicle_id):
    """Return directory holding trip CSV files for ``vehicle_id``."""
    path = os.path.join(vehicle_dir(vehicle_id), "trips")
    os.makedirs(path, exist_ok=True)
    return path


def receipt_dir():
    """Directory for stored taximeter receipts."""
    path = os.path.join(DATA_DIR, "receipts")
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
            for f in os.listdir(old_trip_dir):
                if f.endswith(".csv"):
                    src = os.path.join(old_trip_dir, f)
                    dst = os.path.join(trip_dir(None), f)
                    if not os.path.exists(dst):
                        os.rename(src, dst)
            try:
                os.rmdir(old_trip_dir)
            except OSError:
                pass
    except Exception:
        pass


migrate_legacy_files()

CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
APRS_HOST = "euro.aprs2.net"
APRS_PORT = 14580
LOCAL_TZ = ZoneInfo("Europe/Berlin")
MILES_TO_KM = 1.60934
api_logger = logging.getLogger("api_logger")
if not api_logger.handlers:
    handler = RotatingFileHandler(
        os.path.join(DATA_DIR, "api.log"), maxBytes=1_000_000, backupCount=1
    )
    formatter = logging.Formatter("%(asctime)s %(message)s")
    handler.setFormatter(formatter)
    api_logger.addHandler(handler)
    api_logger.setLevel(logging.INFO)
    # Forward detailed library logs to the same file
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
    handler = RotatingFileHandler(
        os.path.join(DATA_DIR, "state.log"), maxBytes=100_000, backupCount=1
    )
    formatter = logging.Formatter("%(asctime)s %(message)s")
    formatter.converter = lambda ts: datetime.fromtimestamp(ts, LOCAL_TZ).timetuple()
    handler.setFormatter(formatter)
    state_logger.addHandler(handler)
    state_logger.setLevel(logging.INFO)

energy_logger = logging.getLogger("energy_logger")
if not energy_logger.handlers:
    handler = logging.FileHandler(
        os.path.join(DATA_DIR, "energy.log"), encoding="utf-8"
    )
    formatter = logging.Formatter("%(asctime)s %(message)s")
    formatter.converter = lambda ts: datetime.fromtimestamp(ts, LOCAL_TZ).timetuple()
    handler.setFormatter(formatter)
    energy_logger.addHandler(handler)
    energy_logger.setLevel(logging.INFO)

sms_logger = logging.getLogger("sms_logger")
if not sms_logger.handlers:
    handler = RotatingFileHandler(
        os.path.join(DATA_DIR, "sms.log"), maxBytes=100_000, backupCount=1
    )
    formatter = logging.Formatter("%(asctime)s %(message)s")
    formatter.converter = lambda ts: datetime.fromtimestamp(ts, LOCAL_TZ).timetuple()
    handler.setFormatter(formatter)
    sms_logger.addHandler(handler)
    sms_logger.setLevel(logging.INFO)


def _load_last_state(filename=os.path.join(DATA_DIR, "state.log")):
    """Load the last logged state for each vehicle from ``state.log``."""
    result = {}
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                idx = line.find("{")
                if idx != -1:
                    try:
                        entry = json.loads(line[idx:])
                        vid = entry.get("vehicle_id")
                        state = entry.get("state")
                        if vid is not None and state is not None:
                            result[vid] = state
                    except Exception:
                        pass
    except Exception:
        pass
    return result


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
    """Update ``api-liste.json`` while preserving existing keys."""
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                try:
                    current = json.load(f)
                except Exception:
                    current = {}
        else:
            current = {}

        # drop the dynamic drive path to keep the file small
        filtered = data.copy() if isinstance(data, dict) else data
        if isinstance(filtered, dict):
            filtered.pop("path", None)
        merged = _merge_data(current, filtered)

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def update_api_list(data, filename=os.path.join(DATA_DIR, "api-liste.txt")):
    """Update ``api-liste.txt`` with key/value pairs in API order."""
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        existing_lines = []
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if ": " in line:
                        k, v = line.split(": ", 1)
                    else:
                        k, v = line, ""
                    existing_lines.append((k, v))

        existing_map = {k: i for i, (k, _v) in enumerate(existing_lines)}
        kv = _collect_key_values(data)
        kv = [(k, v) for k, v in kv if not k.startswith("path[") and k != "path"]

        lines = existing_lines[:]
        for idx, (k, v) in enumerate(kv):
            value = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            if k in existing_map:
                pos = existing_map[k]
                lines[pos] = (k, value)
            else:
                # try to place the key after the nearest previous known key
                insert_pos = None
                for prev_idx in range(idx - 1, -1, -1):
                    prev_k = kv[prev_idx][0]
                    if prev_k in existing_map:
                        insert_pos = existing_map[prev_k] + 1
                        break
                if insert_pos is None:
                    # fallback: before the next known key
                    insert_pos = len(lines)
                    for next_k, _ in kv[idx + 1:]:
                        if next_k in existing_map:
                            insert_pos = existing_map[next_k]
                            break
                lines.insert(insert_pos, (k, value))
                existing_map = {key: i for i, (key, _v) in enumerate(lines)}

        content = "\n".join(f"{k}: {v}" for k, v in lines) + "\n"

        current = ""
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                current = f.read()

        if content != current:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
        _update_api_json(data)
    except Exception:
        pass


# Communication with the Tesla API is logged via ``log_api_data`` and the
# ``teslapy``/``urllib3`` loggers. Requests to this web application are not
# recorded in ``api.log``.


def log_api_data(endpoint, data):
    """Write API communication to the rotating log file."""
    try:
        api_logger.info(json.dumps({"endpoint": endpoint, "data": data}))
        update_api_list(data)
    except Exception:
        pass


STAT_FILE = os.path.join(DATA_DIR, "statistics.json")
PARKTIME_FILE = os.path.join(DATA_DIR, "parktime.json")
TAXI_DB = os.path.join(DATA_DIR, "taximeter.db")

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
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if isinstance(cfg, dict):
                return cfg
    except Exception:
        pass
    return {}


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


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


def check_auth(username, password):
    user = os.getenv("TESLA_EMAIL")
    pw = os.getenv("TESLA_PASSWORD")
    return username == user and password == pw


def authenticate():
    return Response(
        "Authentication required",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'},
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)

    return decorated


def _load_parktime():
    """Load the last park timestamp from ``parktime.json``."""
    try:
        with open(PARKTIME_FILE, "r", encoding="utf-8") as f:
            return int(json.load(f))
    except Exception:
        return None


def _save_parktime(ts):
    """Persist the park timestamp to ``parktime.json``."""
    try:
        with open(PARKTIME_FILE, "w", encoding="utf-8") as f:
            json.dump(int(ts), f)
    except Exception:
        pass


def _delete_parktime():
    """Remove the stored park timestamp if present."""
    try:
        os.remove(PARKTIME_FILE)
    except Exception:
        pass


park_start_ms = _load_parktime()
last_shift_state = None
trip_path = []
current_trip_file = None
current_trip_date = None
drive_pause_ms = None
latest_data = {}
address_cache = {}
subscribers = {}
threads = {}
_vehicle_list_cache = []
_vehicle_list_cache_ts = 0.0
_vehicle_list_lock = threading.Lock()
api_errors = []
api_errors_lock = threading.Lock()
state_lock = threading.Lock()
last_vehicle_state = _load_last_state()
occupant_present = False
_default_vehicle_id = None
_last_aprs_info = {}
_last_wx_info = {}


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
    """Append a GPS point to a trip history CSV."""
    if filename is None:
        filename = os.path.join(DATA_DIR, "trip_history.csv")
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "a", encoding="utf-8") as f:
            row = [
                ts,
                lat,
                lon,
                "" if speed is None else speed,
                "" if power is None else power,
                "" if heading is None else heading,
                "" if gear is None else gear,
            ]
            f.write(",".join(str(v) for v in row) + "\n")
    except Exception:
        pass


def track_drive_path(vehicle_data):
    """Maintain the current trip path and log points when driving."""
    global trip_path, current_trip_file, current_trip_date, drive_pause_ms
    drive = (
        vehicle_data.get("drive_state", {}) if isinstance(vehicle_data, dict) else {}
    )
    shift = drive.get("shift_state")
    lat = drive.get("latitude")
    lon = drive.get("longitude")
    ts = drive.get("timestamp") or drive.get("gps_as_of")
    speed = drive.get("speed")
    power = drive.get("power")
    heading = drive.get("heading")
    if ts and ts < 1e12:
        ts = int(ts * 1000)
    if shift in (None, "P"):
        if drive_pause_ms is None:
            drive_pause_ms = ts if ts is not None else int(time.time() * 1000)
            if lat is not None and lon is not None and current_trip_file:
                if ts is None:
                    ts = int(time.time() * 1000)
                _log_trip_point(
                    ts,
                    lat,
                    lon,
                    speed,
                    power,
                    heading,
                    shift,
                    current_trip_file,
                )
        else:
            if ts is None:
                ts = int(time.time() * 1000)
            if ts - drive_pause_ms > 600000:
                trip_path = []
                current_trip_file = None
                current_trip_date = None
        return
    if drive_pause_ms is not None:
        if ts is None:
            ts = int(time.time() * 1000)
        if ts - drive_pause_ms > 600000:
            trip_path = []
            current_trip_file = None
            current_trip_date = None
        drive_pause_ms = None
    if lat is not None and lon is not None:
        if ts is None:
            ts = int(time.time() * 1000)
        vid = vehicle_data.get("id_s") or vehicle_data.get("vehicle_id")
        date_str = datetime.fromtimestamp(ts / 1000, LOCAL_TZ).strftime("%Y%m%d")
        if current_trip_file is None or current_trip_date != date_str:
            current_trip_file = os.path.join(trip_dir(vid), f"trip_{date_str}.csv")
            current_trip_date = date_str
        point = [lat, lon]
        if not trip_path or trip_path[-1] != point:
            trip_path.append(point)
            if ts is not None:
                _log_trip_point(
                    ts,
                    lat,
                    lon,
                    speed,
                    power,
                    heading,
                    shift,
                    current_trip_file,
                )


def _log_api_error(exc):
    """Store API error messages with timestamp for later retrieval."""
    ts = time.time()
    msg = str(exc)
    with api_errors_lock:
        api_errors.append({"timestamp": ts, "message": msg})
        if len(api_errors) > 50:
            api_errors.pop(0)


def log_vehicle_state(vehicle_id, state):
    """Log vehicle state changes to ``state.log`` if changed."""
    try:
        with state_lock:
            if last_vehicle_state.get(vehicle_id) != state:
                last_vehicle_state[vehicle_id] = state
                state_logger.info(
                    json.dumps({"vehicle_id": vehicle_id, "state": state})
                )
    except Exception:
        pass


def _last_logged_energy(vehicle_id):
    """Return the last logged energy value for ``vehicle_id`` or ``None``."""
    try:
        with open(os.path.join(DATA_DIR, "energy.log"), "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            idx = line.find("{")
            if idx != -1:
                try:
                    entry = json.loads(line[idx:])
                    if entry.get("vehicle_id") == vehicle_id:
                        return float(entry.get("added_energy", 0.0))
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _log_energy(vehicle_id, amount):
    """Store the last added energy in ``energy.log`` using local time."""
    try:
        last = _last_logged_energy(vehicle_id)
        if last is None or abs(last - amount) > 0.001:
            entry = json.dumps({"vehicle_id": vehicle_id, "added_energy": amount})
            energy_logger.info(entry)
    except Exception:
        pass


def _log_sms(message, success):
    """Append SMS information to ``sms.log``."""
    try:
        sms_logger.info(json.dumps({"message": message, "success": success}))
    except Exception:
        pass


def _cache_file(vehicle_id):
    """Return filename for cached data of a vehicle."""
    return os.path.join(vehicle_dir(vehicle_id), "cache.json")


def _load_cached(vehicle_id):
    """Load cached vehicle data from disk."""
    try:
        with open(_cache_file(vehicle_id), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cached(vehicle_id, data):
    """Write vehicle data cache to disk."""
    try:
        with open(_cache_file(vehicle_id), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def _last_energy_file(vehicle_id):
    """Return filename for the last added energy of a vehicle."""
    return os.path.join(vehicle_dir(vehicle_id), "last_energy.txt")


def _load_last_energy(vehicle_id):
    """Load the last added energy value from disk."""
    try:
        with open(_last_energy_file(vehicle_id), "r", encoding="utf-8") as f:
            return float(f.read().strip())
    except Exception:
        return None


def _save_last_energy(vehicle_id, value):
    """Persist the last added energy value for a vehicle."""
    try:
        with open(_last_energy_file(vehicle_id), "w", encoding="utf-8") as f:
            f.write(str(value))
    except Exception:
        pass


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
    vid = str(vehicle_data.get("id_s") or vehicle_data.get("vehicle_id") or "default")
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
    """Return a sorted list of available trip CSV paths."""
    dirs = []
    if vehicle_id is None:
        try:
            for name in os.listdir(DATA_DIR):
                if not str(name).isdigit():
                    continue
                d = os.path.join(DATA_DIR, name, "trips")
                if os.path.isdir(d):
                    dirs.append(d)
        except Exception:
            pass
    else:
        dirs.append(trip_dir(vehicle_id))
    files = []
    for d in dirs:
        try:
            for f in os.listdir(d):
                if f.endswith(".csv"):
                    files.append(os.path.join(d, f))
        except Exception:
            continue
    files.sort()
    return files


def _get_trip_periods():
    """Return sorted lists of available weeks and months."""
    weeks = set()
    months = set()
    for path in _get_trip_files():
        fname = os.path.basename(path)
        date_str = fname.split("_")[-1].split(".")[0]
        try:
            day = datetime.strptime(date_str, "%Y%m%d").date()
        except Exception:
            continue
        iso_year, iso_week, _ = day.isocalendar()
        weeks.add(f"{iso_year}-W{iso_week:02d}")
        months.add(day.strftime("%Y-%m"))
    return sorted(weeks), sorted(months)


def _load_trip_period(prefix, key):
    """Load all trip points for the given week or month key."""
    points = []
    for path in _get_trip_files():
        fname = os.path.basename(path)
        date_str = fname.split("_")[-1].split(".")[0]
        try:
            day = datetime.strptime(date_str, "%Y%m%d").date()
        except Exception:
            continue
        iso_year, iso_week, _ = day.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        month_key = day.strftime("%Y-%m")
        if prefix == "week" and week_key != key:
            continue
        if prefix == "month" and month_key != key:
            continue
        points.extend(_load_trip(path))
    return points


def _load_trip(filename):
    """Load all coordinates with optional speed and power from a trip CSV."""
    points = []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 3:
                    continue
                ts, lat, lon = parts[:3]
                speed = parts[3] if len(parts) >= 4 and parts[3] else None
                power = parts[4] if len(parts) >= 5 and parts[4] else None
                heading = parts[5] if len(parts) >= 6 and parts[5] else None
                gear = parts[6] if len(parts) >= 7 and parts[6] else None
                try:
                    ts = int(float(ts)) if ts else None
                    lat = float(lat)
                    lon = float(lon)
                    speed = float(speed) if speed is not None else None
                    power = float(power) if power is not None else None
                    heading = float(heading) if heading is not None else None
                    gear = gear if gear is not None else None
                except Exception:
                    continue
                points.append([lat, lon, speed, power, ts, heading, gear])
    except Exception:
        pass
    return points


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
    """Return distance in km for a week or month selection."""
    dist = 0.0
    for path in _get_trip_files():
        fname = os.path.basename(path)
        date_str = fname.split("_")[-1].split(".")[0]
        try:
            day = datetime.strptime(date_str, "%Y%m%d").date()
        except Exception:
            continue
        iso_year, iso_week, _ = day.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        month_key = day.strftime("%Y-%m")
        if prefix == "week" and week_key != key:
            continue
        if prefix == "month" and month_key != key:
            continue
        dist += _trip_distance(path)
    return dist


def _parse_log_time(ts_str):
    """Return a timezone-aware datetime parsed from a log line."""
    for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts_str, fmt).replace(tzinfo=LOCAL_TZ)
        except Exception:
            continue
    return None


def _load_state_entries(filename=os.path.join(DATA_DIR, "state.log")):
    """Parse state log entries as (timestamp, state) tuples."""
    entries = []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                idx = line.find("{")
                if idx == -1:
                    continue
                ts_str = line[:idx].strip()
                ts_dt = _parse_log_time(ts_str)
                if ts_dt is None:
                    continue
                ts = ts_dt.timestamp()
                try:
                    data = json.loads(line[idx:])
                    state = data.get("state")
                    entries.append((ts, state))
                except Exception:
                    continue
    except Exception:
        pass
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


def _compute_energy_stats(filename=os.path.join(DATA_DIR, "energy.log")):
    """Return per-day added energy in kWh based on ``energy.log``."""
    energy = {}
    last_vals = {}
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                idx = line.find("{")
                if idx == -1:
                    continue
                ts_str = line[:idx].strip()
                ts_dt = _parse_log_time(ts_str)
                if ts_dt is None:
                    continue
                day = ts_dt.date().isoformat()
                try:
                    entry = json.loads(line[idx:])
                    vid = entry.get("vehicle_id")
                    val = float(entry.get("added_energy", 0.0))
                except Exception:
                    continue
                if vid is not None:
                    last = last_vals.get(vid)
                    if last is not None and abs(last - val) < 0.001:
                        continue
                    last_vals[vid] = val
                energy[day] = energy.get(day, 0.0) + val
    except Exception:
        pass
    return energy


def compute_statistics():
    """Compute daily statistics and save them to ``STAT_FILE``."""
    stats = _compute_state_stats(_load_state_entries())
    energy = _compute_energy_stats()
    for path in _get_trip_files():
        fname = os.path.basename(path)
        date_str = fname.split("_")[-1].split(".")[0]
        try:
            date_str = datetime.strptime(date_str, "%Y%m%d").date().isoformat()
        except Exception:
            pass
        km = _trip_distance(path)
        speed = _trip_max_speed(path)
        stats.setdefault(
            date_str, {"online": 0.0, "offline": 0.0, "asleep": 0.0}
        )
        stats[date_str]["km"] = km
        stats[date_str]["speed"] = speed
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
    try:
        os.makedirs(os.path.dirname(STAT_FILE), exist_ok=True)
        with open(STAT_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return stats


def compute_trip_summaries():
    """Return weekly and monthly distance summaries."""
    weekly = {}
    monthly = {}
    for path in _get_trip_files():
        fname = os.path.basename(path)
        date_str = fname.split("_")[-1].split(".")[0]
        try:
            day = datetime.strptime(date_str, "%Y%m%d").date()
        except Exception:
            continue
        km = _trip_distance(path)
        iso_year, iso_week, _ = day.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        weekly[week_key] = round(weekly.get(week_key, 0.0) + km, 2)
        month_key = day.strftime("%Y-%m")
        monthly[month_key] = round(monthly.get(month_key, 0.0) + km, 2)
    return weekly, monthly


def get_tesla():
    """Authenticate and return a Tesla object or None."""
    if teslapy is None:
        return None

    email = os.getenv("TESLA_EMAIL")
    password = os.getenv("TESLA_PASSWORD")
    access_token = os.getenv("TESLA_ACCESS_TOKEN")
    refresh_token = os.getenv("TESLA_REFRESH_TOKEN")

    tokens_provided = access_token and refresh_token
    if not tokens_provided and not (email and password):
        return None

    tesla = teslapy.Tesla(email, app_user_agent="Tesla-Dashboard")
    try:
        if tokens_provided:
            tesla.sso_token = {
                "access_token": access_token,
                "refresh_token": refresh_token,
            }
            tesla.refresh_token()
        elif access_token:
            tesla.refresh_token({"access_token": access_token})
        else:
            tesla.fetch_token(password=password)
    except Exception as exc:
        _log_api_error(exc)
        return None
    return tesla


def sanitize(data):
    """Remove personally identifiable fields from the vehicle data."""
    sensitive = {
        "id",
        "user_id",
        "vehicle_id",
        "vin",
        "tokens",
        "token",
        "access_token",
        "refresh_token",
        "backseat_token",
        "backseat_token_updated_at",
    }
    if isinstance(data, dict):
        for key in list(data.keys()):
            if key in sensitive or "token" in key:
                data.pop(key, None)
            else:
                sanitize(data[key])
    elif isinstance(data, list):
        for item in data:
            sanitize(item)
    return data


def _cached_vehicle_list(tesla, ttl=86400):
    """Return vehicle list with basic time-based caching."""
    global _vehicle_list_cache, _vehicle_list_cache_ts, _default_vehicle_id
    now = time.time()
    with _vehicle_list_lock:
        if not _vehicle_list_cache or now - _vehicle_list_cache_ts > ttl:
            try:
                _vehicle_list_cache = tesla.vehicle_list()
                _vehicle_list_cache_ts = now
                log_api_data(
                    "vehicle_list", sanitize([v.copy() for v in _vehicle_list_cache])
                )
                if _vehicle_list_cache and _default_vehicle_id is None:
                    _default_vehicle_id = str(_vehicle_list_cache[0]["id_s"])
            except Exception as exc:
                _log_api_error(exc)
                return []
        return _vehicle_list_cache


def default_vehicle_id():
    """Return the first vehicle ID or None if unavailable."""
    global _default_vehicle_id
    if _default_vehicle_id is not None:
        return _default_vehicle_id
    tesla = get_tesla()
    if tesla is None:
        return None
    vehicles = _cached_vehicle_list(tesla)
    if vehicles:
        _default_vehicle_id = str(vehicles[0]["id_s"])
        return _default_vehicle_id
    return None


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

    return state


def get_vehicle_state(vehicle_id=None):
    """Return the current vehicle state without waking the car."""
    vid = str(vehicle_id or _default_vehicle_id or "default")
    state = last_vehicle_state.get(vid)

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


def reverse_geocode(lat, lon, vehicle_id=None):
    """Return address ``Straße Hausnummer, PLZ Ort-Stadtteil`` for coordinates."""

    def _compose_label(street, house_number, postcode, city, district):
        parts = []

        street_part = " ".join(
            [p for p in [street, house_number] if p]
        ).strip()
        if street_part:
            parts.append(street_part)

        city_text = ""
        if city:
            city_text = city
            if district and district != city:
                city_text += f"-{district}"
        elif district:
            city_text = district

        second_part = " ".join([p for p in [postcode, city_text] if p]).strip()
        if second_part:
            parts.append(second_part)

        return ", ".join(parts) if parts else None

    headers = {"User-Agent": "TeslaDashboard/1.0"}
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lon,
            "format": "jsonv2",
            "addressdetails": 1,
        }
        r = requests.get(url, params=params, headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        addr = data.get("address", {})

        street = (
            addr.get("road")
            or addr.get("pedestrian")
            or addr.get("footway")
        )
        house_number = addr.get("house_number")
        city = addr.get("city") or addr.get("town") or addr.get("village")
        district = (
            addr.get("suburb")
            or addr.get("city_district")
            or addr.get("district")
        )
        postcode = addr.get("postcode")

        label = _compose_label(street, house_number, postcode, city, district)
        if label:
            return {"address": label, "raw": data}
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

            street = props.get("street")
            house_number = props.get("housenumber")
            postcode = props.get("postcode")
            city = props.get("city") or props.get("locality")
            district = props.get("district")

            label = _compose_label(street, house_number, postcode, city, district)
            if label:
                return {"address": label, "raw": data}
    except Exception as exc2:
        _log_api_error(exc2)
    return {}


def _fetch_data_once(vehicle_id="default"):
    """Return current data or cached values based on vehicle state."""
    if vehicle_id in (None, "default"):
        vid = _default_vehicle_id
        cache_id = "default"
    else:
        vid = vehicle_id
        cache_id = vehicle_id

    cached = _load_cached(cache_id)

    state = last_vehicle_state.get(vid or cache_id)
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
        if isinstance(cached, dict):
            last_val = cached.get("last_charge_energy_added")
        if last_val is None:
            last_val = _load_last_energy(cache_id)

        charge = data.get("charge_state", {})
        val = charge.get("charge_energy_added")
        saved_val = last_val

        if val is not None:
            if last_val is not None and val < last_val:
                # Finish previous session before counter resets
                if last_val > 0:
                    _log_energy(cache_id, last_val)
                _save_last_energy(cache_id, last_val)
                saved_val = last_val
            last_val = val

            end_state = charge.get("charging_state")
            if end_state in ("Complete", "Disconnected"):
                if val > 0:
                    _log_energy(cache_id, val)
                _save_last_energy(cache_id, val)
                saved_val = val
        elif charge.get("charging_state") in ("Complete", "Disconnected") and last_val is not None:
            if last_val > 0:
                _log_energy(cache_id, last_val)
            _save_last_energy(cache_id, last_val)
            saved_val = last_val

        if saved_val is not None:
            data["last_charge_energy_added"] = saved_val

        drive = data.get("drive_state", {})
        lat = drive.get("latitude")
        lon = drive.get("longitude")
        if lat is not None and lon is not None:
            entry = address_cache.get(cache_id)
            now = time.time()
            needs_update = (
                entry is None
                or now - entry.get("ts", 0) >= 5
                or abs(entry.get("lat") - lat) > 1e-4
                or abs(entry.get("lon") - lon) > 1e-4
            )
            if needs_update:
                result = reverse_geocode(lat, lon, vehicle_id)
                addr = result.get("address")
                if addr:
                    address_cache[cache_id] = {
                        "lat": lat,
                        "lon": lon,
                        "address": addr,
                        "ts": now,
                    }
            entry = address_cache.get(cache_id)
            if entry and entry.get("address"):
                data["location_address"] = entry["address"]
            else:
                data.pop("location_address", None)
        else:
            address_cache.pop(cache_id, None)
            data.pop("location_address", None)

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
        start = time.time()
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
            remaining = interval - (time.time() - start)
            if remaining > 0:
                time.sleep(remaining)
        else:
            remaining = idle_interval - (time.time() - start)
            _sleep_idle(max(0, remaining))


def _start_thread(vehicle_id):
    """Start background fetching thread for the given vehicle."""
    if vehicle_id in threads:
        return
    t = threading.Thread(target=_fetch_loop, args=(vehicle_id,), daemon=True)
    threads[vehicle_id] = t
    t.start()


# Taximeter instance using the existing fetch function and config-based tariff
taximeter = Taximeter(TAXI_DB, _fetch_data_once, get_taximeter_tariff)


@app.route("/")
def index():
    cfg = load_config()
    return render_template(
        "index.html",
        version=__version__,
        year=CURRENT_YEAR,
        config=cfg,
    )


@app.route("/map")
def map_only():
    """Display only the map without additional modules."""
    return render_template("map.html", version=__version__)


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
    )


@app.route("/daten")
def data_only():
    """Display live or cached vehicle data without extra UI."""
    _start_thread("default")
    data = latest_data.get("default")
    if data is None:
        data = _fetch_data_once("default")
    return render_template("data.html", data=data)


@app.route("/api/data")
def api_data():
    _start_thread("default")
    data = latest_data.get("default")
    if data is None:
        data = _fetch_data_once("default")
    return jsonify(data)


@app.route("/api/data/<vehicle_id>")
def api_data_vehicle(vehicle_id):
    _start_thread(vehicle_id)
    data = latest_data.get(vehicle_id)
    if data is None:
        data = _fetch_data_once(vehicle_id)
    return jsonify(data)


@app.route("/stream")
@app.route("/stream/<vehicle_id>")
def stream_vehicle(vehicle_id="default"):
    """Stream vehicle data to the client using Server-Sent Events."""
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
def api_vehicles():
    vehicles = get_vehicle_list()
    return jsonify(vehicles)


@app.route("/api/state")
@app.route("/api/state/<vehicle_id>")
def api_state(vehicle_id=None):
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
    vehicle_id = request.args.get("vehicle_id")
    result = reverse_geocode(lat, lon, vehicle_id)
    return jsonify(result)


@app.route("/api/config")
def api_config():
    """Return visibility configuration without sensitive fields."""
    cfg = load_config()
    if "phone_number" in cfg:
        cfg["phone_number"] = True
    if "infobip_api_key" in cfg:
        cfg["infobip_api_key"] = True
    cfg.pop("infobip_base_url", None)
    return jsonify(cfg)


@app.route("/api/announcement")
def api_announcement():
    """Return the current announcement text."""
    cfg = load_config()
    text = cfg.get("announcement", "")
    info = get_news_events_info()
    if info:
        text = text + ("\n" if text else "") + info
    return jsonify({"announcement": text})


@app.route("/api/alarm_state")
@app.route("/api/alarm_state/<vehicle_id>")
def api_alarm_state(vehicle_id=None):
    """Return the current alarm state."""
    vid = vehicle_id or "default"
    _start_thread(vid)
    data = latest_data.get(vid)
    if data is None:
        data = _fetch_data_once(vid)
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
        _log_sms(message, success)
        if success:
            return jsonify({"success": True})
        try:
            error = resp.json().get("requestError", {}).get("serviceException", {}).get("text")
        except Exception:
            error = resp.text
        return jsonify({"success": False, "error": error})
    except Exception as exc:
        _log_sms(message, False)
        return jsonify({"success": False, "error": str(exc)})


@app.route("/config", methods=["GET", "POST"])
@requires_auth
def config_page():
    cfg = load_config()
    if request.method == "POST":
        for item in CONFIG_ITEMS:
            cfg[item["id"]] = item["id"] in request.form
        callsign = request.form.get("aprs_callsign", "").strip()
        passcode = request.form.get("aprs_passcode", "").strip()
        wx_callsign = request.form.get("aprs_wx_callsign", "").strip()
        wx_enabled = "aprs_wx_enabled" in request.form
        aprs_comment = request.form.get("aprs_comment", "").strip()
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
    return render_template("config.html", items=CONFIG_ITEMS, config=cfg)


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
    return render_template("statistik.html", rows=rows, config=cfg)


@app.route("/api/errors")
def api_errors_route():
    """Return collected API errors as JSON."""
    with api_errors_lock:
        return jsonify(list(api_errors))


@app.route("/apiliste")
def api_list_file():
    """Return the aggregated API key list as plain text."""
    try:
        with open(os.path.join(DATA_DIR, "api-liste.txt"), "r", encoding="utf-8") as f:
            lines = [
                line
                for line in f
                if not line.startswith("path[") and not line.startswith("path:")
            ]
            content = "".join(lines)
    except Exception:
        content = ""
    return Response(content, mimetype="text/plain")


@app.route("/state")
def state_log_page():
    """Display the vehicle state log."""
    log_lines = []
    try:
        with open(os.path.join(DATA_DIR, "state.log"), "r", encoding="utf-8") as f:
            log_lines = f.readlines()
    except Exception:
        pass
    return render_template("state.html", log_lines=log_lines)


@app.route("/apilog")
def api_log_page():
    """Display the API log."""
    log_lines = []
    try:
        with open(os.path.join(DATA_DIR, "api.log"), "r", encoding="utf-8") as f:
            log_lines = f.readlines()
    except Exception:
        pass
    return render_template("apilog.html", log_lines=log_lines)


@app.route("/sms")
def sms_log_page():
    """Display the SMS log."""
    log_lines = []
    try:
        with open(os.path.join(DATA_DIR, "sms.log"), "r", encoding="utf-8") as f:
            log_lines = f.readlines()
    except Exception:
        pass
    return render_template("sms.html", log_lines=log_lines)


@app.route("/taxameter")
def taxameter_page():
    cfg = load_config()
    company = cfg.get("taxi_company", "Taxi Schauer")
    file_paths = [os.path.relpath(p, DATA_DIR) for p in _get_trip_files()]
    recent_files = file_paths[-10:]
    file_opts = []
    for f in recent_files:
        label = os.path.basename(f).replace("trip_", "").split(".")[0]
        try:
            label = datetime.strptime(label, "%Y%m%d").strftime("%Y-%m-%d")
        except Exception:
            pass
        file_opts.append({"value": f, "label": label})

    selected = request.args.get("file")
    if selected not in file_paths and file_opts:
        selected = file_opts[-1]["value"]

    trips = []
    if selected:
        segs = _split_trip_segments(os.path.join(DATA_DIR, selected))
        for idx, seg in enumerate(segs, 1):
            if seg["start"] is None:
                continue
            s_dt = datetime.fromtimestamp(seg["start"], LOCAL_TZ)
            e_dt = datetime.fromtimestamp(seg["end"], LOCAL_TZ)
            label = f"{s_dt.strftime('%Y-%m-%d %H:%M')} - {e_dt.strftime('%H:%M')}"
            value = f"file={selected}&segment={idx}"
            trips.append({"value": value, "label": label})

    vehicle_id = default_vehicle_id()
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
def api_taxameter_start():
    vid = request.form.get("vehicle_id") or default_vehicle_id()
    taximeter.vehicle_id = vid
    _start_thread(vid)
    taximeter.start()
    return jsonify(taximeter.status())


@app.route("/api/taxameter/pause", methods=["POST"])
def api_taxameter_pause():
    vid = request.form.get("vehicle_id")
    if vid:
        taximeter.vehicle_id = vid
    taximeter.pause()
    return jsonify(taximeter.status())


@app.route("/api/taxameter/stop", methods=["POST"])
def api_taxameter_stop():
    vid = request.form.get("vehicle_id")
    if vid:
        taximeter.vehicle_id = vid
    result = taximeter.stop()
    if result:
        company = get_taxi_company()
        slogan = get_taxi_slogan()
        text = format_receipt(company, result.get("breakdown", {}), result.get("distance", 0.0), slogan)
        rdir = receipt_dir()
        ride_id = result.get("ride_id")
        if ride_id is not None:
            txt_path = os.path.join(rdir, f"{ride_id}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            data_path = os.path.join(rdir, f"{ride_id}.json")
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "company": company,
                        "slogan": slogan,
                        "breakdown": result.get("breakdown", {}),
                        "distance": result.get("distance", 0.0),
                        "qr_code": f"/receipts/{ride_id}.png",
                    },
                    f,
                )
            url = url_for("taxameter_receipt", ride_id=ride_id, _external=True)
            img = qrcode.make(url)
            img_path = os.path.join(rdir, f"{ride_id}.png")
            img.save(img_path)
            result["qr_code"] = f"/receipts/{ride_id}.png"
            result["receipt_url"] = url
        result["company"] = company
        result["slogan"] = slogan
    return jsonify(result or {"active": False})


@app.route("/api/taxameter/reset", methods=["POST"])
def api_taxameter_reset():
    vid = request.form.get("vehicle_id")
    if vid:
        taximeter.vehicle_id = vid
    taximeter.reset()
    return jsonify({"active": False})


@app.route("/api/taxameter/status")
def api_taxameter_status():
    vid = request.args.get("vehicle_id")
    if vid:
        taximeter.vehicle_id = vid
    return jsonify(taximeter.status())


@app.route("/api/taxameter/trips")
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
    rdir = receipt_dir()
    json_path = os.path.join(rdir, f"{ride_id}.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return render_template("taxameter_receipt.html", **data)
        except Exception:
            pass
    path = os.path.join(rdir, f"{ride_id}.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        abort(404)
    return Response(text, mimetype="text/plain")


@app.route("/taxameter/trip_receipt")
def taxameter_trip_receipt():
    """Create a taximeter receipt for a recorded trip."""
    selected = request.args.get("file")
    segment_idx = request.args.get("segment")
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
        if ".." in selected or not selected.endswith(".csv"):
            abort(404)
        path = os.path.join(DATA_DIR, selected)
        if not os.path.exists(path):
            abort(404)
        if segment_idx is not None:
            try:
                idx = int(segment_idx)
            except ValueError:
                abort(404)
            segments = _split_trip_segments(path)
            if idx < 1 or idx > len(segments):
                abort(404)
            seg = segments[idx - 1]
            dist = seg["distance"]
            wait_time = seg["wait"]
        else:
            dist = _trip_distance(path)
            wait_time = 0.0
    tariff = get_taximeter_tariff()
    tm = Taximeter(TAXI_DB, lambda _vid: {}, get_taximeter_tariff)
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


@app.route("/receipts/<path:filename>")
def receipts_file(filename):
    return send_from_directory(receipt_dir(), filename)


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
    try:
        with open(os.path.join(DATA_DIR, "api.log"), "r", encoding="utf-8") as f:
            log_lines = f.readlines()[-50:]
    except Exception:
        pass

    return render_template(
        "debug.html", env_info=env_info, log_lines=log_lines, latest=latest_data
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8013, debug=True)
