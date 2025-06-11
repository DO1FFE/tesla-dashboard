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

## Features

While parked, the dashboard now displays tire pressure readings, instantaneous power usage, the 12V consumption and how long the vehicle has been parked. The information table is sorted for easier comparison.

## Reference

For a sample API response from Tesla, see [docs/sample_api_response.json](docs/sample_api_response.json).
