import os
import json
import queue
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, jsonify, Response, request
import requests
from functools import wraps
from dotenv import load_dotenv
from version import get_version
from datetime import datetime, timedelta

try:
    import teslapy
except ImportError:
    teslapy = None

try:
    import aprslib
except ImportError:
    aprslib = None

load_dotenv()
app = Flask(__name__)
__version__ = get_version()
CURRENT_YEAR = datetime.now().year

# Ensure data paths are relative to this file regardless of the
# current working directory.  This allows running the application
# from any location while still finding the trip files and caches.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
APRS_HOST = "euro.aprs2.net"
APRS_PORT = 14580
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
    handler.setFormatter(formatter)
    state_logger.addHandler(handler)
    state_logger.setLevel(logging.INFO)


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
                    for next_k, _ in kv[idx + 1 :]:
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
# ``teslapy``/``urllib3`` loggers. Requests to this web application are no longer
# recorded in ``api.log``.


def log_api_data(endpoint, data):
    """Write API communication to the rotating log file."""
    try:
        api_logger.info(json.dumps({"endpoint": endpoint, "data": data}))
        update_api_list(data)
    except Exception:
        pass


TRIP_DIR = os.path.join(DATA_DIR, "trips")
STAT_FILE = os.path.join(DATA_DIR, "statistics.json")

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
    {"id": "charging-info", "desc": "Ladeinformationen"},
    {"id": "v2l-infos", "desc": "V2L-Hinweis"},
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


park_start_ms = None
last_shift_state = None
trip_path = []
current_trip_file = None
current_trip_date = None
drive_pause_ms = None
latest_data = {}
subscribers = {}
threads = {}
_vehicle_list_cache = []
_vehicle_list_cache_ts = 0.0
_vehicle_list_lock = threading.Lock()
_supercharger_cache = {}
_supercharger_cache_ts = {}
api_errors = []
api_errors_lock = threading.Lock()
state_lock = threading.Lock()
last_vehicle_state = _load_last_state()
occupant_present = False
_default_vehicle_id = None
_last_aprs_info = {}

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
    else:
        park_start_ms = None
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


def _log_trip_point(ts, lat, lon, speed=None, power=None, filename=None):
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
    if ts and ts < 1e12:
        ts = int(ts * 1000)
    if shift in (None, "P"):
        if drive_pause_ms is None:
            drive_pause_ms = ts if ts is not None else int(time.time() * 1000)
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
        date_str = time.strftime("%Y%m%d", time.localtime(ts / 1000))
        if current_trip_file is None or current_trip_date != date_str:
            current_trip_file = os.path.join(TRIP_DIR, f"trip_{date_str}.csv")
            current_trip_date = date_str
        point = [lat, lon]
        if not trip_path or trip_path[-1] != point:
            trip_path.append(point)
            if ts is not None:
                _log_trip_point(ts, lat, lon, speed, power, current_trip_file)


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


def _cache_file(vehicle_id):
    """Return filename for cached data of a vehicle."""
    name = vehicle_id if vehicle_id is not None else "default"
    return os.path.join(DATA_DIR, f"cache_{name}.json")


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
    name = vehicle_id if vehicle_id is not None else "default"
    return os.path.join(DATA_DIR, f"last_energy_{name}.txt")


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
    heading = drive.get("heading")
    speed = drive.get("speed")
    temp = climate.get("outside_temp")

    vid = str(vehicle_data.get("id_s") or vehicle_data.get("vehicle_id") or "default")
    now = time.time()
    last = _last_aprs_info.get(vid)
    changed = last is None
    if last is not None:
        if abs(lat - last.get("lat", 0)) > 1e-5 or abs(lon - last.get("lon", 0)) > 1e-5:
            changed = True
        if heading != last.get("heading"):
            changed = True
        if temp != last.get("temp"):
            changed = True
        if now - last.get("time", 0) >= 600:
            changed = True
    if not changed:
        return
    comment_parts = []
    if temp is not None:
        temp_f = int(round(temp * 9 / 5 + 32))
        comment_parts.append(f"/t{temp_f:03d}")
    if comment_cfg:
        comment_parts.append(comment_cfg)
    comment = "".join(comment_parts)
    try:
        aprs = aprslib.IS(callsign, passwd=str(passcode), host=APRS_HOST, port=APRS_PORT)
        aprs.connect()
        from aprslib.util import latitude_to_ddm, longitude_to_ddm

        lat_ddm = latitude_to_ddm(lat)
        lon_ddm = longitude_to_ddm(lon)
        course = int(round(heading or 0)) % 360
        spd_knots = int(round((speed or 0) / 1.852))
        body = f"!{lat_ddm}/{lon_ddm}_{course:03d}/{spd_knots:03d}"
        if comment:
            body += f"{comment}"
        packet = f"{callsign}>APRS:{body}"
        aprs.sendall(packet)
        
        aprs.close()
        _last_aprs_info[vid] = {
            "lat": lat,
            "lon": lon,
            "heading": heading,
            "temp": temp,
            "time": now,
        }
    except Exception as exc:
        _log_api_error(exc)


