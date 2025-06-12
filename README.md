# Tesla Dashboard

This is a simple Flask application that displays real-time data from a Tesla vehicle using the [teslapy](https://github.com/tdorssers/TeslaPy) library.

## Setup

1. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
    The application uses `python-dotenv` to load variables from a `.env` file.

2. Copy `.env.example` to `.env` and fill in your Tesla credentials:
    - `TESLA_EMAIL` and `TESLA_PASSWORD` **or**
    - `TESLA_ACCESS_TOKEN` and `TESLA_REFRESH_TOKEN`

3. Run the server:
    ```bash
    python app.py
    ```

4. Open `http://localhost:8013` in your browser (the server listens on `0.0.0.0:8013`).

API responses are logged to `data/api.log`. The log file uses rotation and will
grow to at most 1&nbsp;MB.

All required JavaScript and CSS libraries are bundled under `static/` so the dashboard works even without Internet access.

The backend continuously polls the Tesla API and pushes new data to clients using Server-Sent Events (SSE).

## Features

The dashboard shows a short overview depending on whether the vehicle is parked, driving or charging. Below this, additional tables are grouped by category (battery/charging, climate, drive state, vehicle status and media information) to make the raw API data easier to read. While parked the dashboard also displays tire pressures, power usage of the drive unit and the 12V battery as well as how long the vehicle has been parked.

While driving, a blue path is drawn on the map using the reported GPS positions. These points are also logged to `data/trip_history.csv` for later analysis.

Data is streamed to the frontend via `/stream/<vehicle_id>` using Server-Sent Events so the dashboard updates instantly when new information arrives.

## Reference

For a sample API response from Tesla, see [docs/sample_api_response.json](docs/sample_api_response.json).
