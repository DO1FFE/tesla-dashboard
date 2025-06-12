import os
import json
import queue
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, jsonify, Response, request
from dotenv import load_dotenv

try:
    import teslapy
except ImportError:
    teslapy = None

load_dotenv()
app = Flask(__name__)

os.makedirs('data', exist_ok=True)
api_logger = logging.getLogger('api_logger')
if not api_logger.handlers:
    handler = RotatingFileHandler(os.path.join('data', 'api.log'),
                                  maxBytes=1_000_000, backupCount=1)
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


# Communication with the Tesla API is logged via ``log_api_data`` and the
# ``teslapy``/``urllib3`` loggers. Requests to this web application are no longer
# recorded in ``api.log``.


def log_api_data(endpoint, data):
    """Write API communication to the rotating log file."""
    try:
        api_logger.info(json.dumps({'endpoint': endpoint, 'data': data}))
    except Exception:
        pass


park_start_ms = None
last_shift_state = None
trip_path = []
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


def _log_trip_point(ts, lat, lon):
    """Append a GPS point to the trip history CSV."""
    try:
        os.makedirs('data', exist_ok=True)
        with open(os.path.join('data', 'trip_history.csv'), 'a', encoding='utf-8') as f:
            f.write(f"{ts},{lat},{lon}\n")
    except Exception:
        pass


def track_drive_path(vehicle_data):
    """Maintain the current trip path and log points when driving."""
    global trip_path
    drive = vehicle_data.get('drive_state', {}) if isinstance(vehicle_data, dict) else {}
    shift = drive.get('shift_state')
    lat = drive.get('latitude')
    lon = drive.get('longitude')
    ts = drive.get('timestamp') or drive.get('gps_as_of')
    if ts and ts < 1e12:
        ts = int(ts * 1000)
    if shift in (None, 'P'):
        trip_path = []
        return
    if lat is not None and lon is not None:
        point = [lat, lon]
        if not trip_path or trip_path[-1] != point:
            trip_path.append(point)
            if ts is not None:
                _log_trip_point(ts, lat, lon)


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
    return os.path.join('data', f'cache_{name}.json')


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


def _load_last_trip(filename=os.path.join('data', 'trip_history.csv'), idle_ms=600000):
    """Return coordinates of the most recent trip from the history CSV."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            rows = [line.strip().split(',') for line in f if line.strip()]
            rows = [(int(t), float(lat), float(lon)) for t, lat, lon in rows]
    except Exception:
        return []
    if not rows:
        return []

    path = [[rows[-1][1], rows[-1][2]]]
    prev = rows[-1][0]
    for ts, lat, lon in reversed(rows[:-1]):
        if prev - ts > idle_ms:
            break
        path.insert(0, [lat, lon])
        prev = ts
    return path


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


def _fetch_loop(vehicle_id, interval=5):
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
    return render_template('index.html')


@app.route('/map')
def map_only():
    """Display only the map without additional modules."""
    return render_template('map.html')


@app.route('/history')
def trip_history():
    """Show the last recorded trip on a map."""
    path = _load_last_trip()
    heading = 0.0
    if len(path) >= 2:
        heading = _bearing(path[-2], path[-1])
    return render_template('history.html', path=path, heading=heading)


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


@app.route('/error')
def get_errors():
    """Return collected API errors."""
    with api_errors_lock:
        return jsonify(list(api_errors))


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
        with open(os.path.join('data', 'api.log'), 'r', encoding='utf-8') as f:
            log_lines = f.readlines()[-50:]
    except Exception:
        pass

    with api_errors_lock:
        errors = list(api_errors)

    return render_template('debug.html', env_info=env_info, log_lines=log_lines,
                          errors=errors, latest=latest_data)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8013, debug=True)
