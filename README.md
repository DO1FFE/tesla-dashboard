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
    - optionally set `TESLA_REQUEST_TIMEOUT` (in seconds) to limit Tesla API calls and avoid gateway timeouts

3. Run the server:
    ```bash
    python app.py
    ```

4. Open `http://localhost:8013` in your browser (the server listens on `0.0.0.0:8013`).
5. On the configuration page (`/config`) you can set your APRS call sign, passcode and an optional comment to transmit position packets via an EU APRS-IS server. You may also enable an additional WX packet using a separate call sign. Temperatures are included in Celsius within the comment. Positions are sent at most every 30 seconds while driving and at least every 10 minutes even without changes. WX packets obey the same limits and are only transmitted when the outside temperature changes or after ten minutes without an update. The page also lets you adjust the Tesla API polling interval, the idle interval, the deep-sleep recheck interval, and disable the announcement text.
6. You can also enter the driver's phone number in international format (for example `+491701234567`), your Infobip API key and an optional sender ID here. Leave the sender field empty if the account does not support custom senders. SMS messages to the driver can be enabled or disabled and you may choose whether they are only allowed while driving or at any time. When restricted to driving mode, messages are still allowed for five minutes after parking.
7. When sending a text message the sender's name is requested as well. The entire message including the name must not exceed 160 characters.

### Fleet battery temperature lookup

Battery temperature can be enriched through the Tesla Fleet API when a charge state endpoint is configured. Set `TESLA_FLEET_CHARGE_STATE_URL` to the full Fleet charge state URL and include a `{vehicle_id}` placeholder that will be replaced automatically. You may optionally fix the vehicle using `TESLA_FLEET_VEHICLE_ID`; otherwise the dashboard falls back to the current vehicle id.

Authentication prefers the dedicated `TESLA_FLEET_ACCESS_TOKEN`. If that is not provided, the dashboard first reuses the active Owner session token from teslapy, then `TESLA_ACCESS_TOKEN`, and finally the Fleet token. Without a Fleet URL or any usable token the Fleet lookup is skipped and the dashboard only uses Owner API data.

Example `.env` snippet:

```
TESLA_FLEET_CHARGE_STATE_URL=https://fleet-api.tesla.com/api/1/vehicles/{vehicle_id}/charge_state
TESLA_FLEET_VEHICLE_ID=12345678901234567
TESLA_FLEET_ACCESS_TOKEN=eyJhbGciOi...
```

All sent text messages are written to `data/sms.log` and can be viewed on the `/sms` page.
Timestamps in this file are recorded in the Europe/Berlin timezone.

All API calls are logged to `data/api.log` without storing request details. The log file uses rotation and will grow to at most 1&nbsp;MB.
Vehicle state changes are written to `data/state.log`.
The file `data/energy.log` keeps a record of the energy added after each charging session. Each entry includes a timestamp in the Europe/Berlin timezone and is used to calculate daily totals on the statistics page.
The latest successful API response is stored in `data/<vehicle_id>/cache.json`.
This cache is always updated with the current vehicle state so the dashboard
knows whether the car is online, asleep or offline even when no fresh data is
available. When the Tesla API cannot be reached the server serves this cached
data back to the client. On startup the server checks for leftover files using the
old naming scheme such as `cache_<id>.json`, `last_energy_<id>.txt` or CSV files
in `data/trips` and moves them to the appropriate vehicle folder automatically.
All data paths are resolved relative to the application directory, so the server
can be started from any location while still accessing existing trips and logs.

### Statistics aggregation

Daily and monthly statistics are persisted in `data/statistics.db` inside the
`statistics_aggregate` table. A background worker processes new log entries
incrementally instead of parsing all files on every request. Existing log files
and `statistics.json` are imported once during the first aggregation run. The
HTML output of `/statistik` stays unchanged because the page now reads directly
from the aggregation table.

The aggregation interval can be configured via the environment variable
`AGGREGATION_INTERVAL_SECONDS` or the CLI flag `--aggregation-interval` when
starting `app.py`. Values are given in seconds and default to five minutes.
After switching to the database-backed aggregation you may optionally remove
the legacy `statistics.json` file if no longer needed.

All required JavaScript and CSS libraries are bundled under `static/` so the dashboard works even without Internet access.

