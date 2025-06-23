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
5. On the configuration page (`/config`) you can set your APRS call sign, passcode and an optional comment to transmit position packets via an EU APRS-IS server. You may also enable an additional WX packet using a separate call sign. Temperatures are included in Celsius within the comment. Positions are sent at most every 30 seconds while driving and at least every 10 minutes even without changes. WX packets obey the same limits and are only transmitted when the outside temperature changes or after ten minutes without an update. The page also lets you adjust the Tesla API polling interval and disable the announcement text.

API responses are logged to `data/api.log`. The log file uses rotation and will grow to at most 1&nbsp;MB.
Vehicle state changes are written to `data/state.log`.
Timestamps in this file are recorded in the Europe/Berlin timezone.
The latest successful API response is stored in `data/cache_<vehicle_id>.json`.
This cache is always updated with the current vehicle state so the dashboard
knows whether the car is online, asleep or offline even when no fresh data is
available. When the Tesla API cannot be reached the server serves this cached
data back to the client.
All data paths are resolved relative to the application directory, so the server
can be started from any location while still accessing existing trips and logs.

All required JavaScript and CSS libraries are bundled under `static/` so the dashboard works even without Internet access.

The backend continuously polls the Tesla API and pushes new data to clients using Server-Sent Events (SSE).
The frontend first checks `/api/state` to make sure the car is online before
opening the streaming connection.  When the vehicle is reported as `offline` or
`asleep` no further API requests are made, preventing the car from waking up
unexpectedly.  Only when occupant presence is reported via `/api/occupant` will
the application wake the vehicle and query live data.

## Features

The dashboard shows a short overview depending on whether the vehicle is parked, driving or charging. Below this, additional tables are grouped by category (battery/charging, climate, drive state, vehicle status and media information) to make the raw API data easier to read. While parked the dashboard also displays tire pressures, power usage of the drive unit and the 12V battery as well as how long the vehicle has been parked.

While driving, a blue path is drawn on the map using the reported GPS positions. All trips of a day are logged to a single CSV file under `data/trips` for later analysis.
The `/history` page lists these files so previous trips can be selected and displayed on an interactive map.
Entire weeks or months can also be chosen to display longer time spans at once.
Using the slider you can inspect each recorded point and see the exact timestamp along with speed and power information.
When multiple cars are available a drop-down menu lets you switch between vehicles.
Below the navigation bar a small media player section shows details of the currently playing track if provided by the API.
The configuration page also offers an option to highlight doors and windows in blue.
Additional toggles allow hiding the heater indicators and the list of nearby Superchargers on the main page.
You can also enable or disable the announcement text and adjust the API polling interval without restarting the server.
Clients reload automatically when the polling interval changes so the new setting takes effect immediately.

Data is streamed to the frontend via `/stream/<vehicle_id>` using Server-Sent Events so the dashboard updates instantly when new information arrives.
The endpoint `/apiliste` exposes a text file listing all seen API variables and their latest values.

The same information is also stored as hierarchical JSON in `data/api-liste.json`.

## Endpoints

* `/` – main dashboard with map and status information
* `/map` – map-only view without additional details
* `/daten` – vehicle data without the map
* `/history` – select and display recorded trips
* `/error` – show recent API errors (JSON via `/api/errors`)
* `/state` – display the vehicle state log
* `/debug` – display environment info and recent log lines
* `/api/vehicles` – list available vehicles as JSON
* `/api/state` – return the current vehicle state as JSON
* `/api/version` – return the current dashboard version as JSON
* `/api/clients` – number of connected clients as JSON
* `/api/occupant` – get or set occupant presence flag
* `/api/announcement` – return the current announcement text as JSON
    * Use `POST` with a JSON body like `{ "present": true }` or `{ "present": false }`
      to keep the vehicle awake only when someone is inside.
* `/stream/<vehicle_id>` – Server-Sent Events endpoint used by the frontend

## Version

The dashboard reports its own version in the footer. The version string is derived
from the number of Git commits so it increases automatically with every pull request.
Clients periodically fetch `/api/version` and reload the page when the version changes
so the browser always shows the latest release.
The footer also includes a copyright notice:
```
Tesla-Dashboard Version 1.0.X - © <current year> Erik Schauer, do1ffe@darc.de
```

## Reference

For a sample API response from Tesla, see [docs/sample_api_response.json](docs/sample_api_response.json).

The API reports doors, windows, trunk and frunk using numeric values. These
values are `0` when the part is closed and `1` (or any non-zero value) when the
part is open. The dashboard therefore treats any non-zero value as "open" to
handle potential future variations.
