import os
import json
import queue
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, jsonify, Response, request
from dotenv import load_dotenv
from version import get_version
from datetime import datetime

try:
    import teslapy
except ImportError:
    teslapy = None

load_dotenv()
app = Flask(__name__)
__version__ = get_version()
CURRENT_YEAR = datetime.now().year

# Ensure data paths are relative to this file regardless of the
# current working directory.  This allows running the application
# from any location while still finding the trip files and caches.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)
api_logger = logging.getLogger('api_logger')
if not api_logger.handlers:
    handler = RotatingFileHandler(
        os.path.join(DATA_DIR, 'api.log'), maxBytes=1_000_000, backupCount=1)
    formatter = logging.Formatter('%(asctime)s %(message)s')
    handler.setFormatter(formatter)
    api_logger.addHandler(handler)
    api_logger.setLevel(logging.INFO)
    # Forward detailed library logs to the same file
    for name in ('teslapy', 'urllib3'):
        lib_logger = logging.getLogger(name)
        lib_logger.addHandler(handler)
        lib_logger.setLevel(logging.DEBUG)
    try:
        import http.client as http_client
        http_client.HTTPConnection.debuglevel = 1
    except Exception:
        pass


# Tools to build an aggregated list of API keys ------------------------------

def _collect_keys(data, prefix='', keys=None):
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


def _collect_key_values(data, prefix='', result=None):
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


def _update_api_json(data, filename=os.path.join(DATA_DIR, 'api-liste.json')):
    """Update ``api-liste.json`` while preserving existing keys."""
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                try:
                    current = json.load(f)
                except Exception:
                    current = {}
        else:
            current = {}

        merged = _merge_data(current, data)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def update_api_list(data, filename=os.path.join(DATA_DIR, 'api-liste.txt')):
    """Update ``api-liste.txt`` with key/value pairs in API order."""
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        existing_lines = []
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.rstrip('\n')
                    if ': ' in line:
                        k, v = line.split(': ', 1)
                    else:
                        k, v = line, ''
                    existing_lines.append((k, v))

        existing_map = {k: i for i, (k, _v) in enumerate(existing_lines)}
        kv = _collect_key_values(data)

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

        content = '\n'.join(f"{k}: {v}" for k, v in lines) + '\n'

        current = ''
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                current = f.read()

        if content != current:
            with open(filename, 'w', encoding='utf-8') as f:
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
        api_logger.info(json.dumps({'endpoint': endpoint, 'data': data}))
        update_api_list(data)
    except Exception:
        pass


TRIP_DIR = os.path.join(DATA_DIR, 'trips')

park_start_ms = None
last_shift_state = None
trip_path = []
current_trip_file = None
latest_data = {}
subscribers = {}
threads = {}
_vehicle_list_cache = []
_vehicle_list_cache_ts = 0.0
_vehicle_list_lock = threading.Lock()
api_errors = []
api_errors_lock = threading.Lock()


def track_park_time(vehicle_data):
    """Track when the vehicle was first seen parked."""
    global park_start_ms, last_shift_state
    drive = vehicle_data.get('drive_state', {}) if isinstance(vehicle_data, dict) else {}
    shift = drive.get('shift_state')
    ts = drive.get('timestamp') or drive.get('gps_as_of')
    if ts and ts < 1e12:
        ts = int(ts * 1000)
    if shift in (None, 'P'):
        if park_start_ms is None or last_shift_state not in (None, 'P'):
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
    return ' '.join(parts)


def _log_trip_point(ts, lat, lon, filename=None):
    """Append a GPS point to a trip history CSV."""
    if filename is None:
        filename = os.path.join(DATA_DIR, 'trip_history.csv')
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"{ts},{lat},{lon}\n")
    except Exception:
        pass


def track_drive_path(vehicle_data):
    """Maintain the current trip path and log points when driving."""
    global trip_path, current_trip_file
    drive = vehicle_data.get('drive_state', {}) if isinstance(vehicle_data, dict) else {}
    shift = drive.get('shift_state')
    lat = drive.get('latitude')
    lon = drive.get('longitude')
    ts = drive.get('timestamp') or drive.get('gps_as_of')
    if ts and ts < 1e12:
        ts = int(ts * 1000)
    if shift in (None, 'P'):
        trip_path = []
        current_trip_file = None
        return
    if lat is not None and lon is not None:
        if current_trip_file is None:
            if ts is None:
                ts = int(time.time() * 1000)
            timestr = time.strftime('%Y%m%d_%H%M%S', time.localtime(ts / 1000))
            current_trip_file = os.path.join(TRIP_DIR, f'trip_{timestr}.csv')
        point = [lat, lon]
        if not trip_path or trip_path[-1] != point:
            trip_path.append(point)
            if ts is not None:
                _log_trip_point(ts, lat, lon, current_trip_file)


