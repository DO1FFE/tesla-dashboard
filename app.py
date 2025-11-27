import eventlet
eventlet.monkey_patch()

import os
import json
import queue
from collections import deque
import threading
import time
import logging
import glob
import socket
import uuid
import secrets
import sqlite3
import argparse
from urllib.parse import urlparse
from pathlib import Path
from logging.handlers import RotatingFileHandler
from io import UnsupportedOperation
from flask import (
    Flask,
    render_template,
    jsonify,
    Response,
    request,
    send_from_directory,
    abort,
    url_for,
    redirect,
    g,
    make_response,
)
from flask_wtf import CSRFProtect
from taximeter import Taximeter
import requests
from functools import wraps
from dotenv import load_dotenv
from version import get_version
import qrcode
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from importlib import metadata
from flask_socketio import SocketIO, emit
from flask_compress import Compress

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


def _secret_key():
    """Return the configured secret key or generate a temporary one."""

    secret = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY")
    if secret:
        return secret
    generated = secrets.token_hex(32)
    logging.warning(
        "FLASK_SECRET_KEY not set; generated temporary SECRET_KEY for CSRF protection"
    )
    return generated


load_dotenv()
app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600
app.config["SECRET_KEY"] = _secret_key()
csrf = CSRFProtect(app)
Compress(app)
socketio = SocketIO(app, async_mode="eventlet")
__version__ = get_version()
CURRENT_YEAR = datetime.now(ZoneInfo("Europe/Berlin")).year
RECEIPT_TIME_FORMAT = "%d.%m.%Y %H:%M"
GA_TRACKING_ID = os.getenv("GA_TRACKING_ID")
TESLA_REQUEST_TIMEOUT = float(os.getenv("TESLA_REQUEST_TIMEOUT", "5"))
CLIENT_TIMEOUT = int(os.getenv("CLIENT_TIMEOUT", "60"))
SECRET_PLACEHOLDER = "********"

"""Utilities for serving a compatible Socket.IO client script.

``ensure_socketio_client`` downloads the script into ``static/js`` if it is not
already present.  ``_preload_socketio_client`` is invoked on startup to ensure
the file is available before the first request.  The helper functions are
defined before the preload call so that the module can import cleanly.
"""

# Ensure required Socket.IO client libraries are available in ``static/js``.
SOCKETIO_CLIENT_MAP = {5: "4.7.2", 4: "4.5.4"}
SOCKETIO_JS_DIR = Path(__file__).parent / "static" / "js"
SOCKETIO_DOWNLOAD_ATTEMPTS = set()


def ensure_socketio_client(version: str) -> None:
    """Download missing Socket.IO client script into ``static/js``.

    The download is attempted only once per version to avoid blocking
    repeated requests when the CDN is unreachable.
    """

    if version in SOCKETIO_DOWNLOAD_ATTEMPTS:
        return
    SOCKETIO_DOWNLOAD_ATTEMPTS.add(version)

    SOCKETIO_JS_DIR.mkdir(parents=True, exist_ok=True)
    dest = SOCKETIO_JS_DIR / f"socket.io-{version}.min.js"
    if dest.exists():
        return

    url = f"https://cdn.socket.io/{version}/socket.io.min.js"
    try:
        resp = requests.get(url, timeout=2)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    except Exception as exc:
        logging.warning("Failed to download Socket.IO %s: %s", version, exc)


def _socketio_client_version() -> str:
    """Return the Socket.IO client version matching ``python-socketio``."""
    try:
        major = int(metadata.version("python-socketio").split(".", 1)[0])
    except Exception:
        major = max(SOCKETIO_CLIENT_MAP)
    return SOCKETIO_CLIENT_MAP.get(major, next(iter(SOCKETIO_CLIENT_MAP.values())))


def _preload_socketio_client():
    """Fetch the appropriate Socket.IO client script on startup."""
    version = _socketio_client_version()
    ensure_socketio_client(version)


_preload_socketio_client()


def socketio_client_script() -> str:
    """Return URL to a compatible Socket.IO client script."""
    version = _socketio_client_version()
    ensure_socketio_client(version)
    dest = SOCKETIO_JS_DIR / f"socket.io-{version}.min.js"
    if dest.exists():
        return url_for("static", filename=f"js/socket.io-{version}.min.js")
    return f"https://cdn.socket.io/{version}/socket.io.min.js"


@app.context_processor
def inject_ga_id():
    """Add Google Analytics tracking ID to all templates."""
    return {"ga_id": GA_TRACKING_ID}


@app.before_request
def assign_client_id():
    """Ensure every client has a persistent identifier."""
    cid = request.cookies.get("client_id")
    if cid is None:
        cid = uuid.uuid4().hex
        g.client_id = cid
        g.set_client_id_cookie = True
    else:
        g.client_id = cid


@app.before_request
def _ensure_background_started():
    if not (_aggregation_thread and _aggregation_thread.is_alive()):
        _start_statistics_aggregation()


def _ensure_background_started_once():
    _start_statistics_aggregation()


if hasattr(app, "before_first_request"):
    app.before_first_request(_ensure_background_started_once)
else:
    app.before_request(_ensure_background_started_once)


@app.after_request
def persist_client_id(resp):
    if getattr(g, "set_client_id_cookie", False):
        resp.set_cookie("client_id", g.client_id, max_age=315360000)
    return resp


# Track connected clients with their connection metadata
active_clients = {}
current_speaker_id = None
ptt_timer = None
audio_buffer = bytearray()


def _client_ip():
    """Return the originating client IP taking proxy headers into account."""

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        for part in forwarded.split(","):
            candidate = part.strip()
            if candidate:
                return candidate
    return request.remote_addr or ""


LOOKUP_CACHE_TTL = int(os.getenv("LOOKUP_CACHE_TTL", "300"))
_hostname_cache = {}
_ipinfo_cache = {}
_lookup_queue = queue.Queue()
_queued_ips = set()
_lookup_lock = threading.Lock()