def _get_trip_files(directory=TRIP_DIR):
    """Return a list of available trip CSV files sorted chronologically."""
    try:
        os.makedirs(directory, exist_ok=True)
        files = [f for f in os.listdir(directory) if f.endswith(".csv")]
        files.sort()
        return files
    except Exception:
        return []


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
                try:
                    ts = int(float(ts)) if ts else None
                    lat = float(lat)
                    lon = float(lon)
                    speed = float(speed) if speed is not None else None
                    power = float(power) if power is not None else None
                except Exception:
                    continue
                points.append([lat, lon, speed, power, ts])
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
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f").timestamp()
                except Exception:
                    try:
                        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").timestamp()
                    except Exception:
                        continue
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
            day = datetime.fromtimestamp(t).date()
            next_day = datetime.combine(day + timedelta(days=1), datetime.min.time()).timestamp()
            segment_end = min(end, next_day)
            dur = segment_end - t
            d = stats.setdefault(day.isoformat(), {"online": 0.0, "offline": 0.0, "asleep": 0.0})
            key = state if state in d else "offline"
            d[key] += dur
            t = segment_end
    return stats


def compute_statistics():
    """Compute daily statistics and save them to ``STAT_FILE``."""
    stats = _compute_state_stats(_load_state_entries())
    for fname in _get_trip_files():
        date_str = fname.split("_")[-1].split(".")[0]
        try:
            date_str = datetime.strptime(date_str, "%Y%m%d").date().isoformat()
        except Exception:
            pass
        path = os.path.join(TRIP_DIR, fname)
        km = _trip_distance(path)
        stats.setdefault(date_str, {"online": 0.0, "offline": 0.0, "asleep": 0.0})
        stats[date_str]["km"] = km
    for day, val in stats.items():
        total = 24 * 3600
        for k in ("online", "offline", "asleep"):
            val[k] = round(val.get(k, 0.0) / total * 100, 2)
        val.setdefault("km", 0.0)
    try:
        os.makedirs(os.path.dirname(STAT_FILE), exist_ok=True)
        with open(STAT_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return stats


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
    if isinstance(data, dict):
        if "vin" in data:
            data.pop("vin", None)
        for value in data.values():
            sanitize(value)
    elif isinstance(data, list):
        for item in data:
            sanitize(item)
    return data


def _cached_vehicle_list(tesla, ttl=300):
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


def get_vehicle_state(vehicle_id=None):
    """Return the current vehicle state without waking the car."""
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
        vehicle.get_vehicle_summary()
        state = vehicle.get("state") or vehicle["state"]
        log_vehicle_state(vehicle["id_s"], state)
        log_api_data("get_vehicle_summary", {"state": state})
    except Exception as exc:
        _log_api_error(exc)
        log_vehicle_state(vehicle["id_s"], "offline")
        return {"error": "Vehicle unavailable", "state": "offline"}

    return {"state": state}


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
            vehicle.get_vehicle_summary()
            state = vehicle.get("state") or vehicle["state"]
            log_vehicle_state(vehicle["id_s"], state)
            log_api_data("get_vehicle_summary", {"state": state})
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


def get_superchargers(vehicle_id=None, ttl=60):
    """Return nearby Superchargers for the given vehicle."""
    tesla = get_tesla()
    if tesla is None:
        return []

    vehicles = _cached_vehicle_list(tesla)
    if not vehicles:
        return []

    vehicle = None
    if vehicle_id is not None:
        vehicle = next((v for v in vehicles if str(v["id_s"]) == str(vehicle_id)), None)
    if vehicle is None:
        vehicle = vehicles[0]

    vid = vehicle["id_s"]
    now = time.time()
    if vid in _supercharger_cache and now - _supercharger_cache_ts.get(vid, 0) < ttl:
        return _supercharger_cache[vid]

    state = last_vehicle_state.get(vid)
    if state in (None, "online") or occupant_present:
        state_info = get_vehicle_state(vid)
        state = state_info.get("state") if isinstance(state_info, dict) else state
    if state != "online" and not occupant_present:
        return _supercharger_cache.get(vid, [])

    try:
        sites = vehicle.get_nearby_charging_sites()
        log_api_data("get_nearby_charging_sites", sanitize(sites))
        chargers = []
        for s in sites.get("superchargers", []):
            dist = s.get("distance_miles")
            if dist is not None:
                dist = round(dist * 1.60934, 1)
            loc = s.get("location") or {}
            chargers.append(
                {
                    "name": s.get("name"),
                    "distance_km": dist,
                    "available_stalls": s.get("available_stalls"),
                    "total_stalls": s.get("total_stalls"),
                    "location": {"lat": loc.get("lat"), "long": loc.get("long")},
                }
            )
        _supercharger_cache[vid] = chargers
        _supercharger_cache_ts[vid] = now
        return chargers
    except Exception as exc:
        _log_api_error(exc)
        return _supercharger_cache.get(vid, [])


def reverse_geocode(lat, lon, vehicle_id=None):
    """Return address information for given coordinates using OpenStreetMap."""

    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"lat": lat, "lon": lon, "format": "jsonv2"}
        headers = {"User-Agent": "TeslaDashboard/1.0"}
        r = requests.get(url, params=params, headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        return {"address": data.get("display_name"), "raw": data}
    except Exception as exc:
        _log_api_error(exc)
        return {}


def _fetch_data_once(vehicle_id="default"):
    """Return current data or cached values based on vehicle state."""
    global _default_vehicle_id
    if vehicle_id in (None, "default"):
        vid = _default_vehicle_id
        cache_id = "default"
    else:
        vid = vehicle_id
        cache_id = vehicle_id

    cached = _load_cached(cache_id)

    state = last_vehicle_state.get(vid or cache_id)
    # Always query the vehicle state so transitions from "offline" are detected
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
        charge = data.get("charge_state", {})
        if (
            charge.get("charging_state") == "Charging"
            and charge.get("charge_energy_added") is not None
        ):
            last_val = charge.get("charge_energy_added")
            _save_last_energy(cache_id, last_val)
        elif last_val is None:
            last_val = _load_last_energy(cache_id)
        if last_val is not None:
            data["last_charge_energy_added"] = last_val
        try:
            data["superchargers"] = get_superchargers(vid)
        except Exception:
            pass

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
    return data


def _fetch_loop(vehicle_id, interval=3):
    """Continuously fetch data for a vehicle and notify subscribers."""
    while True:
        data = _fetch_data_once(vehicle_id)
        if isinstance(data, dict) and data.get("_live"):
            try:
                send_aprs(data)
            except Exception:
                pass
        for q in subscribers.get(vehicle_id, []):
            q.put(data)
        time.sleep(interval)


def _start_thread(vehicle_id):
    """Start background fetching thread for the given vehicle."""
    if vehicle_id in threads:
        return
    t = threading.Thread(target=_fetch_loop, args=(vehicle_id,), daemon=True)
    threads[vehicle_id] = t
    t.start()


@app.route("/")
def index():
    return render_template("index.html", version=__version__, year=CURRENT_YEAR)


@app.route("/map")
def map_only():
    """Display only the map without additional modules."""
    return render_template("map.html", version=__version__)


@app.route("/history")
def trip_history():
    """Show recorded trips and allow selecting a trip to display."""
    files = _get_trip_files()
    selected = request.args.get("file")
    if selected not in files and files:
        selected = files[-1]
    path = _load_trip(os.path.join(TRIP_DIR, selected)) if selected else []
    heading = 0.0
    if len(path) >= 2:
        heading = _bearing(path[-2][:2], path[-1][:2])
    return render_template(
        "history.html", path=path, heading=heading, files=files, selected=selected
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
                data = q.get()
                yield f"data: {json.dumps(data)}\n\n"
        finally:
            subscribers.get(vehicle_id, []).remove(q)

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


@app.route("/api/superchargers")
@app.route("/api/superchargers/<vehicle_id>")
def api_superchargers(vehicle_id=None):
    """Return nearby Superchargers as JSON."""
    chargers = get_superchargers(vehicle_id)
    return jsonify(chargers)


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
    """Return visibility configuration as JSON."""
    return jsonify(load_config())


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


@app.route("/config", methods=["GET", "POST"])
@requires_auth
def config_page():
    cfg = load_config()
    if request.method == "POST":
        for item in CONFIG_ITEMS:
            cfg[item["id"]] = item["id"] in request.form
        callsign = request.form.get("aprs_callsign", "").strip()
        passcode = request.form.get("aprs_passcode", "").strip()
        aprs_comment = request.form.get("aprs_comment", "").strip()
        if callsign:
            cfg["aprs_callsign"] = callsign
        elif "aprs_callsign" in cfg:
            cfg.pop("aprs_callsign")
        if passcode:
            cfg["aprs_passcode"] = passcode
        elif "aprs_passcode" in cfg:
            cfg.pop("aprs_passcode")
        if aprs_comment:
            cfg["aprs_comment"] = aprs_comment
        elif "aprs_comment" in cfg:
            cfg.pop("aprs_comment")
        save_config(cfg)
    return render_template("config.html", items=CONFIG_ITEMS, config=cfg)


@app.route("/error")
def error_page():
    """Display collected API errors."""
    with api_errors_lock:
        errors = list(api_errors)
    for e in errors:
        try:
            e["time_str"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(e["timestamp"])
            )
        except Exception:
            e["time_str"] = str(e["timestamp"])
    return render_template("errors.html", errors=errors)


@app.route("/statistik")
def statistics_page():
    """Display daily statistics of vehicle state and distance."""
    stats = compute_statistics()
    rows = []
    for day in sorted(stats.keys()):
        entry = stats[day]
        rows.append(
            {
                "date": day,
                "online": entry.get("online", 0.0),
                "offline": entry.get("offline", 0.0),
                "asleep": entry.get("asleep", 0.0),
                "km": round(entry.get("km", 0.0), 2),
            }
        )
    return render_template("statistik.html", rows=rows)


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
