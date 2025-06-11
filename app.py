import os
from flask import Flask, render_template, jsonify
from dotenv import load_dotenv

try:
    import teslapy
except ImportError:
    teslapy = None

load_dotenv()
app = Flask(__name__)


def get_vehicle_data():
    """Fetch vehicle data using teslapy if available."""
    if teslapy is None:
        return {"error": "teslapy not installed"}

    email = os.getenv("TESLA_EMAIL")
    password = os.getenv("TESLA_PASSWORD")
    access_token = os.getenv("TESLA_ACCESS_TOKEN")
    refresh_token = os.getenv("TESLA_REFRESH_TOKEN")

    tokens_provided = access_token and refresh_token
    if not tokens_provided and not (email and password):
        return {"error": "Missing Tesla credentials"}

    with teslapy.Tesla(email) as tesla:
        if tokens_provided:
            tesla.sso_token = {"access_token": access_token, "refresh_token": refresh_token}
            tesla.refresh_token()
        elif access_token:
            tesla.refresh_token({'access_token': access_token})
        else:
            tesla.fetch_token(password=password)

        vehicles = tesla.vehicle_list()
        if not vehicles:
            return {"error": "No vehicles found"}
        vehicle = vehicles[0]
        vehicle_data = vehicle.get_vehicle_data()
        return vehicle_data


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/data')
def api_data():
    data = get_vehicle_data()
    return jsonify(data)


if __name__ == '__main__':
    app.run(debug=True)