def _perform_hostname_lookup(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def _ipinfo_data(ip):
    if not ip:
        return {}
    try:
        resp = requests.get(f"https://ipinfo.io/{ip}/json", timeout=1)
        if resp.ok:
            return resp.json()
    except Exception:
        pass
    return {}


def _refresh_ip_metadata(ip):
    hostname = _perform_hostname_lookup(ip)
    ipinfo = _ipinfo_data(ip)
    now = time.time()
    _hostname_cache[ip] = {"value": hostname, "ts": now}
    _ipinfo_cache[ip] = {"value": ipinfo, "ts": now}


def _lookup_worker():
    while True:
        try:
            ip = _lookup_queue.get(timeout=1)
        except queue.Empty:
            continue
        try:
            _refresh_ip_metadata(ip)
        finally:
            with _lookup_lock:
                _queued_ips.discard(ip)
            _lookup_queue.task_done()


def _enqueue_lookup(ip):
    if not ip:
        return
    with _lookup_lock:
        if ip in _queued_ips:
            return
        _queued_ips.add(ip)
    _lookup_queue.put(ip)


def _cached_hostname(ip):
    now = time.time()
    entry = _hostname_cache.get(ip)
    if entry and now - entry.get("ts", 0) <= LOOKUP_CACHE_TTL:
        return entry.get("value", "")
    _enqueue_lookup(ip)
    return entry.get("value", "") if entry else ""


def _cached_ipinfo(ip):
    now = time.time()
    entry = _ipinfo_cache.get(ip)
    if entry and now - entry.get("ts", 0) <= LOOKUP_CACHE_TTL:
        return entry.get("value", {})
    _enqueue_lookup(ip)
    return entry.get("value", {}) if entry else {}


lookup_thread = threading.Thread(
    target=_lookup_worker, name="client_lookup_worker", daemon=True
)
lookup_thread.start()


def lookup_location(ip):
    """Return city/country information for ``ip`` using cached ipinfo.io data."""

    data = _cached_ipinfo(ip)
    city = data.get("city")
    country = data.get("country")
    if city and country:
        return f"{city}, {country}"
    return city or country or ""


def lookup_provider(ip):
    """Return provider/organisation information for ``ip``."""

    data = _cached_ipinfo(ip)
    return data.get("org", "")


def parse_user_agent(ua):
    """Extract simple browser and OS information from user agent string."""
    browser = ""
    os_name = ""
    if "Firefox" in ua:
        browser = "Firefox"
    elif "Chrome" in ua and "Chromium" not in ua:
        browser = "Chrome"
    elif "Chromium" in ua:
        browser = "Chromium"
    elif "Safari" in ua and "Chrome" not in ua:
        browser = "Safari"
    elif "MSIE" in ua or "Trident" in ua:
        browser = "Internet Explorer"

    if "Windows" in ua:
        os_name = "Windows"
    elif "Android" in ua:
        os_name = "Android"
    elif "iPhone" in ua or "iPad" in ua or "iOS" in ua:
        os_name = "iOS"
    elif "Mac OS X" in ua:
        os_name = "macOS"
    elif "Linux" in ua:
        os_name = "Linux"

    return browser, os_name


@app.before_request
def _track_client():
    """Collect information about the connecting client."""
    ip = _client_ip()
    ua = request.headers.get("User-Agent", "")
    hostname = _cached_hostname(ip)
    now = time.time()
    info = active_clients.get(ip)
    if info is None:
        browser, os_name = parse_user_agent(ua)
        info = {
            "ip": ip,
            "hostname": hostname,
            "location": lookup_location(ip) if ip else "",
            "provider": lookup_provider(ip) if ip else "",
            "user_agent": ua,
            "browser": browser,
            "os": os_name,
            "first_seen": now,
            "last_seen": now,
            "connections": 0,
        }
        active_clients[ip] = info
    else:
        info["last_seen"] = now
        info["user_agent"] = ua
        info["hostname"] = hostname
        info["browser"], info["os"] = parse_user_agent(ua)
        if ip and not info.get("location"):
            info["location"] = lookup_location(ip)
        if ip and not info.get("provider"):
            info["provider"] = lookup_provider(ip)
    if not request.path.startswith("/static/") and not request.path.startswith("/images/"):
        page_path = request.path
        if page_path.startswith("/api"):
            ref = request.headers.get("Referer")
            if ref:
                try:
                    page_path = urlparse(ref).path
                except Exception:
                    page_path = "/"
            else:
                page_path = "/"
        if page_path:
            page = page_path.strip("/")
            if not page:
                page = "index.html"
            else:
                segment = page.split("/")[-1]
                if "." not in segment:
                    page = f"{segment}.html"
                else:
                    page = segment
            pages = info.setdefault("pages", [])
            if page not in pages:
                pages.append(page)

    if request.path.startswith("/stream"):
        info["connections"] = info.get("connections", 0) + 1


# Block clients based on configured IP addresses
@app.before_request
def block_ip_clients():
    cfg = load_config()
    raw = cfg.get("blocked_ips", "")
    if isinstance(raw, str):
        blocked = [ip.strip() for ip in raw.split(",") if ip.strip()]
    elif isinstance(raw, list):
        blocked = [ip.strip() for ip in raw if isinstance(ip, str) and ip.strip()]
    else:
        blocked = []
    ip = _client_ip()
    if (
        blocked
        and ip in blocked
        and request.path != "/blocked"
        and not request.path.startswith("/images/")
    ):
        # Replace recorded pages so the client shows as blocked
        info = active_clients.setdefault(ip, {"ip": ip})
        pages = info.setdefault("pages", [])
        if "index.html" in pages:
            pages.remove("index.html")
        if "blocked.html" not in pages:
            pages.append("blocked.html")
        return render_template("blocked.html"), 403


# Ensure data paths are relative to this file regardless of the
# current working directory.  This allows running the application
# from any location while still finding the trip files and caches.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _vehicle_key(vehicle_id):
    return str(vehicle_id) if vehicle_id not in (None, "") else "default"


def vehicle_dir(vehicle_id):
    """Return directory for a specific vehicle."""
    dir_name = _vehicle_key(vehicle_id)
    path = os.path.join(DATA_DIR, dir_name)
    os.makedirs(path, exist_ok=True)
    return path


def trip_dir(vehicle_id):
    """Return directory holding trip CSV files for ``vehicle_id``."""
    path = os.path.join(vehicle_dir(vehicle_id), "trips")
    os.makedirs(path, exist_ok=True)
    return path


def config_file(vehicle_id=None):
    return os.path.join(vehicle_dir(vehicle_id), "config.json")


def log_file(vehicle_id, name):
    return os.path.join(vehicle_dir(vehicle_id), name)


def resolve_log_path(vehicle_id, name):
    path = log_file(vehicle_id, name)
    legacy = os.path.join(DATA_DIR, name)
    if not os.path.exists(path) and os.path.exists(legacy):
        return legacy
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
            if fname == "config.json":
                src = os.path.join(DATA_DIR, fname)
                dst = config_file(None)
                if os.path.exists(src) and not os.path.exists(dst):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
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
        for log_name in ("api.log", "state.log", "energy.log", "sms.log"):
            src = os.path.join(DATA_DIR, log_name)
            dst = log_file(None, log_name)
            if os.path.exists(src) and not os.path.exists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.rename(src, dst)
            rotated = glob.glob(f"{src}.*")
            for path in rotated:
                target = os.path.join(vehicle_dir(None), os.path.basename(path))
                if not os.path.exists(target):
                    os.rename(path, target)
    except Exception:
        pass


migrate_legacy_files()

CONFIG_FILE = config_file(None)
APRS_HOST = "euro.aprs2.net"
APRS_PORT = 14580
LOCAL_TZ = ZoneInfo("Europe/Berlin")
MILES_TO_KM = 1.60934
PARK_UI_LOG = "park-ui.log"
PARKING_CHARGING_STATES = {"Charging", "Starting", "Stopped", "NoPower"}
_active_parking_sessions = {}
_last_parking_samples = {}


def _merge_state_logs(filename=None, vehicle_id=None):
    """Combine rotated state log files into a single file."""

    if filename is None:
        filename = log_file(vehicle_id, "state.log")

    parts = sorted(
        glob.glob(f"{filename}.*"),
        key=lambda p: int(p.rsplit(".", 1)[1]),
        reverse=True,
    )
    if not parts:
        return
    base_content = ""
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            base_content = f.read()
    with open(filename, "w", encoding="utf-8") as dest:
        for part in parts:
            with open(part, "r", encoding="utf-8") as src:
                dest.write(src.read())
            os.remove(part)
        dest.write(base_content)


def _get_api_logger(vehicle_id=None):
    name = f"api_logger_{_vehicle_key(vehicle_id)}"
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_file(vehicle_id, "api.log"), maxBytes=1_000_000, backupCount=1
        )
        formatter = logging.Formatter("%(asctime)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        for lib_name in ("teslapy", "urllib3"):
            lib_logger = logging.getLogger(lib_name)
            if handler not in lib_logger.handlers:
                lib_logger.addHandler(handler)
            lib_logger.setLevel(logging.DEBUG)
        try:
            import http.client as http_client

            http_client.HTTPConnection.debuglevel = 1
        except Exception:
            pass
    base_logger = globals().get("api_logger")
    if base_logger and base_logger is not logger:
        for handler in base_logger.handlers:
            if handler not in logger.handlers:
                logger.addHandler(handler)
    return logger


def _get_state_logger(vehicle_id=None):
    name = f"state_logger_{_vehicle_key(vehicle_id)}"
    logger = logging.getLogger(name)
    if not logger.handlers:
        path = log_file(vehicle_id, "state.log")
        _merge_state_logs(filename=path)
        handler = logging.FileHandler(path, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s %(message)s")
        formatter.converter = (
            lambda ts: datetime.fromtimestamp(ts, LOCAL_TZ).timetuple()
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    base_logger = globals().get("state_logger")
    if base_logger and base_logger is not logger:
        for handler in base_logger.handlers:
            if handler not in logger.handlers:
                logger.addHandler(handler)
    return logger


def _get_energy_logger(vehicle_id=None):
    name = f"energy_logger_{_vehicle_key(vehicle_id)}"
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.FileHandler(
            log_file(vehicle_id, "energy.log"), mode="a+", encoding="utf-8"
        )
        formatter = logging.Formatter("%(asctime)s %(message)s")
        formatter.converter = (
            lambda ts: datetime.fromtimestamp(ts, LOCAL_TZ).timetuple()
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    base_logger = globals().get("energy_logger")
    if base_logger and base_logger is not logger:
        for handler in base_logger.handlers:
            if handler not in logger.handlers:
                logger.addHandler(handler)
    return logger


def _get_sms_logger(vehicle_id=None):
    name = f"sms_logger_{_vehicle_key(vehicle_id)}"
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_file(vehicle_id, "sms.log"), maxBytes=100_000, backupCount=1
        )
        formatter = logging.Formatter("%(asctime)s %(message)s")
        formatter.converter = (
            lambda ts: datetime.fromtimestamp(ts, LOCAL_TZ).timetuple()
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    base_logger = globals().get("sms_logger")
    if base_logger and base_logger is not logger:
        for handler in base_logger.handlers:
            if handler not in logger.handlers:
                logger.addHandler(handler)
    return logger


# Default loggers for backward compatibility
api_logger = _get_api_logger(None)
state_logger = _get_state_logger(None)
energy_logger = _get_energy_logger(None)
sms_logger = _get_sms_logger(None)


def _load_last_state(vehicle_id=None, filename=None):
    """Load the last logged state for each vehicle from ``state.log``."""

    if filename is None:
        filename = resolve_log_path(vehicle_id, "state.log")

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


# Tools to build an aggregated list of API values ----------------------------

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


def log_api_data(endpoint, data, vehicle_id=None):
    """Write API communication to the rotating log file."""

    try:
        logger = _get_api_logger(vehicle_id)
        logger.info(json.dumps({"endpoint": endpoint, "data": data}))
        update_api_list(data)
    except Exception:
        pass


STAT_FILE = os.path.join(DATA_DIR, "statistics.json")
PARKTIME_FILE = os.path.join(DATA_DIR, "parktime.json")
TAXI_DB = os.path.join(DATA_DIR, "taximeter.db")
STATISTICS_DB = os.getenv("STATISTICS_DB_PATH") or os.path.join(DATA_DIR, "statistics.db")
AGGREGATION_INTERVAL = float(os.getenv("AGGREGATION_INTERVAL_SECONDS", "300"))
DISABLE_STATISTICS_AGGREGATION = os.getenv("DISABLE_STATISTICS_AGGREGATION") == "1"
FORCE_STATISTICS_REBUILD = os.getenv("FORCE_STATISTICS_REBUILD") == "1"


def _parse_cli_arguments():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--aggregation-interval",
        type=float,
        help="Seconds between statistics aggregation runs (default: env AGGREGATION_INTERVAL_SECONDS)",
    )
    parser.add_argument(
        "--rebuild-statistics",
        action="store_true",
        help="Force a full rebuild of statistics from logs and trip CSVs",
    )
    args, _unknown = parser.parse_known_args()
    if args.aggregation_interval:
        global AGGREGATION_INTERVAL
        AGGREGATION_INTERVAL = max(1.0, args.aggregation_interval)
    if args.rebuild_statistics:
        global FORCE_STATISTICS_REBUILD
        FORCE_STATISTICS_REBUILD = True

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
    {"id": "ptt-controls", "desc": "Push-to-Talk"},
]


_config_cache = {}
_config_mtime = {}


def invalidate_config_cache(vehicle_id=None):
    """Force the next load to read the config from disk."""

    global _config_cache, _config_mtime
    if vehicle_id is None:
        _config_cache = {}
        _config_mtime = {}
    else:
        key = _vehicle_key(vehicle_id)
        _config_cache.pop(key, None)
        _config_mtime.pop(key, None)


def _read_config_from_disk(vehicle_id=None):
    try:
        with open(config_file(vehicle_id), "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if isinstance(cfg, dict):
                return cfg
    except Exception:
        pass
    return {}


def load_config(vehicle_id=None):
    global _config_cache, _config_mtime

    key = _vehicle_key(vehicle_id)

    try:
        mtime = os.path.getmtime(config_file(vehicle_id))
    except OSError:
        mtime = None

    cached = _config_cache.get(key)
    if cached is None or mtime != _config_mtime.get(key):
        _config_cache[key] = _read_config_from_disk(vehicle_id)
        _config_mtime[key] = mtime

    return dict(_config_cache.get(key, {}))


def save_config(cfg, vehicle_id=None):
    global _config_cache, _config_mtime

    key = _vehicle_key(vehicle_id)

    try:
        with open(config_file(vehicle_id), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        _config_cache[key] = dict(cfg)
        try:
            _config_mtime[key] = os.path.getmtime(config_file(vehicle_id))
        except OSError:
            _config_mtime[key] = None
    except Exception:
        pass


def is_ptt_enabled():
    """Return whether push-to-talk controls are enabled in the config."""

    cfg = load_config()
    return bool(cfg.get("ptt-controls", True))


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


def format_receipt(company, breakdown, distance=0.0, slogan="", printed_at=None):
    if printed_at is None:
        printed_at = datetime.now(LOCAL_TZ).strftime(RECEIPT_TIME_FORMAT)
    lines = []
    if company:
        lines.append(company)
        if slogan:
            lines.append(slogan)
        lines.append("")
    if printed_at:
        lines.append(f"Datum: {printed_at}")
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
        log_api_data(
            "NOTIFICATIONS_GET_NEWS_AND_EVENTS_TOGGLES",
            data,
            vehicle_id=_default_vehicle_id,
        )
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
_statistics_cache_lock = threading.Lock()
_statistics_cache = {"signature": None, "data": None}
_aggregation_lock = threading.Lock()
_aggregation_initialized = False
_aggregation_thread = None


def _force_statistics_rebuild_on_start():
    """Ensure the next aggregation run performs a full rebuild."""

    global FORCE_STATISTICS_REBUILD
    FORCE_STATISTICS_REBUILD = True
    with _statistics_cache_lock:
        _statistics_cache["signature"] = None
        _statistics_cache["data"] = None


def _statistics_conn():
    os.makedirs(os.path.dirname(STATISTICS_DB), exist_ok=True)
    conn = sqlite3.connect(STATISTICS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_statistics_tables(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS statistics_aggregate (
            scope TEXT NOT NULL,
            date TEXT NOT NULL,
            online REAL DEFAULT 0.0,
            offline REAL DEFAULT 0.0,
            asleep REAL DEFAULT 0.0,
            km REAL DEFAULT 0.0,
            speed REAL DEFAULT 0.0,
            energy REAL DEFAULT 0.0,
            park_energy_pct REAL DEFAULT 0.0,
            park_km REAL DEFAULT 0.0,
            PRIMARY KEY (scope, date)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS statistics_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS statistics_energy_sessions (
            day TEXT NOT NULL,
            session_key TEXT PRIMARY KEY,
            value REAL DEFAULT 0.0
        )
        """
    )
    conn.commit()


def _get_meta(conn, key, default=None):
    cur = conn.execute("SELECT value FROM statistics_meta WHERE key=?", (key,))
    row = cur.fetchone()
    if row is None:
        return default
    return row[0]


def _set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO statistics_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    conn.commit()


def _reset_statistics_state(conn):
    conn.execute("DELETE FROM statistics_aggregate")
    conn.execute("DELETE FROM statistics_energy_sessions")
    conn.execute("DELETE FROM statistics_meta")
    conn.commit()
    with _statistics_cache_lock:
        _statistics_cache["signature"] = None
        _statistics_cache["data"] = None


def _statistics_missing_recent_days(conn, days=3):
    if days <= 0:
        return False
    expected = {(datetime.now(LOCAL_TZ).date() - timedelta(days=i)).isoformat() for i in range(days)}
    placeholders = ",".join(["?"] * len(expected))
    cur = conn.execute(
        f"SELECT date FROM statistics_aggregate WHERE scope='daily' AND date IN ({placeholders})",
        tuple(expected),
    )
    present = {row[0] for row in cur.fetchall()}
    return bool(expected - present)


def _load_daily_from_db(conn):
    cur = conn.execute(
        "SELECT date, online, offline, asleep, km, speed, energy, park_energy_pct, park_km FROM statistics_aggregate WHERE scope='daily'"
    )
    data = {}
    for row in cur.fetchall():
        data[row[0]] = {
            "online": float(row[1] or 0.0),
            "offline": float(row[2] or 0.0),
            "asleep": float(row[3] or 0.0),
            "km": float(row[4] or 0.0),
            "speed": float(row[5] or 0.0),
            "energy": float(row[6] or 0.0),
            "park_energy_pct": float(row[7] or 0.0),
            "park_km": float(row[8] or 0.0),
        }
    return data


def _write_daily_row(conn, day, payload, scope="daily"):
    conn.execute(
        """
        INSERT INTO statistics_aggregate (
            scope, date, online, offline, asleep, km, speed, energy, park_energy_pct, park_km
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(scope, date) DO UPDATE SET
            online=excluded.online,
            offline=excluded.offline,
            asleep=excluded.asleep,
            km=excluded.km,
            speed=excluded.speed,
            energy=excluded.energy,
            park_energy_pct=excluded.park_energy_pct,
            park_km=excluded.park_km
        """,
        (
            scope,
            day,
            payload.get("online", 0.0),
            payload.get("offline", 0.0),
            payload.get("asleep", 0.0),
            payload.get("km", 0.0),
            payload.get("speed", 0.0),
            payload.get("energy", 0.0),
            payload.get("park_energy_pct", 0.0),
            payload.get("park_km", 0.0),
        ),
    )


def _merge_daily_row(conn, day, payload):
    current = _load_daily_from_db(conn).get(day, {})
    merged = {
        "online": round(float(current.get("online", 0.0)) + payload.get("online", 0.0), 6),
        "offline": round(float(current.get("offline", 0.0)) + payload.get("offline", 0.0), 6),
        "asleep": round(float(current.get("asleep", 0.0)) + payload.get("asleep", 0.0), 6),
        "km": round(float(current.get("km", 0.0)) + payload.get("km", 0.0), 6),
        "speed": max(float(current.get("speed", 0.0)), payload.get("speed", 0.0)),
        "energy": round(float(current.get("energy", 0.0)) + payload.get("energy", 0.0), 6),
        "park_energy_pct": round(
            float(current.get("park_energy_pct", 0.0)) + payload.get("park_energy_pct", 0.0), 6
        ),
        "park_km": round(float(current.get("park_km", 0.0)) + payload.get("park_km", 0.0), 6),
    }
    _write_daily_row(conn, day, merged)
    conn.commit()


def _rebuild_monthly_scope(conn):
    conn.execute("DELETE FROM statistics_aggregate WHERE scope='monthly'")
    cur = conn.execute(
        "SELECT date, online, offline, asleep, km, speed, energy, park_energy_pct, park_km FROM statistics_aggregate WHERE scope='daily'"
    )
    monthly = {}
    for row in cur.fetchall():
        month = row[0][:7]
        m = monthly.setdefault(
            month,
            {
                "online_sum": 0.0,
                "offline_sum": 0.0,
                "asleep_sum": 0.0,
                "km": 0.0,
                "speed": 0.0,
                "energy": 0.0,
                "park_energy_pct": 0.0,
                "park_km": 0.0,
                "count": 0,
            },
        )
        m["online_sum"] += float(row[1] or 0.0)
        m["offline_sum"] += float(row[2] or 0.0)
        m["asleep_sum"] += float(row[3] or 0.0)
        m["km"] += float(row[4] or 0.0)
        m["speed"] = max(m["speed"], float(row[5] or 0.0))
        m["energy"] += float(row[6] or 0.0)
        m["park_energy_pct"] += float(row[7] or 0.0)
        m["park_km"] += float(row[8] or 0.0)
        m["count"] += 1

    for month, payload in monthly.items():
        cnt = payload["count"] or 1
        _write_daily_row(
            conn,
            month,
            {
                "online": round(payload["online_sum"] / cnt, 2),
                "offline": round(payload["offline_sum"] / cnt, 2),
                "asleep": round(payload["asleep_sum"] / cnt, 2),
                "km": round(payload["km"], 2),
                "speed": round(payload["speed"], 2),
                "energy": round(payload["energy"], 2),
                "park_energy_pct": round(payload["park_energy_pct"], 2),
                "park_km": round(payload["park_km"], 2),
            },
            scope="monthly",
        )
    conn.commit()


def _seed_energy_sessions_from_log(conn, offset=0):
    path = resolve_log_path(_default_vehicle_id or default_vehicle_id(), "energy.log")
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    if offset > size:
        offset = 0

    try:
        with open(path, "r", encoding="utf-8") as handle:
            handle.seek(offset)
            for line in handle:
                idx = line.find("{")
                if idx == -1:
                    continue
                ts_str = line[:idx].strip()
                ts_dt = _parse_log_time(ts_str)
                if ts_dt is None:
                    continue
                try:
                    entry = json.loads(line[idx:])
                    vid = entry.get("vehicle_id")
                    val = float(entry.get("added_energy", 0.0))
                except Exception:
                    continue

                if val <= 0:
                    continue
                day = ts_dt.date().isoformat()
                session_key = (vid if vid is not None else "__default__") + "|" + ts_dt.isoformat()
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO statistics_energy_sessions(day, session_key, value) VALUES(?, ?, ?)",
                        (day, session_key, val),
                    )
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    conn.commit()
    _set_meta(conn, "energy_offset", size)


def _distribute_state_duration(conn, start, end, state):
    if start is None or end is None or state is None:
        return
    if end <= start:
        return
    current = start
    total_seconds = 24 * 3600
    while current < end:
        day = datetime.fromtimestamp(current, LOCAL_TZ).date()
        next_day = datetime.combine(day + timedelta(days=1), datetime.min.time(), LOCAL_TZ).timestamp()
        segment_end = min(end, next_day)
        duration = segment_end - current
        pct = round(duration / total_seconds * 100.0, 6)
        key = state if state in {"online", "offline", "asleep"} else "offline"
        _merge_daily_row(conn, day.isoformat(), {key: pct})
        current = segment_end


def _process_state_log_increment(conn):
    vid = _default_vehicle_id or default_vehicle_id()
    path = resolve_log_path(vid, "state.log")
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0

    offset = int(float(_get_meta(conn, "state_offset", 0) or 0))
    if offset > size:
        offset = 0

    last_ts = None
    last_state = _get_meta(conn, "state_last_state")
    ts_val = _get_meta(conn, "state_last_ts")
    if ts_val is not None:
        try:
            last_ts = float(ts_val)
        except (TypeError, ValueError):
            last_ts = None

    entries = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            handle.seek(offset)
            for line in handle:
                idx = line.find("{")
                if idx == -1:
                    continue
                ts_str = line[:idx].strip()
                ts_dt = _parse_log_time(ts_str)
                if ts_dt is None:
                    continue
                try:
                    data = json.loads(line[idx:])
                    state = data.get("state")
                except Exception:
                    continue
                entries.append((ts_dt.timestamp(), state))
    except FileNotFoundError:
        entries = []
    except Exception:
        entries = []

    if last_ts is None and entries:
        last_ts, last_state = entries[0]
        entries = entries[1:]

    now_ts = time.time()
    for ts, state in entries:
        if last_state is not None and last_ts is not None:
            _distribute_state_duration(conn, last_ts, ts, last_state)
        last_ts = ts
        last_state = state

    if last_state is not None and last_ts is not None:
        _distribute_state_duration(conn, last_ts, now_ts, last_state)
        last_ts = now_ts

    _set_meta(conn, "state_last_ts", last_ts or 0)
    if last_state is not None:
        _set_meta(conn, "state_last_state", last_state)
    _set_meta(conn, "state_offset", size)


def _process_energy_log_increment(conn):
    vid = _default_vehicle_id or default_vehicle_id()
    path = resolve_log_path(vid, "energy.log")
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    offset = int(float(_get_meta(conn, "energy_offset", 0) or 0))
    if offset > size:
        offset = 0

    try:
        with open(path, "r", encoding="utf-8") as handle:
            handle.seek(offset)
            for line in handle:
                idx = line.find("{")
                if idx == -1:
                    continue
                ts_str = line[:idx].strip()
                ts_dt = _parse_log_time(ts_str)
                if ts_dt is None:
                    continue
                try:
                    entry = json.loads(line[idx:])
                    vid_val = entry.get("vehicle_id")
                    val = float(entry.get("added_energy", 0.0))
                except Exception:
                    continue
                if val <= 0:
                    continue
                session_key = (vid_val if vid_val is not None else "__default__") + "|" + ts_dt.isoformat()
                day = ts_dt.date().isoformat()
                cur = conn.execute(
                    "SELECT value FROM statistics_energy_sessions WHERE session_key=?",
                    (session_key,),
                ).fetchone()
                previous = float(cur[0]) if cur else 0.0
                if val > previous:
                    delta = val - previous
                    _merge_daily_row(conn, day, {"energy": delta})
                    conn.execute(
                        "INSERT INTO statistics_energy_sessions(day, session_key, value) VALUES(?, ?, ?) ON CONFLICT(session_key) DO UPDATE SET value=excluded.value",
                        (day, session_key, val),
                    )
    except FileNotFoundError:
        pass
    except Exception:
        pass
    conn.commit()
    _set_meta(conn, "energy_offset", size)


def _distribute_parking_loss(conn, start_ts, end_ts, pct_loss, range_loss):
    if pct_loss <= 0 and range_loss <= 0:
        return
    if start_ts is None and end_ts is None:
        return
    if start_ts is None:
        _merge_daily_row(conn, end_ts.date().isoformat(), {"park_energy_pct": pct_loss, "park_km": range_loss})
        return
    if end_ts is None or end_ts <= start_ts:
        _merge_daily_row(conn, start_ts.date().isoformat(), {"park_energy_pct": pct_loss, "park_km": range_loss})
        return
    total_seconds = (end_ts - start_ts).total_seconds()
    if total_seconds <= 0:
        _merge_daily_row(conn, start_ts.date().isoformat(), {"park_energy_pct": pct_loss, "park_km": range_loss})
        return
    cursor = start_ts
    allocated_pct = 0.0
    allocated_range = 0.0
    while cursor.date() < end_ts.date():
        next_midnight = datetime.combine(cursor.date() + timedelta(days=1), datetime.min.time(), tzinfo=cursor.tzinfo)
        span = (next_midnight - cursor).total_seconds()
        if span <= 0:
            break
        share = span / total_seconds
        share_pct = pct_loss * share
        share_range = range_loss * share
        _merge_daily_row(
            conn,
            cursor.date().isoformat(),
            {"park_energy_pct": share_pct, "park_km": share_range},
        )
        allocated_pct += share_pct
        allocated_range += share_range
        cursor = next_midnight
    remaining_pct = max(pct_loss - allocated_pct, 0.0)
    remaining_range = max(range_loss - allocated_range, 0.0)
    _merge_daily_row(
        conn, end_ts.date().isoformat(), {"park_energy_pct": remaining_pct, "park_km": remaining_range}
    )


def _process_parking_log_increment(conn):
    path = os.path.join(DATA_DIR, "park-loss.log")
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    offset = int(float(_get_meta(conn, "parking_offset", 0) or 0))
    if offset > size:
        offset = 0
    try:
        with open(path, "r", encoding="utf-8") as handle:
            handle.seek(offset)
            for line in handle:
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if not isinstance(entry, dict):
                    continue
                start = entry.get("start")
                end = entry.get("end")
                pct_loss = _as_float(entry.get("energy_pct")) or 0.0
                range_loss = _as_float(entry.get("range_km")) or 0.0
                try:
                    start_ts = datetime.fromisoformat(start) if start else None
                    end_ts = datetime.fromisoformat(end) if end else None
                except Exception:
                    start_ts = None
                    end_ts = None
                _distribute_parking_loss(conn, start_ts, end_ts, pct_loss, range_loss)
    except FileNotFoundError:
        pass
    except Exception:
        pass
    conn.commit()
    _set_meta(conn, "parking_offset", size)


def _snapshot_trip_file_state(conn):
    meta = {}
    for path in _get_trip_files():
        try:
            stat = os.stat(path)
        except OSError:
            continue
        meta[path] = {
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "km": _trip_distance(path),
            "speed": _trip_max_speed(path),
        }
    _set_meta(conn, "trip_files_meta", json.dumps(meta))


def _process_trip_files_increment(conn):
    raw_meta = _get_meta(conn, "trip_files_meta")
    meta_missing = raw_meta is None
    try:
        meta = json.loads(raw_meta) if isinstance(raw_meta, str) else {}
    except Exception:
        meta = {}

    if meta_missing and _get_meta(conn, "statistics_initialized") == "1":
        _snapshot_trip_file_state(conn)
        return
    updated_meta = {}

    for path in _get_trip_files():
        try:
            stat = os.stat(path)
        except OSError:
            continue

        previous = meta.get(path, {})
        prev_mtime = float(previous.get("mtime", 0.0) or 0.0)
        prev_size = int(previous.get("size", 0) or 0)
        prev_km = float(previous.get("km", 0.0) or 0.0)
        changed = stat.st_mtime != prev_mtime or stat.st_size != prev_size
        if not changed:
            updated_meta[path] = previous
            continue

        km = _trip_distance(path)
        speed = _trip_max_speed(path)
        fname = os.path.basename(path)
        date_str = fname.split("_")[-1].split(".")[0]
        try:
            day = datetime.strptime(date_str, "%Y%m%d").date().isoformat()
        except Exception:
            day = date_str

        delta_km = km - prev_km if km > prev_km else 0.0
        payload = {"speed": speed}
        if delta_km > 0:
            payload["km"] = delta_km
        _merge_daily_row(conn, day, payload)

        updated_meta[path] = {
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "km": km,
            "speed": speed,
        }

    _set_meta(conn, "trip_files_meta", json.dumps(updated_meta))


def _initial_statistics_backfill(conn):
    stats = compute_statistics()
    for day, payload in stats.items():
        _write_daily_row(conn, day, payload)
    conn.commit()
    _rebuild_monthly_scope(conn)
    _snapshot_trip_file_state(conn)
    try:
        with open(resolve_log_path(_default_vehicle_id or default_vehicle_id(), "state.log"), "r", encoding="utf-8") as handle:
            last_line = None
            for line in handle:
                last_line = line
            if last_line:
                idx = last_line.find("{")
                ts_str = last_line[:idx].strip() if idx != -1 else None
                ts_dt = _parse_log_time(ts_str) if ts_str else None
                if ts_dt:
                    try:
                        data = json.loads(last_line[idx:])
                        _set_meta(conn, "state_last_state", data.get("state"))
                        _set_meta(conn, "state_last_ts", ts_dt.timestamp())
                    except Exception:
                        pass
    except Exception:
        pass
    _set_meta(conn, "state_offset", os.path.getsize(resolve_log_path(_default_vehicle_id or default_vehicle_id(), "state.log")) if os.path.exists(resolve_log_path(_default_vehicle_id or default_vehicle_id(), "state.log")) else 0)
    _seed_energy_sessions_from_log(conn)
    _set_meta(conn, "parking_offset", os.path.getsize(os.path.join(DATA_DIR, "park-loss.log")) if os.path.exists(os.path.join(DATA_DIR, "park-loss.log")) else 0)
    _set_meta(conn, "statistics_initialized", "1")


def _statistics_aggregation_tick():
    global FORCE_STATISTICS_REBUILD
    with _aggregation_lock:
        conn = None
        try:
            conn = _statistics_conn()
            _ensure_statistics_tables(conn)
            initialized = _get_meta(conn, "statistics_initialized") == "1"
            rebuild_due_to_gap = initialized and _statistics_missing_recent_days(conn)
            if FORCE_STATISTICS_REBUILD or rebuild_due_to_gap:
                logging.warning(
                    "Forcing statistics rebuild%s",
                    " due to missing recent days" if rebuild_due_to_gap else "",
                )
                _reset_statistics_state(conn)
                FORCE_STATISTICS_REBUILD = False
                initialized = False

            if not initialized:
                _initial_statistics_backfill(conn)
            _process_state_log_increment(conn)
            _process_energy_log_increment(conn)
            _compute_parking_losses()
            _process_parking_log_increment(conn)
            _process_trip_files_increment(conn)
            _rebuild_monthly_scope(conn)
        finally:
            if conn is not None:
                conn.close()


def _statistics_aggregation_loop(interval):
    while True:
        try:
            _statistics_aggregation_tick()
        except Exception:
            logging.exception("Statistics aggregation failed")
        time.sleep(max(1.0, interval))


def _start_statistics_aggregation(interval=None):
    global _aggregation_thread, _aggregation_initialized
    if DISABLE_STATISTICS_AGGREGATION:
        return
    if _aggregation_thread and _aggregation_thread.is_alive():
        return
    _aggregation_thread = threading.Thread(
        target=_statistics_aggregation_loop, args=(interval or AGGREGATION_INTERVAL,), daemon=True
    )
    _aggregation_thread.start()
    _aggregation_initialized = True
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
    shift = _normalize_shift_state(drive.get("shift_state"))
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
    shift = _normalize_shift_state(drive.get("shift_state"))
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
        key = _vehicle_key(vehicle_id)
        with state_lock:
            if last_vehicle_state.get(key) != state:
                last_vehicle_state[key] = state
                logger = _get_state_logger(vehicle_id)
                logger.info(
                    json.dumps({"vehicle_id": vehicle_id, "state": state})
                )
    except Exception:
        pass


def _last_logged_energy(vehicle_id):
    """Return the last logged energy value for ``vehicle_id`` or ``None``."""
    _ts, value = _last_logged_energy_entry(vehicle_id)
    return value


def _last_logged_energy_entry(vehicle_id):
    """Return the timestamp and value of the last energy entry for a vehicle."""
    try:
        with open(
            resolve_log_path(vehicle_id, "energy.log"), "r", encoding="utf-8"
        ) as f:
            lines = f.readlines()
        for line in reversed(lines):
            idx = line.find("{")
            if idx != -1:
                try:
                    entry = json.loads(line[idx:])
                    if entry.get("vehicle_id") == vehicle_id:
                        ts_str = line[:idx].strip()
                        ts_dt = _parse_log_time(ts_str)
                        val = float(entry.get("added_energy", 0.0))
                        return ts_dt, val
                except Exception:
                    continue
    except Exception:
        pass
    return None, None


def _log_energy(vehicle_id, amount, timestamp=None):
    """Store the last added energy in ``energy.log`` using local time.

    Within a 30 minute window duplicate entries for the same vehicle are
    suppressed. When multiple distinct values are recorded in that interval the
    new amount is logged so every reported session value is preserved.

    Additional writes are blocked until a new charging session starts unless
    the new value differs from the last persisted amount. This prevents moving
    logged energy to a different day while still keeping all reported values.

    When ``timestamp`` is provided it is used as the log timestamp so that
    energy is associated with the start of the charging session rather than the
    completion time.

    Returns ``True`` when a new entry was written and ``False`` otherwise.
    """

    def _has_recent_entry(lines, reference_dt, vehicle, amount, eps):
        for line in lines:
            idx = line.find("{")
            if idx == -1:
                continue
            ts_str = line[:idx].strip()
            ts_dt = _parse_log_time(ts_str)
            if ts_dt is None:
                continue
            try:
                data = json.loads(line[idx:])
            except Exception:
                continue
            if data.get("vehicle_id") != vehicle:
                continue
            logged_amount = None
            try:
                logged_amount = float(data.get("added_energy", 0.0))
            except Exception:
                logged_amount = None
            if (
                logged_amount is not None
                and amount is not None
                and abs(logged_amount - amount) > eps
            ):
                # Allow session updates with different energy values to be
                # recorded immediately.
                continue
            if reference_dt is None:
                return True
            if ts_dt >= reference_dt:
                return True
            try:
                delta = (reference_dt - ts_dt).total_seconds()
            except Exception:
                continue
            if 0 <= delta <= 30 * 60:
                return True
        return False

    written = False
    try:
        with _energy_log_lock:
            eps = 0.001
            logger = _get_energy_logger(vehicle_id)
            last_ts, last = _last_logged_energy_entry(vehicle_id)
            marker_before = _current_last_energy_marker(vehicle_id)
            stored_marker = _last_energy_markers.get(vehicle_id)
            if stored_marker is None and marker_before is not None:
                _last_energy_markers[vehicle_id] = marker_before
                stored_marker = marker_before
            try:
                amount_val = float(amount)
            except (TypeError, ValueError):
                amount_val = None
            except Exception:
                amount_val = None
            if amount_val is None:
                return False

            now = datetime.now(LOCAL_TZ)
            ts_dt = timestamp
            if isinstance(ts_dt, (int, float)):
                ts_dt = datetime.fromtimestamp(ts_dt, LOCAL_TZ)
            if ts_dt is not None and ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=LOCAL_TZ)
            if ts_dt is None:
                ts_dt = now
            else:
                ts_dt = ts_dt.astimezone(LOCAL_TZ)

            allow_update = (
                last is not None
                and last_ts is not None
                and amount_val is not None
                and ts_dt is not None
                and ts_dt >= last_ts
                and abs(amount_val - last) > eps
            )
            if vehicle_id in _recently_logged_sessions and not (
                allow_update
            ):
                return False

            if (
                last is not None
                and amount_val is not None
                and abs(amount_val - last) <= eps
            ):
                if (
                    marker_before is not None
                    and stored_marker is not None
                    and marker_before == stored_marker
                ):
                    return False
                if not (
                    last_ts is not None
                    and ts_dt is not None
                    and ts_dt > last_ts
                ):
                    return False
            primary_path = log_file(vehicle_id, "energy.log")
            handler = next(
                (h for h in reversed(logger.handlers) if getattr(h, "stream", None)),
                None,
            )
            filename = getattr(handler, "baseFilename", None) or primary_path
            line_tpl = "{ts} {msg}\n"
            ts_str = ts_dt.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
            has_recent_entry = False

            stream = getattr(handler, "stream", None)

            if handler is not None and stream is not None:
                handler.acquire()
                try:
                    handler.flush()
                    readable = getattr(stream, "readable", lambda: False)()
                    seekable = getattr(stream, "seekable", lambda: False)()
                    if readable and seekable:
                        stream.seek(0)
                        lines = stream.readlines()
                        has_recent_entry = _has_recent_entry(
                            lines, ts_dt, vehicle_id, amount_val, eps
                        )
                except UnsupportedOperation:
                    pass
                except Exception:
                    pass
                finally:
                    handler.release()

            if not has_recent_entry:
                try:
                    with open(filename, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except FileNotFoundError:
                    lines = []
                except Exception:
                    lines = []

                has_recent_entry = _has_recent_entry(
                    lines, ts_dt, vehicle_id, amount_val, eps
                )

            if (
                has_recent_entry
                and last_ts is not None
                and ts_dt is not None
                and ts_dt > last_ts
            ):
                has_recent_entry = False

            if has_recent_entry:
                return False

            entry = json.dumps({"vehicle_id": vehicle_id, "added_energy": amount_val})
            line = line_tpl.format(ts=ts_str, msg=entry)

            if handler is not None and stream is not None:
                handler.acquire()
                try:
                    writable = getattr(stream, "writable", lambda: False)()
                    seekable = getattr(stream, "seekable", lambda: False)()
                    if writable and seekable:
                        stream.seek(0, os.SEEK_END)
                        stream.write(line)
                        stream.flush()
                        written = True
                except UnsupportedOperation:
                    pass
                except Exception:
                    pass
                finally:
                    handler.release()

            if not written:
                try:
                    with open(filename, "a", encoding="utf-8") as f:
                        f.write(line)
                    written = True
                except Exception:
                    pass

            if written and filename != primary_path:
                try:
                    os.makedirs(os.path.dirname(primary_path), exist_ok=True)
                    with open(primary_path, "a", encoding="utf-8") as f:
                        f.write(line)
                except Exception:
                    pass

            if written:
                _recently_logged_sessions.add(vehicle_id)
                if marker_before is not None:
                    _last_energy_markers[vehicle_id] = marker_before
    except Exception:
        return False
    return written


def _range_to_km(value):
    """Return ``value`` converted to kilometres when possible."""

    if value is None:
        return None
    try:
        if isinstance(value, dict):
            val = float(value.get("value", 0.0))
            unit = str(value.get("unit") or "").lower()
            if unit in ("km", "kilometer", "kilometre"):
                return val
            if unit in ("mi", "mile", "miles"):
                return val * MILES_TO_KM
            return None
        val = float(value)
    except Exception:
        return None
    if val < 0:
        return None
    return val * MILES_TO_KM


def _extract_dashboard_range_km(charge_state):
    """Return the range in kilometres using the dashboard preference order."""

    if not isinstance(charge_state, dict):
        return None
    for key in (
        "ideal_battery_range",
        "est_battery_range",
        "battery_range",
        "rated_battery_range",
    ):
        rng = _range_to_km(charge_state.get(key))
        if rng is not None:
            return rng
    return None


def _as_float(value):
    """Return ``value`` converted to ``float`` or ``None`` on failure."""

    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _normalize_shift_state(shift):
    """Return the shift state normalised for comparisons."""

    if shift is None:
        return None

    if isinstance(shift, str):
        value = shift.strip()
    else:
        try:
            value = str(shift).strip()
        except Exception:
            return None

    if not value:
        return None

    upper = value.upper()
    if upper in {"N/A", "NA", "UNKNOWN"}:
        return None
    if upper == "PARK":
        return "P"
    return upper


def _parking_log_path(filename=None):
    """Return the path to the dashboard parking log file."""

    if filename:
        return filename
    return os.path.join(DATA_DIR, PARK_UI_LOG)


def _load_last_parking_entry(vehicle_id, filename=None):
    """Return the last logged parking entry for ``vehicle_id`` or ``None``."""

    path = _parking_log_path(filename)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            tail = deque(handle, maxlen=256)
    except FileNotFoundError:
        return None
    except Exception:
        return None

    for line in reversed(tail):
        idx = line.find("{")
        if idx == -1:
            continue
        ts_str = line[:idx].strip()
        try:
            payload = json.loads(line[idx:])
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        vid = str(payload.get("vehicle_id") or "")
        if vid and vehicle_id is not None and vid != vehicle_id:
            continue
        entry = {
            "vehicle_id": vid or vehicle_id,
            "battery_pct": _as_float(payload.get("battery_pct")),
            "range_km": _as_float(payload.get("range_km")),
            "state": payload.get("state") or None,
            "session": payload.get("session") or None,
        }
        ts_dt = _parse_log_time(ts_str)
        if ts_dt is not None:
            entry["timestamp"] = ts_dt
        return entry
    return None


def _log_dashboard_parking_sample(
    vehicle_id,
    timestamp=None,
    battery_pct=None,
    range_km=None,
    state=None,
    session=None,
    filename=None,
):
    """Persist a single parking sample used by the dashboard backend."""

    if vehicle_id in (None, ""):
        vehicle_id = "default"
    vehicle_id = str(vehicle_id)

    if timestamp is None:
        timestamp = datetime.now(LOCAL_TZ)
    elif isinstance(timestamp, (int, float)):
        timestamp = datetime.fromtimestamp(timestamp, LOCAL_TZ)
    elif timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=LOCAL_TZ)
    else:
        timestamp = timestamp.astimezone(LOCAL_TZ)

    pct = _as_float(battery_pct)
    rng = _as_float(range_km)
    if pct is None and rng is None and state is None:
        return False

    record = {
        "vehicle_id": vehicle_id,
        "battery_pct": None if pct is None else round(pct, 6),
        "range_km": None if rng is None else round(rng, 6),
        "state": state or None,
        "session": str(session) if session is not None else None,
    }

    last = _last_parking_samples.get(vehicle_id)
    if last is None:
        last = _load_last_parking_entry(vehicle_id, filename=filename)
        if last is not None:
            cached = {
                "battery_pct": last.get("battery_pct"),
                "range_km": last.get("range_km"),
                "state": last.get("state"),
                "session": last.get("session"),
            }
            _last_parking_samples[vehicle_id] = cached
            last = cached

    def _normalized(value):
        if value is None:
            return None
        try:
            return round(float(value), 6)
        except Exception:
            return None

    if last:
        if (
            _normalized(last.get("battery_pct")) == record["battery_pct"]
            and _normalized(last.get("range_km")) == record["range_km"]
            and (last.get("state") or None) == record["state"]
            and (last.get("session") or None) == record["session"]
        ):
            return False

    path = _parking_log_path(filename)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass

    ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    line = f"{ts_str} {json.dumps(record, ensure_ascii=False)}\n"
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception:
        return False

    _last_parking_samples[vehicle_id] = {
        "battery_pct": record["battery_pct"],
        "range_km": record["range_km"],
        "state": record["state"],
        "session": record["session"],
    }
    return True


def _record_dashboard_parking_state(vehicle_id, data):
    """Record a dashboard parking sample when the vehicle is parked."""

    if not isinstance(data, dict):
        return

    charge_state = data.get("charge_state") or {}
    drive_state = data.get("drive_state") or {}

    shift = _normalize_shift_state(drive_state.get("shift_state"))
    charging_state = str(charge_state.get("charging_state") or "")
    state_value = data.get("state")

    speed_val = _as_float(drive_state.get("speed"))
    power_val = _as_float(drive_state.get("power"))
    is_stationary = True
    if speed_val is not None and abs(speed_val) > 0.05:
        is_stationary = False
    if power_val is not None and abs(power_val) > 1:
        is_stationary = False

    session_key = str(vehicle_id)
    session = _active_parking_sessions.get(session_key)

    is_park = shift == "P"
    is_unknown = shift is None
    assume_parked = (
        is_unknown
        and is_stationary
        and (state_value in {None, "online", "asleep", "parked", "offline"})
    )
    parked = is_park or assume_parked or (session is not None and is_unknown)
    charging = charging_state in PARKING_CHARGING_STATES

    if parked and not charging:
        if session is None:
            session_id = f"{session_key}-{datetime.now(LOCAL_TZ).isoformat()}"
            session = {"id": session_id, "state": state_value or "parked"}
            _active_parking_sessions[session_key] = session
        elif session.get("id") is None:
            session["id"] = f"{session_key}-{datetime.now(LOCAL_TZ).isoformat()}"

        if state_value:
            session["state"] = state_value

        pct = charge_state.get("usable_battery_level")
        if pct is None:
            pct = charge_state.get("battery_level")
        pct_val = _as_float(pct)
        rng_val = _extract_dashboard_range_km(charge_state)

        state_for_log = session.get("state") or "parked"
        _log_dashboard_parking_sample(
            vehicle_id,
            battery_pct=pct_val,
            range_km=rng_val,
            state=state_for_log,
            session=session.get("id"),
        )
        return

    if session is not None:
        _active_parking_sessions.pop(session_key, None)


def _log_sms(message, success, vehicle_id=None):
    """Append SMS information to ``sms.log``."""
    try:
        logger = _get_sms_logger(vehicle_id)
        logger.info(json.dumps({"message": message, "success": success}))
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
        marker = _current_last_energy_marker(vehicle_id)
        if marker is not None:
            _last_energy_markers[vehicle_id] = marker
    except Exception:
        pass


_charging_session_start = {}
_recently_logged_sessions = set()
_energy_log_lock = threading.Lock()
_last_energy_markers = {}


def _current_last_energy_marker(vehicle_id):
    """Return a marker tuple for ``last_energy.txt`` of ``vehicle_id``."""

    try:
        path = _last_energy_file(vehicle_id)
        stat = os.stat(path)
        return (stat.st_mtime_ns, stat.st_size)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _session_start_file(vehicle_id):
    """Return filename that stores the current charging session start time."""
    return os.path.join(vehicle_dir(vehicle_id), "charge_session_start.txt")


def _load_session_start(vehicle_id):
    """Return stored charging session start timestamp for ``vehicle_id``."""
    start = _charging_session_start.get(vehicle_id)
    if start is not None:
        return start
    try:
        with open(_session_start_file(vehicle_id), "r", encoding="utf-8") as f:
            ts_str = f.read().strip()
        if not ts_str:
            return None
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=LOCAL_TZ)
        else:
            dt = dt.astimezone(LOCAL_TZ)
        _charging_session_start[vehicle_id] = dt
        return dt
    except Exception:
        return None


def _save_session_start(vehicle_id, start_dt):
    """Persist the charging session start timestamp for ``vehicle_id``."""
    if start_dt is None:
        return
    _recently_logged_sessions.discard(vehicle_id)
    try:
        if isinstance(start_dt, (int, float)):
            start_dt = datetime.fromtimestamp(start_dt, LOCAL_TZ)
        elif isinstance(start_dt, datetime):
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=LOCAL_TZ)
            else:
                start_dt = start_dt.astimezone(LOCAL_TZ)
        else:
            return
        os.makedirs(vehicle_dir(vehicle_id), exist_ok=True)
        with open(_session_start_file(vehicle_id), "w", encoding="utf-8") as f:
            f.write(start_dt.isoformat())
        _charging_session_start[vehicle_id] = start_dt
    except Exception:
        pass


def _clear_session_start(vehicle_id):
    """Remove persisted start timestamp for ``vehicle_id`` if present."""
    _charging_session_start.pop(vehicle_id, None)
    _recently_logged_sessions.discard(vehicle_id)
    try:
        os.remove(_session_start_file(vehicle_id))
    except FileNotFoundError:
        pass
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

    vid = None
    try:
        vid = vehicle_data.get("id_s") or vehicle_data.get("vehicle_id")
    except Exception:
        vid = None
    vid = _vehicle_key(vid)

    cfg = load_config(vehicle_id=vid)
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
    vid = vid or _vehicle_key(vehicle_data.get("id_s") or vehicle_data.get("vehicle_id"))
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


def _load_state_entries(filename=None, vehicle_id=None):
    """Parse state log entries as (timestamp, state) tuples."""

    if filename is None:
        filename = resolve_log_path(vehicle_id, "state.log")

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


def _compute_energy_stats(filename=None, vehicle_id=None):
    """Return per-day added energy in kWh based on ``energy.log``."""
    if filename is None:
        filename = resolve_log_path(vehicle_id, "energy.log")

    eps = 0.001
    daily_sessions = {}

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
                try:
                    entry = json.loads(line[idx:])
                    vid = entry.get("vehicle_id")
                    val = float(entry.get("added_energy", 0.0))
                except Exception:
                    continue

                if val <= eps:
                    continue

                day = ts_dt.date().isoformat()
                session_key = (
                    vid if vid is not None else "__default__",
                    ts_dt.isoformat(),
                )

                sessions = daily_sessions.setdefault(day, {})
                previous = sessions.get(session_key)
                if previous is None or val > previous:
                    sessions[session_key] = val
    except Exception:
        pass

    energy = {}
    for day, sessions in daily_sessions.items():
        total = sum(sessions.values())
        if total > eps:
            energy[day] = round(total, 6)

    return energy


def _iter_parking_log_lines(filename):
    """Yield (timestamp, payload) tuples from the dashboard parking log."""

    if not filename:
        return

    path = _parking_log_path(filename)

    def _read(pathname):
        try:
            with open(pathname, "r", encoding="utf-8") as handle:
                for line in handle:
                    idx = line.find("{")
                    if idx == -1:
                        continue
                    ts_str = line[:idx].strip()
                    ts_dt = _parse_log_time(ts_str)
                    if ts_dt is None:
                        continue
                    try:
                        payload = json.loads(line[idx:])
                    except Exception:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    yield ts_dt, payload
        except FileNotFoundError:
            return
        except Exception:
            return

    base_dir = os.path.dirname(path) or "."
    base_name = os.path.basename(path)

    rotated = []
    for candidate in glob.glob(os.path.join(base_dir, f"{base_name}.*")):
        try:
            mtime = os.path.getmtime(candidate)
        except OSError:
            continue
        rotated.append((mtime, candidate))
    rotated.sort(key=lambda item: (item[0], item[1]))

    for _mtime, candidate in rotated:
        yield from _read(candidate)

    if os.path.exists(path):
        yield from _read(path)


def _process_dashboard_parking_log(filename, distribute_loss):
    """Populate parking losses from the dashboard parking log."""

    sessions = {}
    processed = False
    drop_tolerance = 0.01

    for ts_dt, payload in _iter_parking_log_lines(filename):
        processed = True
        vehicle_id = str(payload.get("vehicle_id") or "default")
        session_id = payload.get("session")
        if session_id is None:
            session_key = (vehicle_id, "__default__")
        else:
            session_key = (vehicle_id, str(session_id))

        pct = _as_float(payload.get("battery_pct"))
        rng_km = _as_float(payload.get("range_km"))
        state_value = payload.get("state") or "parked"

        session = sessions.get(session_key)
        if session is None:
            sessions[session_key] = {
                "pct": pct,
                "range": rng_km,
                "pct_min": pct,
                "range_min": rng_km,
                "ts": ts_dt,
                "state": state_value,
            }
            continue

        if state_value:
            session["state"] = state_value

        last_ts = session.get("ts")
        pct_baseline = session.get("pct_min")
        range_baseline = session.get("range_min")
        pct_loss = 0.0
        range_loss = 0.0

        if pct is not None and pct_baseline is not None:
            drop = pct_baseline - pct
            if drop > drop_tolerance:
                pct_loss = drop

        if rng_km is not None and range_baseline is not None:
            drop_range = range_baseline - rng_km
            if drop_range > drop_tolerance:
                range_loss = drop_range

        if (
            (pct_loss > 0 or range_loss > 0)
            and last_ts is not None
            and ts_dt is not None
            and ts_dt > last_ts
        ):
            distribute_loss(last_ts, ts_dt, pct_loss, range_loss, session.get("state") or "parked")

        updated_measurement = False
        if pct is not None:
            session["pct"] = pct
            if pct_loss > 0 or pct_baseline is None:
                session["pct_min"] = pct
            updated_measurement = True
        if rng_km is not None:
            session["range"] = rng_km
            if range_loss > 0 or range_baseline is None:
                session["range_min"] = rng_km
            updated_measurement = True
        if (updated_measurement or session.get("ts") is None) and ts_dt is not None:
            session["ts"] = ts_dt

    return processed


def _process_legacy_parking_log(filename, distribute_loss, vehicle_id=None):
    """Populate parking losses from the legacy ``api.log`` format."""

    if not filename:
        return False

    files = []
    sessions = {}
    processed = False

    api_path = resolve_log_path(vehicle_id, "api.log") if filename else None

    if filename == api_path:
        rotated = []
        for path in glob.glob(f"{filename}.*"):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            rotated.append((mtime, path))
        rotated.sort(key=lambda item: (item[0], item[1]))
        files.extend(path for _mtime, path in rotated)

    if filename and os.path.exists(filename):
        files.append(filename)

    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    idx = line.find("{")
                    if idx == -1:
                        continue
                    ts_str = line[:idx].strip()
                    ts_dt = _parse_log_time(ts_str)
                    if ts_dt is None:
                        continue
                    try:
                        payload = json.loads(line[idx:])
                    except Exception:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("endpoint") != "get_vehicle_data":
                        continue
                    data = payload.get("data")
                    if not isinstance(data, dict):
                        continue

                    processed = True

                    vid = data.get("id_s") or data.get("vehicle_id") or "default"
                    vid = str(vid)

                    charge_state = data.get("charge_state") or {}
                    drive_state = data.get("drive_state") or {}
                    shift = _normalize_shift_state(drive_state.get("shift_state"))
                    speed_val = _as_float(drive_state.get("speed"))
                    power_val = _as_float(drive_state.get("power"))
                    charging_state = str(charge_state.get("charging_state") or "")

                    state_value = data.get("state")
                    if not isinstance(state_value, str) or not state_value:
                        state_value = "parked"

                    pct = charge_state.get("usable_battery_level")
                    if pct is None:
                        pct = charge_state.get("battery_level")
                    pct = _as_float(pct)

                    rng_km = _extract_dashboard_range_km(charge_state)

                    session = sessions.get(vid)

                    is_stationary = True
                    if speed_val is not None and abs(speed_val) > 0.05:
                        is_stationary = False
                    if power_val is not None and abs(power_val) > 1:
                        is_stationary = False

                    is_park = shift == "P"
                    is_unknown = shift is None
                    parked = is_stationary and (
                        is_park or (session is not None and is_unknown)
                    )
                    charging = charging_state in PARKING_CHARGING_STATES

                    if parked and not charging:
                        if session is None:
                            sessions[vid] = {
                                "pct": pct,
                                "range": rng_km,
                                "ts": ts_dt,
                                "state": state_value,
                            }
                            continue

                        if state_value:
                            session["state"] = state_value
                        context = session.get("state") or "parked"

                        last_pct = session.get("pct")
                        last_range = session.get("range")
                        pct_loss = 0.0
                        range_loss = 0.0
                        if pct is not None and last_pct is not None:
                            pct_loss = last_pct - pct
                            if pct_loss < 0:
                                pct_loss = 0.0
                        if rng_km is not None and last_range is not None:
                            range_loss = last_range - rng_km
                            if range_loss < 0:
                                range_loss = 0.0
                        if pct_loss > 0 or range_loss > 0:
                            distribute_loss(
                                session.get("ts"),
                                ts_dt,
                                pct_loss,
                                range_loss,
                                context,
                            )
                        updated_measurement = False
                        if pct is not None:
                            session["pct"] = pct
                            updated_measurement = True
                        if rng_km is not None:
                            session["range"] = rng_km
                            updated_measurement = True
                        if updated_measurement or session.get("ts") is None:
                            session["ts"] = ts_dt
                        continue

                    if session is None:
                        continue

                    if not parked:
                        if state_value:
                            session["state"] = state_value
                        # Leaving ``P`` indicates the vehicle started moving.
                        # Any change in state of charge between the last
                        # parked snapshot and this driving entry should not be
                        # attributed to parking losses.
                        sessions.pop(vid, None)
                        continue

                    if charging:
                        pct_loss = 0.0
                        range_loss = 0.0
                        last_pct = session.get("pct")
                        last_range = session.get("range")
                        context = session.get("state") or "parked"
                        if pct is not None and last_pct is not None:
                            pct_loss = last_pct - pct
                            if pct_loss < 0:
                                pct_loss = 0.0
                        if rng_km is not None and last_range is not None:
                            range_loss = last_range - rng_km
                            if range_loss < 0:
                                range_loss = 0.0
                        if pct_loss > 0 or range_loss > 0:
                            distribute_loss(
                                session.get("ts"),
                                ts_dt,
                                pct_loss,
                                range_loss,
                                context,
                            )
                        if pct is not None:
                            session["pct"] = pct
                        if rng_km is not None:
                            session["range"] = rng_km
                        if state_value:
                            session["state"] = state_value
                        session["ts"] = ts_dt
                        continue
        except FileNotFoundError:
            continue
        except Exception:
            continue

    return processed


def _compute_parking_losses(filename=None, vehicle_id=None):
    """Return per-day energy percentage and range losses while parked."""

    if filename is None:
        primary_path = _parking_log_path()
    else:
        primary_path = filename

    log_entries = []
    log_path = os.path.join(DATA_DIR, "park-loss.log")

    totals = {}

    def _log_loss(start_ts, end_ts, pct_loss, range_loss, context):
        if pct_loss <= 0 and range_loss <= 0:
            return
        entry = {
            "start": start_ts.isoformat() if isinstance(start_ts, datetime) else None,
            "end": end_ts.isoformat() if isinstance(end_ts, datetime) else None,
            "energy_pct": round(float(pct_loss), 6),
            "range_km": round(float(range_loss), 6),
            "context": context,
        }
        log_entries.append(entry)

    def _add_loss(day, pct_loss, km_loss):
        if pct_loss <= 0 and km_loss <= 0:
            return
        entry = totals.setdefault(day, {"energy_pct": 0.0, "km": 0.0})
        if pct_loss > 0:
            entry["energy_pct"] += pct_loss
        if km_loss > 0:
            entry["km"] += km_loss

    def _distribute_loss(start_ts, end_ts, pct_loss, range_loss, context="parked"):
        if pct_loss <= 0 and range_loss <= 0:
            return
        if start_ts is None and end_ts is None:
            return

        _log_loss(start_ts, end_ts, pct_loss, range_loss, context)

        if start_ts is None:
            _add_loss(end_ts.date().isoformat(), pct_loss, range_loss)
            return

        if end_ts is None or end_ts <= start_ts:
            _add_loss(start_ts.date().isoformat(), pct_loss, range_loss)
            return

        total_seconds = (end_ts - start_ts).total_seconds()
        if total_seconds <= 0:
            _add_loss(start_ts.date().isoformat(), pct_loss, range_loss)
            return

        allocated_pct = 0.0
        allocated_range = 0.0
        cursor = start_ts

        while cursor.date() < end_ts.date():
            next_midnight = datetime.combine(
                cursor.date() + timedelta(days=1),
                datetime.min.time(),
                tzinfo=cursor.tzinfo,
            )
            span = (next_midnight - cursor).total_seconds()
            if span <= 0:
                break
            share = span / total_seconds
            share_pct = pct_loss * share
            share_range = range_loss * share
            _add_loss(cursor.date().isoformat(), share_pct, share_range)
            allocated_pct += share_pct
            allocated_range += share_range
            cursor = next_midnight

        remaining_pct = max(pct_loss - allocated_pct, 0.0)
        remaining_range = max(range_loss - allocated_range, 0.0)
        _add_loss(end_ts.date().isoformat(), remaining_pct, remaining_range)

    processed = False
    base_name = os.path.basename(primary_path) if primary_path else ""

    if base_name != "api.log":
        processed = _process_dashboard_parking_log(primary_path, _distribute_loss)
        base_dir = os.path.dirname(primary_path) or vehicle_dir(vehicle_id)
        fallback_path = resolve_log_path(vehicle_id, "api.log")
    else:
        fallback_path = primary_path

    if not processed:
        processed = _process_legacy_parking_log(
            fallback_path, _distribute_loss, vehicle_id=vehicle_id
        )

    try:
        existing_entries = []
        seen = set()
        with open(log_path, "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                if not isinstance(record, dict):
                    continue
                start = record.get("start")
                end = record.get("end")
                pct_val = _as_float(record.get("energy_pct"))
                rng_val = _as_float(record.get("range_km"))
                context = record.get("context") or "parked"
                key = (
                    start,
                    end,
                    round(pct_val or 0.0, 6),
                    round(rng_val or 0.0, 6),
                    context,
                )
                if key in seen:
                    continue
                seen.add(key)
                existing_entries.append(
                    {
                        "start": start,
                        "end": end,
                        "energy_pct": round(pct_val or 0.0, 6),
                        "range_km": round(rng_val or 0.0, 6),
                        "context": context,
                    }
                )
    except FileNotFoundError:
        existing_entries = []
        seen = set()
    except Exception:
        existing_entries = []
        seen = set()

    new_entries = []
    for entry in log_entries:
        key = (
            entry.get("start"),
            entry.get("end"),
            entry.get("energy_pct", 0.0),
            entry.get("range_km", 0.0),
            entry.get("context", "parked"),
        )
        if key in seen:
            continue
        seen.add(key)
        new_entries.append(entry)

    if new_entries:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as handle:
                for entry in new_entries:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    return totals


def _load_existing_statistics(filename=None):
    """Return previously computed statistics from ``STAT_FILE`` if available."""

    if filename is None:
        filename = STAT_FILE

    try:
        with open(filename, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _merge_parking_value(prev_total, prev_source, new_raw, tolerance=0.01):
    """Combine previously stored parking metrics with a new measurement."""

    def _to_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    prev_total = _to_float(prev_total, 0.0)
    if prev_source is None:
        had_prev_source = False
        prev_source = prev_total
    else:
        had_prev_source = True
        prev_source = _to_float(prev_source, prev_total)
    new_raw = _to_float(new_raw, 0.0)

    if new_raw <= 0.0:
        return prev_total, prev_source

    replaced = False

    if new_raw >= prev_total - tolerance:
        combined = new_raw
        source = new_raw
    elif abs(new_raw - prev_source) <= tolerance:
        combined = prev_total
        source = prev_source
    elif (not had_prev_source) and new_raw < prev_total - tolerance:
        combined = new_raw
        source = new_raw
        replaced = True
    else:
        combined = prev_total + new_raw
        source = new_raw

    if combined < prev_total and not replaced:
        combined = prev_total
    return combined, source


def compute_statistics():
    """Compute daily statistics and save them to ``STAT_FILE``."""
    vid = _default_vehicle_id or default_vehicle_id()
    previous = _load_existing_statistics()
    try:
        entries = _load_state_entries(vehicle_id=vid)
    except TypeError:
        entries = _load_state_entries()
    stats = _compute_state_stats(entries)
    try:
        energy = _compute_energy_stats(vehicle_id=vid)
    except TypeError:
        energy = _compute_energy_stats()
    try:
        parking = _compute_parking_losses(vehicle_id=vid)
    except TypeError:
        parking = _compute_parking_losses()
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
    for day, loss in parking.items():
        stats.setdefault(day, {"online": 0.0, "offline": 0.0, "asleep": 0.0})
        previous_entry = previous.get(day, {})
        prev_pct_total = previous_entry.get("_park_energy_pct_total", previous_entry.get("park_energy_pct", 0.0))
        prev_pct_source = previous_entry.get("_park_energy_pct_source")
        pct_total, pct_source = _merge_parking_value(
            prev_pct_total, prev_pct_source, loss.get("energy_pct", 0.0)
        )
        prev_km_total = previous_entry.get("_park_km_total", previous_entry.get("park_km", 0.0))
        prev_km_source = previous_entry.get("_park_km_source")
        km_total, km_source = _merge_parking_value(
            prev_km_total, prev_km_source, loss.get("km", 0.0)
        )
        stats[day]["park_energy_pct"] = round(pct_total, 2)
        stats[day]["_park_energy_pct_total"] = pct_total
        stats[day]["_park_energy_pct_source"] = pct_source
        stats[day]["park_km"] = round(km_total, 2)
        stats[day]["_park_km_total"] = km_total
        stats[day]["_park_km_source"] = km_source
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
        val.setdefault("park_energy_pct", 0.0)
        val.setdefault("park_km", 0.0)
        if "_park_energy_pct_total" not in val:
            val["_park_energy_pct_total"] = val["park_energy_pct"]
        if "_park_energy_pct_source" not in val:
            val["_park_energy_pct_source"] = val["park_energy_pct"]
        if "_park_km_total" not in val:
            val["_park_km_total"] = val["park_km"]
        if "_park_km_source" not in val:
            val["_park_km_source"] = val["park_km"]

    parking_days = set(parking.keys())
    for day, old in previous.items():
        current = stats.get(day)
        if current is None:
            stats[day] = dict(old)
            continue
        if day not in parking_days:
            for key in (
                "park_energy_pct",
                "park_km",
                "_park_energy_pct_total",
                "_park_energy_pct_source",
                "_park_km_total",
                "_park_km_source",
            ):
                if key in old:
                    current[key] = old[key]
    try:
        os.makedirs(os.path.dirname(STAT_FILE), exist_ok=True)
        with open(STAT_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return stats


def _statistics_dependency_signature():
    """Return a signature describing inputs used for statistics generation."""

    vid = _default_vehicle_id or default_vehicle_id()
    files = [
        resolve_log_path(vid, "state.log"),
        resolve_log_path(vid, "energy.log"),
        resolve_log_path(vid, "api.log"),
    ]
    files.extend(_get_trip_files())

    signature = []
    for path in files:
        try:
            stat = os.stat(path)
        except OSError:
            signature.append((path, None, None))
            continue
        signature.append((path, stat.st_mtime, stat.st_size))
    return tuple(signature)


def _load_cached_statistics():
    """Return statistics stored in the aggregation database."""

    signature = _statistics_dependency_signature()
    with _statistics_cache_lock:
        cached_signature = _statistics_cache.get("signature")

    thread_alive = _aggregation_thread is not None and _aggregation_thread.is_alive()
    if (not thread_alive) or cached_signature != signature:
        _statistics_aggregation_tick()

    try:
        conn = _statistics_conn()
        _ensure_statistics_tables(conn)
        if _get_meta(conn, "statistics_initialized") != "1":
            _statistics_aggregation_tick()
        stats = _load_daily_from_db(conn)
        conn.close()
        with _statistics_cache_lock:
            _statistics_cache["signature"] = signature
            _statistics_cache["data"] = stats
        return stats
    except Exception:
        fallback = compute_statistics()
        with _statistics_cache_lock:
            _statistics_cache["signature"] = signature
            _statistics_cache["data"] = fallback
        return fallback


def _load_monthly_statistics():
    try:
        conn = _statistics_conn()
        _ensure_statistics_tables(conn)
        cur = conn.execute(
            "SELECT date, online, offline, asleep, km, speed, energy, park_energy_pct, park_km FROM statistics_aggregate WHERE scope='monthly'"
        )
        data = {}
        for row in cur.fetchall():
            data[row[0]] = {
                "online": float(row[1] or 0.0),
                "offline": float(row[2] or 0.0),
                "asleep": float(row[3] or 0.0),
                "km": float(row[4] or 0.0),
                "speed": float(row[5] or 0.0),
                "energy": float(row[6] or 0.0),
                "park_energy_pct": float(row[7] or 0.0),
                "park_km": float(row[8] or 0.0),
            }
        conn.close()
        return data
    except Exception:
        return {}


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

    tesla = teslapy.Tesla(email, app_user_agent="Tesla-Dashboard", timeout=TESLA_REQUEST_TIMEOUT)
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
                    "vehicle_list",
                    sanitize([v.copy() for v in _vehicle_list_cache]),
                    vehicle_id=_default_vehicle_id,
                )
                if _vehicle_list_cache and _default_vehicle_id is None:
                    _default_vehicle_id = str(_vehicle_list_cache[0]["id_s"])
            except Exception as exc:
                _log_api_error(exc)
                return []
        return _vehicle_list_cache


def default_vehicle_id():
    """Return the configured vehicle ID or the first available."""
    global _default_vehicle_id
    if _default_vehicle_id is not None:
        return _default_vehicle_id
    cfg = load_config()
    vid = cfg.get("vehicle_id")
    if vid:
        _default_vehicle_id = str(vid)
        return _default_vehicle_id
    tesla = get_tesla()
    if tesla is None:
        return None
    vehicles = _cached_vehicle_list(tesla)
    if vehicles:
        _default_vehicle_id = str(vehicles[0]["id_s"])
        return _default_vehicle_id
    return None


def _refresh_state(vehicle, times=1):
    """Query the vehicle state multiple times and return the last value."""
    state = None
    vid = None
    try:
        vid = vehicle.get("id_s") or vehicle.get("vehicle_id")
    except Exception:
        try:
            vid = vehicle["id_s"]
        except Exception:
            vid = None
    for _ in range(times):
        try:
            vehicle.get_vehicle_summary()
        except Exception as exc:
            _log_api_error(exc)
            break
        state = vehicle.get("state") or vehicle["state"]
        log_vehicle_state(vid, state)
        log_api_data("get_vehicle_summary", {"state": state}, vehicle_id=vid)
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

    vid = None
    try:
        if isinstance(vehicle, dict):
            vid = vehicle.get("id_s") or vehicle.get("vehicle_id")
        else:
            vid = vehicle["id_s"]
    except Exception:
        vid = None
    if vid is None and vehicle_id is not None:
        vid = vehicle_id
    if vid is None and _default_vehicle_id is not None:
        vid = _default_vehicle_id

    if state is None:
        try:
            state = _refresh_state(vehicle)
        except Exception as exc:
            _log_api_error(exc)
            log_vehicle_state(vid, "offline")
            return {"error": "Vehicle unavailable", "state": "offline"}

    if state != "online":
        
        payload = {"state": state}
        if vid is not None:
            payload["id_s"] = str(vid)

        log_api_data("get_vehicle_data", payload, vehicle_id=vid)
        return payload

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
    log_api_data("get_vehicle_data", sanitized, vehicle_id=vid)
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
        charging_state = charge.get("charging_state")
        saved_val = last_val
        now = datetime.now(LOCAL_TZ)

        session_start = _charging_session_start.get(cache_id)
        if session_start is None:
            session_start = _load_session_start(cache_id)

        if charging_state == "Charging" and session_start is None:
            session_start = now
            _save_session_start(cache_id, session_start)

        if val is not None:
            if last_val is not None and val < last_val:
                # Finish previous session before counter resets
                prev_start = session_start or _load_session_start(cache_id)
                if last_val > 0:
                    logged = _log_energy(cache_id, last_val, timestamp=prev_start)
                    if logged:
                        _save_last_energy(cache_id, last_val)
                        saved_val = last_val
                _clear_session_start(cache_id)
                session_start = None
                if charging_state == "Charging":
                    session_start = now
                    _save_session_start(cache_id, session_start)
            last_val = val

        value_to_log = None
        if charging_state in ("Complete", "Disconnected"):
            if val is not None and val > 0:
                value_to_log = val
            elif val is None and last_val is not None and last_val > 0:
                value_to_log = last_val
        if value_to_log is not None:
            start_time = session_start or _load_session_start(cache_id)
            should_log = True
            if start_time is None:
                try:
                    prev_amount = float(saved_val)
                except (TypeError, ValueError):
                    prev_amount = None
                except Exception:
                    prev_amount = None
                try:
                    current_amount = float(value_to_log)
                except (TypeError, ValueError):
                    current_amount = None
                except Exception:
                    current_amount = None
                if (
                    prev_amount is not None
                    and current_amount is not None
                    and abs(current_amount - prev_amount) <= 0.001
                ):
                    should_log = False

            if should_log:
                logged = _log_energy(cache_id, value_to_log, timestamp=start_time)
            else:
                logged = False
            _clear_session_start(cache_id)
            if logged:
                _save_last_energy(cache_id, value_to_log)
                saved_val = value_to_log
            session_start = None

        if (
            charging_state == "Charging"
            and session_start is None
            and (val is None or val >= 0)
        ):
            session_start = now
            _save_session_start(cache_id, session_start)

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
        vehicle_identifier = (
            data.get("id_s")
            or data.get("vehicle_id")
            or vid
            or cache_id
            or "default"
        )
        try:
            _record_dashboard_parking_state(str(vehicle_identifier), data)
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
            gear_active = _normalize_shift_state(d_state.get("shift_state")) in {"R", "N", "D"}
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
        socketio_client_script=socketio_client_script(),
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
        raw_heading = None
        if len(first) >= 6 and first[5] is not None:
            raw_heading = first[5]
        elif len(path) >= 2:
            raw_heading = _bearing(path[0][:2], path[1][:2])
        if raw_heading is None:
            raw_heading = 0.0
        try:
            heading = float(raw_heading)
        except (TypeError, ValueError):
            heading = 0.0
        gear = _normalize_shift_state(first[6]) if len(first) >= 7 else None
        heading = heading % 360.0
        if gear == "R":
            heading = (heading + 180.0) % 360.0
    weekly, monthly = compute_trip_summaries()
    cfg = load_config()
    response = make_response(
        render_template(
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
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


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
    ip = _client_ip()

    def gen():
        q = queue.Queue()
        subscribers.setdefault(vehicle_id, []).append(q)
        last_path_len = 0
        try:
            # Send the latest data immediately if available
            if vehicle_id in latest_data:
                initial = latest_data[vehicle_id]
                if isinstance(initial, dict):
                    path = initial.get("path")
                    if isinstance(path, list):
                        last_path_len = len(path)
                yield f"data: {json.dumps(initial)}\n\n"
            while True:
                try:
                    data = q.get(timeout=15)
                    payload = data
                    if isinstance(data, dict):
                        payload = dict(data)
                        path = payload.get("path")
                        if isinstance(path, list):
                            previous_len = last_path_len
                            path_len = len(path)
                            path_reset = path_len < previous_len
                            if path_reset:
                                payload["path_reset"] = True
                                previous_len = 0
                            delta = path[previous_len:path_len]
                            if path_reset:
                                # When the path resets we send the full path once
                                payload["path"] = path
                            elif delta:
                                payload.pop("path", None)
                            else:
                                payload.pop("path", None)
                            if delta:
                                payload["path_delta"] = delta
                            last_path_len = path_len
                        else:
                            payload.pop("path", None)
                            last_path_len = 0
                    msg = f"data: {json.dumps(payload)}\n\n"
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
            info = active_clients.get(ip)
            if info:
                info["connections"] = info.get("connections", 1) - 1
                if info["connections"] <= 0:
                    active_clients.pop(ip, None)

    resp = Response(gen(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


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


@app.route("/api/clients/details")
def api_client_details():
    """Return detailed information about connected clients."""
    now = time.time()
    items = []
    expired = []
    for ip, data in list(active_clients.items()):
        last_seen = data.get("last_seen", now)
        pages = data.get("pages", [])
        if now - last_seen > CLIENT_TIMEOUT or not pages:
            expired.append(ip)
            continue
        delta = now - data.get("first_seen", now)
        days = int(delta // 86400)
        hms = time.strftime("%H:%M:%S", time.gmtime(delta % 86400))
        items.append(
            {
                "ip": data.get("ip"),
                "hostname": data.get("hostname"),
                "location": data.get("location"),
                "provider": data.get("provider"),
                "browser": data.get("browser"),
                "os": data.get("os"),
                "user_agent": data.get("user_agent"),
                # Return list of visited pages so clients can format them
                "pages": pages,
                "duration": f"{days:02d} Tage, {hms}",
            }
        )
    for ip in expired:
        active_clients.pop(ip, None)
    items.sort(key=lambda d: d["ip"] or "")
    return jsonify({"clients": items})


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


@csrf.exempt
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


@csrf.exempt
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
        _log_sms(message, success, vehicle_id=_default_vehicle_id)
        if success:
            return jsonify({"success": True})
        try:
            error = resp.json().get("requestError", {}).get("serviceException", {}).get("text")
        except Exception:
            error = resp.text
        return jsonify({"success": False, "error": error})
    except Exception as exc:
        _log_sms(message, False, vehicle_id=_default_vehicle_id)
        return jsonify({"success": False, "error": str(exc)})


@app.route("/config", methods=["GET", "POST"])
@requires_auth
def config_page():
    global _default_vehicle_id
    cfg = load_config()
    vehicles = get_vehicle_list()
    selected_vehicle_id = cfg.get("vehicle_id") or (vehicles[0]["id"] if vehicles else None)
    if request.method == "POST":
        for item in CONFIG_ITEMS:
            cfg[item["id"]] = item["id"] in request.form
        callsign = request.form.get("aprs_callsign", "").strip()
        passcode = request.form.get("aprs_passcode", "").strip()
        keep_passcode = passcode == SECRET_PLACEHOLDER
        if keep_passcode:
            passcode = ""
        wx_callsign = request.form.get("aprs_wx_callsign", "").strip()
        wx_enabled = "aprs_wx_enabled" in request.form
        aprs_comment = request.form.get("aprs_comment", "").strip()
        announcement = request.form.get("announcement", "").strip()
        blocked_ips = request.form.get("blocked_ips", "").strip()
        taxi_company = request.form.get("taxi_company", "").strip()
        taxi_slogan = request.form.get("taxi_slogan", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        if phone_number:
            phone_number = _format_phone(phone_number) or phone_number
        infobip_api_key = request.form.get("infobip_api_key", "").strip()
        keep_infobip_api_key = infobip_api_key == SECRET_PLACEHOLDER
        if keep_infobip_api_key:
            infobip_api_key = ""
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
        selected_vehicle = request.form.get("vehicle_id", "").strip()
        if selected_vehicle:
            selected_vehicle_id = selected_vehicle
        aprs_cfg = load_config(vehicle_id=selected_vehicle_id)
        if "refresh_vehicle_list" in request.form:
            tesla = get_tesla()
            if tesla is not None:
                _cached_vehicle_list(tesla, ttl=0)
                vehicles = get_vehicle_list()
        if callsign:
            aprs_cfg["aprs_callsign"] = callsign
        elif "aprs_callsign" in aprs_cfg:
            aprs_cfg.pop("aprs_callsign")
        existing_passcode = aprs_cfg.get("aprs_passcode") or cfg.get("aprs_passcode")
        if passcode:
            aprs_cfg["aprs_passcode"] = passcode
        elif keep_passcode and existing_passcode:
            aprs_cfg["aprs_passcode"] = existing_passcode
        elif not keep_passcode and "aprs_passcode" in aprs_cfg:
            aprs_cfg.pop("aprs_passcode")
        if wx_callsign:
            aprs_cfg["aprs_wx_callsign"] = wx_callsign
        elif "aprs_wx_callsign" in aprs_cfg:
            aprs_cfg.pop("aprs_wx_callsign")
        aprs_cfg["aprs_wx_enabled"] = wx_enabled
        if aprs_comment:
            aprs_cfg["aprs_comment"] = aprs_comment
        elif "aprs_comment" in aprs_cfg:
            aprs_cfg.pop("aprs_comment")
        if announcement:
            cfg["announcement"] = announcement
        elif "announcement" in cfg:
            cfg.pop("announcement")
        if blocked_ips:
            cfg["blocked_ips"] = ",".join(
                ip.strip() for ip in blocked_ips.split(",") if ip.strip()
            )
        elif "blocked_ips" in cfg:
            cfg.pop("blocked_ips")
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
        elif not keep_infobip_api_key and "infobip_api_key" in cfg:
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
        if selected_vehicle:
            cfg["vehicle_id"] = selected_vehicle
            _default_vehicle_id = selected_vehicle
        elif "vehicle_id" in cfg:
            cfg.pop("vehicle_id")
            _default_vehicle_id = None

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
        save_config(aprs_cfg, vehicle_id=selected_vehicle_id)
    else:
        aprs_cfg = load_config(vehicle_id=selected_vehicle_id)
    display_cfg = dict(cfg)
    for key in ("aprs_callsign", "aprs_passcode", "aprs_wx_callsign", "aprs_wx_enabled", "aprs_comment"):
        if key in aprs_cfg:
            display_cfg[key] = aprs_cfg[key]
    if display_cfg.get("aprs_passcode"):
        display_cfg["aprs_passcode"] = SECRET_PLACEHOLDER
    if display_cfg.get("infobip_api_key"):
        display_cfg["infobip_api_key"] = SECRET_PLACEHOLDER
    return render_template(
        "config.html",
        items=CONFIG_ITEMS,
        config=display_cfg,
        vehicles=vehicles,
        selected_vehicle_id=selected_vehicle_id,
    )


@app.route("/images/<path:filename>")
def images(filename):
    return send_from_directory(
        os.path.join(app.root_path, "static", "images"), filename
    )


@app.route("/blocked")
def blocked():
    return render_template("blocked.html"), 403


@app.errorhandler(404)
def handle_404(_):
    """Display blocked page for unknown routes."""
    return render_template("blocked.html"), 404


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


def _prepare_statistics_payload():
    """Build the statistics payload used by both HTML and JSON views."""
    stats = _load_cached_statistics()
    monthly_data = _load_monthly_statistics()
    current_month = datetime.now(LOCAL_TZ).strftime("%Y-%m")
    rows = []
    current = {
        "online_sum": 0.0,
        "offline_sum": 0.0,
        "asleep_sum": 0.0,
        "km": 0.0,
        "speed": 0.0,
        "energy": 0.0,
        "park_energy_pct": 0.0,
        "park_km": 0.0,
        "count": 0,
    }
    for day in sorted(stats.keys()):
        entry = stats[day]
        if day.startswith(current_month):
            row = {
                "date": day,
                "online": round(entry.get("online", 0.0), 2),
                "offline": round(entry.get("offline", 0.0), 2),
                "asleep": round(entry.get("asleep", 0.0), 2),
                "km": round(entry.get("km", 0.0), 2),
                "speed": int(round(entry.get("speed", 0.0))),
                "energy": round(entry.get("energy", 0.0), 2),
                "park_energy_pct": round(entry.get("park_energy_pct", 0.0), 2),
                "park_km": round(entry.get("park_km", 0.0), 2),
            }
            total = row["online"] + row["offline"] + row["asleep"]
            diff = round(100.0 - total, 2)
            row["offline"] = round(row["offline"] + diff, 2)
            rows.append(row)
            current["online_sum"] += entry.get("online", 0.0)
            current["offline_sum"] += entry.get("offline", 0.0)
            current["asleep_sum"] += entry.get("asleep", 0.0)
            current["km"] += entry.get("km", 0.0)
            current["energy"] += entry.get("energy", 0.0)
            current["park_energy_pct"] += entry.get("park_energy_pct", 0.0)
            current["park_km"] += entry.get("park_km", 0.0)
            current["speed"] = max(current["speed"], entry.get("speed", 0.0))
            current["count"] += 1

    monthly_rows = []
    for month in sorted(monthly_data.keys()):
        data = monthly_data[month]
        row = {
            "date": month,
            "online": round(data.get("online", 0.0), 2),
            "offline": round(data.get("offline", 0.0), 2),
            "asleep": round(data.get("asleep", 0.0), 2),
            "km": round(data.get("km", 0.0), 2),
            "speed": int(round(data.get("speed", 0.0))),
            "energy": round(data.get("energy", 0.0), 2),
            "park_energy_pct": round(data.get("park_energy_pct", 0.0), 2),
            "park_km": round(data.get("park_km", 0.0), 2),
        }
        total = row["online"] + row["offline"] + row["asleep"]
        diff = round(100.0 - total, 2)
        row["offline"] = round(row["offline"] + diff, 2)
        monthly_rows.append(row)

    rows = monthly_rows + rows

    summary = None
    if current["count"]:
        cnt = current["count"]
        summary = {
            "date": current_month,
            "online": round(current["online_sum"] / cnt, 2),
            "offline": round(current["offline_sum"] / cnt, 2),
            "asleep": round(current["asleep_sum"] / cnt, 2),
            "km": round(current["km"], 2),
            "speed": int(round(current["speed"])),
            "energy": round(current["energy"], 2),
            "park_energy_pct": round(current["park_energy_pct"], 2),
            "park_km": round(current["park_km"], 2),
        }
        total = summary["online"] + summary["offline"] + summary["asleep"]
        diff = round(100.0 - total, 2)
        summary["offline"] = round(summary["offline"] + diff, 2)
    # highlight today's statistics and current vehicle state
    today = datetime.now(LOCAL_TZ).date().isoformat()
    vid = str(_default_vehicle_id or "default")
    state = last_vehicle_state.get(vid)
    if state is None and last_vehicle_state:
        # fall back to any known state if default ID is missing
        state = next(iter(last_vehicle_state.values()))

    return {
        "rows": rows,
        "summary": summary,
        "today": today,
        "current_state": state,
    }


@app.route("/statistik")
def statistics_page():
    """Display statistics of vehicle state and distance."""
    payload = _prepare_statistics_payload()
    cfg = load_config()
    return render_template("statistik.html", config=cfg, **payload)


@app.route("/api/statistik")
def api_statistics():
    """Provide statistics data as JSON for live updates."""
    payload = _prepare_statistics_payload()
    return jsonify(payload)


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
    vehicle_id = request.args.get("vehicle_id") or _default_vehicle_id or default_vehicle_id()
    log_lines = []
    try:
        path = resolve_log_path(vehicle_id, "state.log")
        with open(path, "r", encoding="utf-8") as f:
            log_lines = f.readlines()
    except Exception:
        pass
    return render_template("state.html", log_lines=log_lines)


@app.route("/apilog")
def api_log_page():
    """Display the API log."""
    vehicle_id = request.args.get("vehicle_id") or _default_vehicle_id or default_vehicle_id()
    log_lines = []
    try:
        path = resolve_log_path(vehicle_id, "api.log")
        with open(path, "r", encoding="utf-8") as f:
            log_lines = f.readlines()
    except Exception:
        pass
    return render_template("apilog.html", log_lines=log_lines)


@app.route("/sms")
def sms_log_page():
    """Display the SMS log."""
    vehicle_id = request.args.get("vehicle_id") or _default_vehicle_id or default_vehicle_id()
    log_lines = []
    try:
        path = resolve_log_path(vehicle_id, "sms.log")
        with open(path, "r", encoding="utf-8") as f:
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


@csrf.exempt
@app.route("/api/taxameter/start", methods=["POST"])
def api_taxameter_start():
    vid = request.form.get("vehicle_id") or default_vehicle_id()
    taximeter.vehicle_id = vid
    _start_thread(vid)
    taximeter.start()
    return jsonify(taximeter.status())


@csrf.exempt
@app.route("/api/taxameter/pause", methods=["POST"])
def api_taxameter_pause():
    vid = request.form.get("vehicle_id")
    if vid:
        taximeter.vehicle_id = vid
    taximeter.pause()
    return jsonify(taximeter.status())


@csrf.exempt
@app.route("/api/taxameter/stop", methods=["POST"])
def api_taxameter_stop():
    vid = request.form.get("vehicle_id")
    if vid:
        taximeter.vehicle_id = vid
    result = taximeter.stop()
    if result:
        company = get_taxi_company()
        slogan = get_taxi_slogan()
        printed_at = datetime.now(LOCAL_TZ).strftime(RECEIPT_TIME_FORMAT)
        text = format_receipt(
            company,
            result.get("breakdown", {}),
            result.get("distance", 0.0),
            slogan,
            printed_at=printed_at,
        )
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
                        "printed_at": printed_at,
                    },
                    f,
                )
            url = url_for("taxameter_receipt", ride_id=ride_id, _external=True)
            img = qrcode.make(url)
            img_path = os.path.join(rdir, f"{ride_id}.png")
            img.save(img_path)
            result["qr_code"] = f"/receipts/{ride_id}.png"
            result["receipt_url"] = url
        result["printed_at"] = printed_at
        result["company"] = company
        result["slogan"] = slogan
    return jsonify(result or {"active": False})


@csrf.exempt
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
            data.setdefault("printed_at", datetime.now(LOCAL_TZ).strftime(RECEIPT_TIME_FORMAT))
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
    printed_at = datetime.now(LOCAL_TZ).strftime(RECEIPT_TIME_FORMAT)
    return render_template(
        "taxameter_receipt.html",
        company=company,
        slogan=slogan,
        breakdown=breakdown,
        distance=dist,
        qr_code=None,
        printed_at=printed_at,
    )


@app.route("/receipts/<path:filename>")
def receipts_file(filename):
    return send_from_directory(receipt_dir(), filename)


@app.route("/clients")
def clients_view():
    """Show currently connected clients."""
    now = time.time()
    items = []
    expired = []
    for ip, data in list(active_clients.items()):
        last_seen = data.get("last_seen", now)
        pages = data.get("pages", [])
        if now - last_seen > CLIENT_TIMEOUT or not pages:
            expired.append(ip)
            continue
        delta = now - data.get("first_seen", now)
        days = int(delta // 86400)
        hms = time.strftime("%H:%M:%S", time.gmtime(delta % 86400))
        items.append(
            {
                "ip": data.get("ip"),
                "hostname": data.get("hostname"),
                "location": data.get("location"),
                "provider": data.get("provider"),
                "browser": data.get("browser"),
                "os": data.get("os"),
                "user_agent": data.get("user_agent"),
                "pages": pages,
                "duration": f"{days:02d} Tage, {hms}",
            }
        )
    for ip in expired:
        active_clients.pop(ip, None)
    items.sort(key=lambda d: d["ip"] or "")
    return render_template("clients.html", clients=items)


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
        path = resolve_log_path(_default_vehicle_id or default_vehicle_id(), "api.log")
        with open(path, "r", encoding="utf-8") as f:
            log_lines = f.readlines()[-50:]
    except Exception:
        pass

    return render_template(
        "debug.html", env_info=env_info, log_lines=log_lines, latest=latest_data
    )


# Socket.IO handlers for push-to-talk audio


def _client_id():
    """Return a stable client identifier for the current connection."""

    cid = request.cookies.get("client_id")
    if cid:
        return cid
    # ``SocketIOTestClient`` and some real-time connections may not trigger the
    # Flask ``before_request`` handlers that set the ``client_id`` cookie.  Fall
    # back to the Socket.IO session id so that every connection gets a unique
    # identifier and cannot unintentionally acquire the push-to-talk lock of
    # another client.
    return request.sid


def _flush_audio_buffer():
    """Send and clear buffered audio if available."""
    global audio_buffer
    if not is_ptt_enabled():
        audio_buffer.clear()
        return
    if audio_buffer:
        socketio.emit("play_audio", bytes(audio_buffer), include_self=False)
        audio_buffer.clear()


def _release_ptt(expected_id):
    """Release the PTT lock if still held by ``expected_id``."""
    global current_speaker_id, ptt_timer, audio_buffer
    if current_speaker_id == expected_id:
        _flush_audio_buffer()
        current_speaker_id = None
        socketio.emit("unlock_ptt", broadcast=True)
    ptt_timer = None


@socketio.on("connect")
def handle_connect():
    cid = _client_id()
    emit("your_id", {"id": cid})


@socketio.on("start_speaking")
def start_speaking():
    """Allow a client to speak if no other client is active."""
    global current_speaker_id, ptt_timer, audio_buffer
    cid = _client_id()
    sid = request.sid
    if not is_ptt_enabled():
        emit("start_denied", room=sid)
        return
    if current_speaker_id is None:
        current_speaker_id = cid
        audio_buffer.clear()
        emit("start_accepted", room=sid)
        emit("lock_ptt", {"speaker": cid}, broadcast=True, include_self=False)
        if ptt_timer:
            ptt_timer.cancel()
        ptt_timer = threading.Timer(30, _release_ptt, args=[cid])
        ptt_timer.start()
    elif current_speaker_id == cid:
        emit("start_accepted", room=sid)
    else:
        emit("start_denied", room=sid)


@socketio.on("stop_speaking")
def stop_speaking():
    """Release the PTT lock when a client stops speaking."""
    global current_speaker_id, ptt_timer
    if not is_ptt_enabled():
        if current_speaker_id is not None:
            _flush_audio_buffer()
            current_speaker_id = None
            if ptt_timer:
                ptt_timer.cancel()
                ptt_timer = None
        return
    if _client_id() == current_speaker_id:
        _flush_audio_buffer()
        current_speaker_id = None
        emit("unlock_ptt", broadcast=True)
        if ptt_timer:
            ptt_timer.cancel()
            ptt_timer = None


@socketio.on("audio_chunk")
def handle_audio_chunk(data):
    """Forward audio data from the active speaker to all listeners."""
    if not is_ptt_enabled():
        return
    if _client_id() == current_speaker_id:
        global audio_buffer
        try:
            raw = bytes(data)
        except Exception:
            app.logger.warning("Invalid audio chunk received: %r", type(data))
            return
        if raw:
            audio_buffer.extend(raw)
        else:
            app.logger.warning("Empty audio chunk received")


@socketio.on("disconnect")
def handle_disconnect():
    """Ensure lock is released if the speaker disconnects."""
    global current_speaker_id, ptt_timer
    if not is_ptt_enabled():
        if current_speaker_id is not None:
            _flush_audio_buffer()
            current_speaker_id = None
            if ptt_timer:
                ptt_timer.cancel()
                ptt_timer = None
        return
    if _client_id() == current_speaker_id:
        _flush_audio_buffer()
        current_speaker_id = None
        emit("unlock_ptt", broadcast=True)
        if ptt_timer:
            ptt_timer.cancel()
            ptt_timer = None


# When embedded in another process (e.g., WSGI), start aggregation immediately
# and force a full rebuild so caches and offsets are refreshed on boot.
if __name__ != "__main__":
    _force_statistics_rebuild_on_start()
    _start_statistics_aggregation(AGGREGATION_INTERVAL)


if __name__ == "__main__":
    _parse_cli_arguments()
    _force_statistics_rebuild_on_start()
    _start_statistics_aggregation(AGGREGATION_INTERVAL)
    socketio.run(app, host="0.0.0.0", port=8013, debug=True)
