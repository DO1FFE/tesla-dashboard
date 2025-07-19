import sqlite3
import threading
import time
import math


class Taximeter:
    def __init__(self, db_path, fetch_func, tariff_func, vehicle_id="default"):
        self.db_path = db_path
        self.fetch_func = fetch_func
        self.tariff_func = tariff_func
        self.vehicle_id = vehicle_id
        self.lock = threading.Lock()
        self.active = False
        self.ready = True
        self.points = []
        self.distance = 0.0
        self.price = 0.0
        self.start_time = None
        self.thread = None
        self.tariff = {}
        self.last_result = None

    def start(self):
        with self.lock:
            if self.active or not self.ready:
                return False
            self.tariff = self.tariff_func() or {}
            self.active = True
            self.ready = False
            self.last_result = None
            self.points = []
            self.distance = 0.0
            self.price = self._calc_price(0.0)
            self.start_time = time.time()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        with self.lock:
            if not self.active:
                return None
            self.active = False
        if self.thread:
            self.thread.join()
        end = time.time()
        start = self.start_time
        duration = end - start
        dist = self.distance
        price = self._calc_price(dist)
        breakdown = self._calc_breakdown(dist)
        ride_id = self._save_ride(start, end, duration, dist, price)
        result = {
            "start_time": start,
            "end_time": end,
            "duration": duration,
            "distance": dist,
            "price": price,
            "breakdown": breakdown,
            "ride_id": ride_id,
        }
        with self.lock:
            self.price = price
            self.last_result = result
            self.thread = None
        return result

    def status(self):
        with self.lock:
            if not self.active:
                result = {"active": False}
                if self.last_result:
                    result.update(
                        {
                            "distance": round(self.last_result["distance"], 3),
                            "price": round(self.last_result["price"], 2),
                            "duration": self.last_result["duration"],
                        }
                    )
                return result
            duration = time.time() - self.start_time
            return {
                "active": True,
                "distance": round(self.distance, 3),
                "price": round(self.price, 2),
                "duration": duration,
            }

    def _run(self):
        last = None
        while True:
            with self.lock:
                if not self.active:
                    break
            data = self.fetch_func(self.vehicle_id)
            lat = None
            lon = None
            if isinstance(data, dict):
                drive = data.get("drive_state", {})
                lat = drive.get("latitude")
                lon = drive.get("longitude")
            if lat is not None and lon is not None:
                point = (lat, lon)
                with self.lock:
                    if not self.points or self.points[-1] != point:
                        self.points.append(point)
                        if last is not None:
                            self.distance += self._haversine(last, point)
                            self.price = self._calc_price(self.distance)
                        last = point
            time.sleep(5)

    def _calc_breakdown(self, km):
        base = self.tariff.get("base", 4.40)
        r12 = self.tariff.get("rate_1_2", 2.70)
        r34 = self.tariff.get("rate_3_4", 2.60)
        r5 = self.tariff.get("rate_5_plus", 2.40)

        km1 = min(2.0, km)
        km2 = min(2.0, max(0.0, km - km1))
        km3 = max(0.0, km - km1 - km2)

        cost1 = km1 * r12
        cost2 = km2 * r34
        cost3 = km3 * r5

        total = round(base + cost1 + cost2 + cost3, 2)

        return {
            "base": round(base, 2),
            "km_1_2": round(km1, 3),
            "rate_1_2": round(r12, 2),
            "cost_1_2": round(cost1, 2),
            "km_3_4": round(km2, 3),
            "rate_3_4": round(r34, 2),
            "cost_3_4": round(cost2, 2),
            "km_5_plus": round(km3, 3),
            "rate_5_plus": round(r5, 2),
            "cost_5_plus": round(cost3, 2),
            "total": total,
        }

    @staticmethod
    def _haversine(p1, p2):
        lat1, lon1 = p1
        lat2, lon2 = p2
        r = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _calc_price(self, km):
        base = self.tariff.get("base", 4.40)
        r12 = self.tariff.get("rate_1_2", 2.70)
        r34 = self.tariff.get("rate_3_4", 2.60)
        r5 = self.tariff.get("rate_5_plus", 2.40)
        price = base
        remaining = km
        step = min(2.0, remaining)
        price += step * r12
        remaining -= step
        if remaining > 0:
            step = min(2.0, remaining)
            price += step * r34
            remaining -= step
        if remaining > 0:
            price += remaining * r5
        return round(price, 2)

    def _save_ride(self, start, end, duration, distance, price):
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS rides (id INTEGER PRIMARY KEY AUTOINCREMENT, start REAL, end REAL, duration REAL, distance REAL, price REAL)"
        )
        cur.execute(
            "INSERT INTO rides (start, end, duration, distance, price) VALUES (?, ?, ?, ?, ?)",
            (start, end, duration, distance, price),
        )
        ride_id = cur.lastrowid
        con.commit()
        con.close()
        return ride_id

    def reset(self):
        with self.lock:
            self.active = False
            self.ready = True
            self.points = []
            self.distance = 0.0
            self.price = 0.0
            self.start_time = None
            self.thread = None
            self.last_result = None
