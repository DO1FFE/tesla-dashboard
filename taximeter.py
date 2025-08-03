import threading
import time
import math
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Berlin")


class Taximeter:
    def __init__(self, fetch_func, tariff_func, vehicle_id=None):
        self.fetch_func = fetch_func
        self.tariff_func = tariff_func
        self.vehicle_id = vehicle_id
        self.vehicle_db_id = None
        self.user_id = None
        self.lock = threading.Lock()
        self.active = False
        self.paused = False
        self.ready = True
        self.points = []
        self.distance = 0.0
        self.price = 0.0
        self.start_time = None
        self.thread = None
        self.ride_id = None
        self.tariff = {}
        self.last_result = None
        self.wait_time = 0.0
        self.wait_cost = 0.0
        self.waiting = False

    def _is_night(self, timestamp):
        hour = datetime.fromtimestamp(timestamp, LOCAL_TZ).hour
        return hour >= 22 or hour < 6

    def start(self):
        if not self.vehicle_id or self.vehicle_db_id is None:
            raise ValueError("vehicle_id required")
        from app import app, db
        from models import TaximeterRide

        thread_needed = False
        with self.lock:
            if self.active:
                return False
            if self.paused:
                self.active = True
                self.paused = False
                self.waiting = False
                thread_needed = True
                if self.ride_id:
                    with app.app_context():
                        ride = TaximeterRide.query.get(self.ride_id)
                        if ride:
                            ride.status = "active"
                            db.session.commit()
            elif not self.ready:
                return False
            else:
                self.tariff = self.tariff_func() or {}
                self.active = True
                self.ready = False
                self.last_result = None
                self.points = []
                self.distance = 0.0
                self.wait_time = 0.0
                self.wait_cost = 0.0
                self.waiting = False
                self.price = self._round_price(self._calc_price(0.0))
                self.start_time = time.time()
                thread_needed = True
                with app.app_context():
                    ride = TaximeterRide(
                        status="active",
                        started_at=datetime.now(timezone.utc),
                        tariff_snapshot_json=json.dumps(self.tariff),
                        user_id=self.user_id,
                        vehicle_id=self.vehicle_db_id,
                    )
                    db.session.add(ride)
                    db.session.commit()
                    self.ride_id = ride.id
        if thread_needed:
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        return True

    def pause(self):
        if not self.vehicle_id:
            raise ValueError("vehicle_id required")
        from app import app, db
        from models import TaximeterRide
        with self.lock:
            if not self.active:
                return False
            self.active = False
            self.paused = True
        if self.thread:
            self.thread.join()
            self.thread = None
        if self.ride_id:
            with app.app_context():
                ride = TaximeterRide.query.get(self.ride_id)
                if ride:
                    ride.status = "paused"
                    db.session.commit()
        return True

    def stop(self):
        if not self.vehicle_id:
            raise ValueError("vehicle_id required")
        from app import app, db
        from models import TaximeterRide
        with self.lock:
            if not self.active:
                return None
            self.active = False
            self.paused = False
            self.waiting = False
        if self.thread:
            self.thread.join()
        end = time.time()
        start = self.start_time
        duration = end - start
        dist = self.distance
        price = self._round_price(self._calc_price(dist) + self.wait_cost)
        breakdown = self._calc_breakdown(dist)
        ride_id = self.ride_id
        with app.app_context():
            ride = TaximeterRide.query.get(ride_id) if ride_id else None
            if ride:
                ride.status = "stopped"
                ride.ended_at = datetime.now(timezone.utc)
                ride.duration_s = duration
                ride.distance_m = dist * 1000
                ride.wait_time_s = self.wait_time
                ride.cost_base = breakdown.get("base")
                ride.cost_distance = (
                    breakdown.get("cost_1_2", 0.0)
                    + breakdown.get("cost_3_4", 0.0)
                    + breakdown.get("cost_5_plus", 0.0)
                )
                ride.cost_wait = breakdown.get("wait_cost", 0.0)
                ride.cost_total = price
                ride.receipt_json = json.dumps(
                    {"breakdown": breakdown, "distance": dist}
                )
                db.session.commit()
        result = {
            "start_time": start,
            "end_time": end,
            "duration": duration,
            "distance": dist,
            "price": price,
            "breakdown": breakdown,
            "ride_id": ride_id,
            "wait_time": self.wait_time,
        }
        with self.lock:
            self.price = price
            self.last_result = result
            self.thread = None
        return result

    def status(self):
        if not self.vehicle_id:
            raise ValueError("vehicle_id required")
        with self.lock:
            if not self.active:
                result = {"active": False, "paused": self.paused, "waiting": self.waiting}
                if self.last_result:
                    result.update(
                        {
                            "distance": round(self.last_result["distance"], 3),
                            "price": round(self.last_result["price"], 2),
                            "duration": self.last_result["duration"],
                            "breakdown": self.last_result.get("breakdown"),
                            "ride_id": self.last_result.get("ride_id"),
                        }
                    )
                return result
            duration = time.time() - self.start_time
            return {
                "active": True,
                "paused": False,
                "waiting": self.waiting,
                "distance": round(self.distance, 3),
                "price": round(self.price, 2),
                "duration": duration,
            }

    def _run(self):
        from app import app, db
        from models import TaximeterPoint
        with app.app_context():
            last = None
            last_ts = time.time()
            wait_interval = 10.0
            while True:
                with self.lock:
                    if not self.active:
                        break
                data = self.fetch_func(self.vehicle_id)
                lat = None
                lon = None
                speed = None
                heading = None
                odo = None
                if isinstance(data, dict):
                    drive = data.get("drive_state", {})
                    lat = drive.get("latitude")
                    lon = drive.get("longitude")
                    speed = drive.get("speed")
                    heading = drive.get("heading")
                    odo = drive.get("odometer")
                now = time.time()
                dt = now - last_ts
                last_ts = now
                moving = speed is not None and speed >= 5
                if lat is not None and lon is not None:
                    point = (lat, lon)
                    with self.lock:
                        if not self.points or self.points[-1] != point:
                            self.points.append(point)
                            if last is not None:
                                self.distance += self._haversine(last, point)
                            last = point
                    if self.ride_id:
                        p = TaximeterPoint(
                            ride_id=self.ride_id,
                            ts=datetime.now(timezone.utc),
                            lat=lat,
                            lon=lon,
                            speed_kph=speed,
                            heading_deg=heading,
                            odo_m=odo * 1000 if odo is not None else None,
                            is_pause=False,
                            is_wait=not moving,
                        )
                        db.session.add(p)
                        db.session.commit()
                with self.lock:
                    self.waiting = not moving
                    if not moving:
                        prev_units = int(self.wait_time // wait_interval)
                        self.wait_time += dt
                        units = int(self.wait_time // wait_interval)
                        if units > prev_units:
                            rate = self.tariff.get("wait_per_10s", 0.10)
                            self.wait_cost = units * rate
                    self.price = self._round_price(
                        self._calc_price(self.distance) + self.wait_cost
                    )
                time.sleep(2)

    def _calc_breakdown(self, km):
        base = self.tariff.get("base", 4.40)
        r12 = self.tariff.get("rate_1_2", 2.70)
        r34 = self.tariff.get("rate_3_4", 2.60)
        r5 = self.tariff.get("rate_5_plus", 2.40)

        # Night tariff no longer applied

        km1 = min(2.0, km)
        km2 = min(2.0, max(0.0, km - km1))
        km3 = max(0.0, km - km1 - km2)

        cost1 = km1 * r12
        cost2 = km2 * r34
        cost3 = km3 * r5
        wait_cost = self.wait_cost
        total = self._round_price(base + cost1 + cost2 + cost3 + wait_cost)

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
            "wait_time": round(self.wait_time, 1),
            "wait_cost": round(wait_cost, 2),
            "total": total,
            "distance": round(km, 3),
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

    @staticmethod
    def _round_price(value):
        return round(round(value * 10) / 10, 2)

    def _calc_price(self, km):
        base = self.tariff.get("base", 4.40)
        r12 = self.tariff.get("rate_1_2", 2.70)
        r34 = self.tariff.get("rate_3_4", 2.60)
        r5 = self.tariff.get("rate_5_plus", 2.40)

        # Night tariff removed
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
        return price

    def reset(self):
        if not self.vehicle_id:
            raise ValueError("vehicle_id required")
        with self.lock:
            self.active = False
            self.paused = False
            self.ready = True
            self.points = []
            self.distance = 0.0
            self.price = 0.0
            self.start_time = None
            self.thread = None
            self.last_result = None
            self.wait_time = 0.0
            self.wait_cost = 0.0
            self.waiting = False
            self.ride_id = None