def _log_api_error(exc):
    """Store API error messages with timestamp for later retrieval."""
    ts = time.time()
    msg = str(exc)
    with api_errors_lock:
        api_errors.append({'timestamp': ts, 'message': msg})
        if len(api_errors) > 50:
            api_errors.pop(0)


def _cache_file(vehicle_id):
    """Return filename for cached data of a vehicle."""
    name = vehicle_id if vehicle_id is not None else 'default'
    return os.path.join(DATA_DIR, f'cache_{name}.json')


def _load_cached(vehicle_id):
    """Load cached vehicle data from disk."""
    try:
        with open(_cache_file(vehicle_id), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _save_cached(vehicle_id, data):
    """Write vehicle data cache to disk."""
    try:
        with open(_cache_file(vehicle_id), 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        pass


def _get_trip_files(directory=TRIP_DIR):
    """Return a list of available trip CSV files sorted chronologically."""
    try:
        os.makedirs(directory, exist_ok=True)
        files = [f for f in os.listdir(directory) if f.endswith('.csv')]
        files.sort()
        return files
    except Exception:
        return []


def _load_trip(filename):
    """Load all coordinates from a trip history CSV."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            rows = [line.strip().split(',') for line in f if line.strip()]
            rows = [(float(lat), float(lon)) for _t, lat, lon in rows]
        return [[lat, lon] for lat, lon in rows]
    except Exception:
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
            tesla.sso_token = {"access_token": access_token, "refresh_token": refresh_token}
            tesla.refresh_token()
        elif access_token:
            tesla.refresh_token({'access_token': access_token})
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
    global _vehicle_list_cache, _vehicle_list_cache_ts
    now = time.time()
    with _vehicle_list_lock:
        if not _vehicle_list_cache or now - _vehicle_list_cache_ts > ttl:
            try:
                _vehicle_list_cache = tesla.vehicle_list()
                _vehicle_list_cache_ts = now
                log_api_data('vehicle_list', sanitize([v.copy() for v in _vehicle_list_cache]))
            except Exception as exc:
                _log_api_error(exc)
                return []
        return _vehicle_list_cache


def get_vehicle_data(vehicle_id=None):
    """Fetch vehicle data for a given vehicle id."""
    tesla = get_tesla()
    if tesla is None:
        return {"error": "Missing Tesla credentials or teslapy not installed"}

    vehicles = _cached_vehicle_list(tesla)
    if not vehicles:
        return {"error": "No vehicles found"}

    vehicle = None
    if vehicle_id is not None:
        vehicle = next((v for v in vehicles if str(v['id_s']) == str(vehicle_id)), None)
    if vehicle is None:
        vehicle = vehicles[0]

    try:
        vehicle_data = vehicle.get_vehicle_data()
    except Exception as exc:  # vehicle may be asleep/offline
        status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
        if status_code == 408:
            try:
                # wake the vehicle and retry once
                if hasattr(vehicle, 'sync_wake_up'):
                    vehicle.sync_wake_up()
                vehicle_data = vehicle.get_vehicle_data()
            except Exception as exc2:
                _log_api_error(exc2)
                return {"error": "Vehicle is offline or asleep"}
        else:
            _log_api_error(exc)
            return {"error": str(exc)}
    track_park_time(vehicle_data)
    track_drive_path(vehicle_data)
    sanitized = sanitize(vehicle_data)
    log_api_data('get_vehicle_data', sanitized)
    sanitized['park_start'] = park_start_ms
    sanitized['path'] = trip_path
    return sanitized


def get_vehicle_list():
    """Return a list of available vehicles without exposing VIN."""
    tesla = get_tesla()
    if tesla is None:
        return []
    vehicles = _cached_vehicle_list(tesla)
    sanitized = []
    for idx, v in enumerate(vehicles, start=1):
        name = v.get('display_name')
        if not name:
            name = f"Fahrzeug {idx}"
        sanitized.append({"id": v['id_s'], "display_name": name})
    return sanitized


def _fetch_loop(vehicle_id, interval=3):
    """Continuously fetch data for a vehicle and notify subscribers."""
    while True:
        vid = None if vehicle_id == 'default' else vehicle_id
        data = get_vehicle_data(vid)
        if isinstance(data, dict) and not data.get('error'):
            _save_cached(vehicle_id, data)
        else:
            cached = _load_cached(vehicle_id)
            if cached is not None:
                data = cached
        latest_data[vehicle_id] = data
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


@app.route('/')
def index():
    return render_template('index.html', version=__version__, year=CURRENT_YEAR)


@app.route('/map')
def map_only():
    """Display only the map without additional modules."""
    return render_template('map.html', version=__version__)


@app.route('/history')
def trip_history():
    """Show recorded trips and allow selecting a trip to display."""
    files = _get_trip_files()
    selected = request.args.get('file')
    if selected not in files and files:
        selected = files[-1]
    path = _load_trip(os.path.join(TRIP_DIR, selected)) if selected else []
    heading = 0.0
    if len(path) >= 2:
        heading = _bearing(path[-2], path[-1])
    return render_template('history.html', path=path, heading=heading,
                           files=files, selected=selected)


@app.route('/daten')
def data_only():
    """Display live or cached vehicle data without extra UI."""
    _start_thread('default')
    data = latest_data.get('default')
    if data is None:
        data = get_vehicle_data()
        if isinstance(data, dict) and not data.get('error'):
            _save_cached('default', data)
        else:
            cached = _load_cached('default')
            if cached is not None:
                data = cached
        latest_data['default'] = data
    return render_template('data.html', data=data)


@app.route('/api/data')
def api_data():
    _start_thread('default')
    data = latest_data.get('default')
    if data is None:
        data = get_vehicle_data()
        if isinstance(data, dict) and not data.get('error'):
            _save_cached('default', data)
        else:
            cached = _load_cached('default')
            if cached is not None:
                data = cached
        latest_data['default'] = data
    return jsonify(data)


@app.route('/api/data/<vehicle_id>')
def api_data_vehicle(vehicle_id):
    _start_thread(vehicle_id)
    data = latest_data.get(vehicle_id)
    if data is None:
        data = get_vehicle_data(vehicle_id)
        if isinstance(data, dict) and not data.get('error'):
            _save_cached(vehicle_id, data)
        else:
            cached = _load_cached(vehicle_id)
            if cached is not None:
                data = cached
        latest_data[vehicle_id] = data
    return jsonify(data)


@app.route('/stream')
@app.route('/stream/<vehicle_id>')
def stream_vehicle(vehicle_id='default'):
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

    return Response(gen(), mimetype='text/event-stream')


@app.route('/api/vehicles')
def api_vehicles():
    vehicles = get_vehicle_list()
    return jsonify(vehicles)


@app.route('/api/version')
def api_version():
    """Return the current application version."""
    return jsonify({'version': __version__})


@app.route('/error')
def error_page():
    """Display collected API errors."""
    with api_errors_lock:
        errors = list(api_errors)
    for e in errors:
        try:
            e['time_str'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(e['timestamp']))
        except Exception:
            e['time_str'] = str(e['timestamp'])
    return render_template('errors.html', errors=errors)


@app.route('/api/errors')
def api_errors_route():
    """Return collected API errors as JSON."""
    with api_errors_lock:
        return jsonify(list(api_errors))


@app.route('/apiliste')
def api_list_file():
    """Return the aggregated API key list as plain text."""
    try:
        with open(os.path.join(DATA_DIR, 'api-liste.txt'), 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        content = ''
    return Response(content, mimetype='text/plain')


@app.route('/debug')
def debug_info():
    """Display diagnostic information about the server."""
    env_info = {
        'teslapy_available': teslapy is not None,
        'has_email': bool(os.getenv('TESLA_EMAIL')),
        'has_password': bool(os.getenv('TESLA_PASSWORD')),
        'has_access_token': bool(os.getenv('TESLA_ACCESS_TOKEN')),
        'has_refresh_token': bool(os.getenv('TESLA_REFRESH_TOKEN')),
    }

    log_lines = []
    try:
        with open(os.path.join(DATA_DIR, 'api.log'), 'r', encoding='utf-8') as f:
            log_lines = f.readlines()[-50:]
    except Exception:
        pass

    return render_template('debug.html', env_info=env_info, log_lines=log_lines,
                          latest=latest_data)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8013, debug=True)
