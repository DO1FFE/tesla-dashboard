import os
from flask import Flask, render_template, jsonify
from dotenv import load_dotenv

try:
    import teslapy
except ImportError:
    teslapy = None

load_dotenv()
app = Flask(__name__)

park_start_ms = None
last_shift_state = None


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

    tesla = teslapy.Tesla(email)
    if tokens_provided:
        tesla.sso_token = {"access_token": access_token, "refresh_token": refresh_token}
        tesla.refresh_token()
    elif access_token:
        tesla.refresh_token({'access_token': access_token})
    else:
        tesla.fetch_token(password=password)
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


def get_vehicle_data(vehicle_id=None):
    """Fetch vehicle data for a given vehicle id."""
    tesla = get_tesla()
    if tesla is None:
        return {"error": "Missing Tesla credentials or teslapy not installed"}

    vehicles = tesla.vehicle_list()
    if not vehicles:
        return {"error": "No vehicles found"}

    vehicle = None
    if vehicle_id is not None:
        vehicle = next((v for v in vehicles if str(v['id_s']) == str(vehicle_id)), None)
    if vehicle is None:
        vehicle = vehicles[0]

    vehicle_data = vehicle.get_vehicle_data()
    track_park_time(vehicle_data)
    sanitized = sanitize(vehicle_data)
    sanitized['park_start'] = park_start_ms
    return sanitized


def get_vehicle_list():
    """Return a list of available vehicles without exposing VIN."""
    tesla = get_tesla()
    if tesla is None:
        return []
    vehicles = tesla.vehicle_list()
    sanitized = []
    for idx, v in enumerate(vehicles, start=1):
        name = v.get('display_name')
        if not name:
            name = f"Fahrzeug {idx}"
        sanitized.append({"id": v['id_s'], "display_name": name})
    return sanitized


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/data')
def api_data():
    data = get_vehicle_data()
    return jsonify(data)


@app.route('/api/data/<vehicle_id>')
def api_data_vehicle(vehicle_id):
    data = get_vehicle_data(vehicle_id)
    return jsonify(data)


@app.route('/api/vehicles')
def api_vehicles():
    vehicles = get_vehicle_list()
    return jsonify(vehicles)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8013, debug=True)