The backend continuously polls the Tesla API and pushes new data to clients using Server-Sent Events (SSE). The frontend never talks to the Tesla API directly. It only requests data from the backend using the `/api/...` endpoints so tokens remain secure on the server.
The frontend first checks `/api/state` to make sure the car is online before
opening the streaming connection. When the vehicle is reported as `offline` or
`asleep` it keeps showing cached data and only performs rare `/api/data`
rechecks based on the configured deep-sleep interval. The backend follows the
same deep-idle strategy and refreshes the Tesla state only occasionally while
no activity indicators are present. The dashboard never wakes the vehicle
automatically.

## Tesla browser compatibility (dropdowns)

The in-car Tesla browser is an embedded Chromium build that can behave differently from modern desktop or mobile browsers. Dropdowns are especially sensitive because touch input, overflow clipping, and stacking contexts can cause native `<select>` elements to open inconsistently or close immediately.

To mitigate this, the frontend includes a Tesla-specific select replacement:

* `static/js/tesla-browser.js` exposes `isTeslaBrowser()` using a user-agent check (`Tesla/` or `QtCarBrowser`).  
  It is intentionally small and safe to call on every page.
* `static/js/tesla-select.js` activates only when `isTeslaBrowser()` is `true`. It hides native `<select>` elements and renders a custom, touch-friendly dropdown.
* The custom select is the **standard** dropdown behavior for the Tesla browser. Other browsers continue to use native selects.

Best practices for future dropdowns in this repo:

* Prefer click/tap handlers over `:hover`-only interactions.
* Avoid `overflow: hidden` on parent containers of dropdowns, or render the dropdown in a top-level layer.
* Avoid `transform` on containers that host absolutely positioned dropdowns.
* Always set explicit `z-index` values for menu layers.
* Keep touch targets at least 44px tall.
* When in doubt, use the Tesla custom select instead of relying on a native `<select>`.

## Features

The dashboard shows a short overview depending on whether the vehicle is parked, driving or charging. Below this, additional tables are grouped by category (battery/charging, climate, drive state, vehicle status and media information) to make the raw API data easier to read. While parked the dashboard also displays tire pressures, power usage of the drive unit and the 12V battery as well as how long the vehicle has been parked.

While driving, a blue path is drawn on the map using the reported GPS positions. All trips of a day are logged to a single CSV file under `data/<vehicle_id>/trips` for later analysis.
The `/history` page lists these files so previous trips can be selected and displayed on an interactive map.
Entire weeks or months can also be chosen to display longer time spans at once.
Using the slider you can inspect each recorded point and see the exact timestamp along with speed and power information.
When multiple cars are available a drop-down menu lets you switch between vehicles.
Below the navigation bar a small media player section shows details of the currently playing track if provided by the API.
The configuration page also offers an option to highlight doors and windows in blue.
Additional toggles allow hiding the heater indicators and the list of nearby Superchargers on the main page.
You can also enable or disable the announcement text and adjust the API polling interval without restarting the server.
Clients reload automatically when the polling interval changes so the new setting takes effect immediately.

Whenever a door, window, the trunk or the frunk is open or the vehicle is unlocked the backend switches to the normal polling interval. The same happens when someone is detected inside, while charging, or the gear lever is in R, N or D. In all other situations the idle interval is used so the car can enter sleep mode. If the car is already `offline`/`asleep` and there are no activity indicators, the backend uses the deep-sleep interval (`api_interval_sleep`) for very infrequent state rechecks.

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
* `/apilog` – show the raw API log
* `/sms` – show the SMS log
* `/api/vehicles` – list available vehicles as JSON
* `/api/state` – return the current vehicle state as JSON
* `/api/version` – return the current dashboard version as JSON
* `/api/clients` – number of connected clients as JSON
* `/api/heatmap` – aggregated trip points for the heatmap
    * Optional query parameters:
        * `max_points=<positive integer>` down-samples the response to the requested number of points. Omit this parameter or set `max_points=0` to return all recorded points.
        * `format=geojson` returns a GeoJSON FeatureCollection instead of a point list.
* `/api/occupant` – get or set occupant presence flag
    * Use `POST` with a JSON body like `{ "present": true }` or `{ "present": false }`
      to notify the dashboard whether someone is inside.
* `/api/announcement` – return the current announcement text as JSON
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
