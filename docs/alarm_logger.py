"""Beispielskript zum Protokollieren des Fahrzeugalarmzustands."""

import datetime
import os
import time
import requests

API_URL = os.getenv("API_URL", "http://localhost:8013/api/alarm_state")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
LOG_FILE = "alarm.log"
INTERVAL = 15


def log_event(message: str) -> None:
    timestamp = datetime.datetime.now().isoformat()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} - {message}\n")
    print(f"{timestamp} - {message}")


def get_alarm_state():
    headers = {}
    if ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"
    try:
        response = requests.get(API_URL, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("alarm_state")
        log_event(f"Fehler bei API-Abfrage: {response.status_code}")
    except Exception as e:
        log_event(f"Fehler: {e}")
    return None


log_event("\U0001F697 Tesla Alarm Logger gestartet.")
while True:
    state = get_alarm_state()
    if state == "alarm_triggered":
        log_event("\u26a0 ALARM ausgelöst!")
    elif state is not None:
        log_event(f"Alarmstatus: {state}")
    time.sleep(INTERVAL)
