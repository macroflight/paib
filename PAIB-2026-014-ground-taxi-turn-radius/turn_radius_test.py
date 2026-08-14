"""Automated PSX ground turn-radius test (roll-and-measure).

Connects to a bare PSX Main Server, sets gross weight (via TrueZfw + the
first 4 FuelQty tank fields), releases the parking brake, applies a fixed
tiller deflection and a fixed thrust setting (idle by default), and lets
the aircraft accelerate naturally through the turn while logging
lat/lon/heading continuously (brakes are never touched once released).

Instead of holding a fixed speed, turn radius is computed at every sample
from the kinematic relation r = v / omega (groundspeed over turn rate),
giving a full radius-vs-speed curve from a single pass instead of one
radius per discrete speed target.

Usage:
  python3 turn_radius_test.py --weight-t 200 --tiller-pct 100 --tla 0
"""
import argparse
import asyncio
import csv
import math
import statistics
import sys
import time

sys.path.insert(0, "/home/kronberg/psxhacks")
from psx import Client  # noqa: E402

HOST = "127.0.0.1"
PORT = 10747

R_EARTH_M = 6371000.0
LB_PER_KG = 2.20462

FUEL_STEP_KG = 2000.0     # per-tank increment per step (stays under the
                          # ~2268kg jump confirmed to apply instantly)
FUEL_STEP_PAUSE_S = 1.2   # wait for PSX's real confirmation, not our own
                          # optimistic local echo from psx._set()

MAX_CUMULATIVE_TURN_DEG = 360.0  # stop after this much heading change
MAX_SAFE_SPEED_KT = 20.0         # safety abort if this is exceeded
MAX_TEST_DURATION_S = 600
SAMPLE_SMOOTH_WINDOW = 5          # samples, for speed/omega smoothing

# Real-pilot-mode pulsed braking: never hold brakes continuously (heat/wear),
# instead pulse ~50% brake to check speed, then release and let it creep
# back up -- matches the real 747 tight-turn taxi technique.
PILOT_BRAKE_UPPER_KT = 6.5   # start braking above this
PILOT_BRAKE_LOWER_KT = 3.5   # release brake once down to this (never stop!)
PILOT_BRAKE_PCT = "500;500"  # ~50% brake
PILOT_BRAKE_STOP_KT = 0.3    # "stopped" threshold for the final stop


def kg_to_lb(kg):
    return kg * LB_PER_KG


def haversine_m(lat1, lon1, lat2, lon2):
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
    return 2 * R_EARTH_M * math.asin(math.sqrt(a))


class TestHarness:
    def __init__(self, args):
        self.args = args
        self.psx = Client()
        self.psx.logger = lambda msg: None
        self.lat = None
        self.lon = None
        self.heading = None
        self.tla_raw = None
        self.tiller_raw = None
        self.raw_samples = []  # (t, lat, lon, heading_rad)
        self.log_enabled = False
        t0 = time.strftime("%Y%m%d_%H%M%S")
        self.logfile = (
            "/tmp/claude-1000/-home-kronberg-psxhacks/"
            "a46b2231-3315-403e-9129-33c916b96cba/scratchpad/"
            f"roll_{args.weight_t:.0f}t_{args.tiller_pct:.0f}pct_tla{args.tla:.0f}_{t0}.csv"
        )

    def ts(self):
        return time.strftime("%H:%M:%S", time.localtime())

    def log(self, msg):
        print(f"{self.ts()}  {msg}", flush=True)

    def on_pibaal(self, _k, value):
        p = value.split(";")
        self.heading = float(p[2])
        self.lat = float(p[5])
        self.lon = float(p[6])
        if self.log_enabled:
            self.raw_samples.append((time.time(), self.lat, self.lon, self.heading))

    def on_tla(self, _k, value):
        self.tla_raw = value

    def on_tiller(self, _k, value):
        self.tiller_raw = value

    def on_fuelqty(self, _k, value):
        self.fuelqty_raw = value

    async def wait_ready(self):
        self.fuelqty_raw = None
        while self.tla_raw is None or self.lat is None or self.fuelqty_raw is None:
            await asyncio.sleep(0.2)

    def send(self, key, value):
        self.psx.send(key, value)
        self.psx._set(key, value)  # pylint: disable=protected-access

    def fuelqty_field_kg(self, index):
        parts = self.fuelqty_raw.lstrip("d").split(";")
        return (int(parts[index]) / 10.0) / LB_PER_KG

    async def step_fill_tanks(self, target_kg_by_index):
        """Move each tank toward its target (up OR down) in modest steps
        (avoids triggering PSX's slow truck-speed refueling simulation,
        which a single large jump seems to invoke). Stops a tank early if
        it stops responding (real capacity clamp reached)."""
        stuck = {i: 0 for i in target_kg_by_index}
        last_seen = {i: self.fuelqty_field_kg(i) for i in target_kg_by_index}
        for _ in range(200):
            parts = self.fuelqty_raw.lstrip("d").split(";")
            changed = False
            for i, target_kg in target_kg_by_index.items():
                if stuck[i] >= 3:
                    continue
                cur_kg = int(parts[i]) / 10.0 / LB_PER_KG
                remaining = target_kg - cur_kg
                if abs(remaining) > 1.0:
                    step_kg = max(-FUEL_STEP_KG, min(FUEL_STEP_KG, remaining))
                    new_kg = max(0.0, cur_kg + step_kg)
                    parts[i] = str(int(round(kg_to_lb(new_kg) * 10)))
                    changed = True
            if not changed:
                break
            new_fuelqty = "d" + ";".join(parts)
            self.send("FuelQty", new_fuelqty)
            await asyncio.sleep(FUEL_STEP_PAUSE_S)
            for i in target_kg_by_index:
                actual_kg = self.fuelqty_field_kg(i)
                if abs(actual_kg - last_seen[i]) < 0.5:
                    stuck[i] += 1
                else:
                    stuck[i] = 0
                last_seen[i] = actual_kg
        return last_seen

    async def set_weight(self, gross_kg, fuel_kg):
        self.log(f"Setting weight: gross={gross_kg/1000:.1f}t, "
                  f"target fuel={fuel_kg/1000:.1f}t (stepped fill)")

        # Fill mains 0-3 evenly first.
        main_target_kg = fuel_kg / 4.0
        achieved = await self.step_fill_tanks({i: main_target_kg for i in range(4)})
        mains_total_kg = sum(achieved.values())
        self.log(f"-> mains achieved: {mains_total_kg:.0f} kg "
                  f"({[round(v) for v in achieved.values()]})")

        # Spill any shortfall into the center tank (field 6).
        remainder_kg = max(0.0, fuel_kg - mains_total_kg)
        center_result = await self.step_fill_tanks({6: remainder_kg})
        center_kg = center_result[6]
        self.log(f"-> center achieved: {center_kg:.0f} kg "
                  f"(target was {remainder_kg:.0f} kg)")

        total_fuel_kg = mains_total_kg + center_kg
        shortfall_kg = fuel_kg - total_fuel_kg
        if abs(shortfall_kg) > 50.0:
            self.log(f"NOTE: fuel shortfall {shortfall_kg:.0f} kg vs target, "
                      f"compensating via ZFW")

        # ZFW makes up the difference so gross weight hits the target
        # exactly, even if fuel capacity fell short of the request.
        zfw_kg = gross_kg - total_fuel_kg
        zfw_lb = int(round(kg_to_lb(zfw_kg)))
        self.send("TrueZfw", str(zfw_lb))
        self.log(f"-> TrueZfw={zfw_lb} ({zfw_kg/1000:.1f}t), "
                  f"actual gross={(zfw_kg + total_fuel_kg)/1000:.1f}t")
        await asyncio.sleep(1.0)

    async def release_parking_brake(self):
        self.log("Releasing parking brake: Brakes=1000;1000 -> 0;0")
        self.send("Brakes", "1000;1000")
        await asyncio.sleep(1.0)
        self.send("Brakes", "0;0")
        await asyncio.sleep(1.0)

    async def set_parking_brake(self):
        self.log("Setting parking brake: Brakes=1000;1000 -> Qh397=1 -> 0;0")
        self.send("Brakes", "1000;1000")
        await asyncio.sleep(1.0)
        self.send("Qh397", "1")
        await asyncio.sleep(0.5)
        self.send("Brakes", "0;0")
        await asyncio.sleep(1.0)

    def set_tla_all(self, value):
        value = max(0, min(5000, int(value)))
        self.send("Tla", f"{value};{value};{value};{value}")

    def set_tiller(self, value):
        value = max(-999, min(999, int(value)))
        self.send("Tiller", str(value))

    async def run(self):
        await self.wait_ready()
        self.log(f"Ready. lat={math.degrees(self.lat):.6f} "
                  f"lon={math.degrees(self.lon):.6f} "
                  f"heading={math.degrees(self.heading):.1f}")

        gross_kg = self.args.weight_t * 1000
        fuel_kg = 5000.0 if self.args.weight_t <= 250 else 130000.0
        await self.set_weight(gross_kg, fuel_kg)

        if self.args.tow_turn_radius is not None:
            self.log(f"Setting Qi275 (TowTurnRadius) = {self.args.tow_turn_radius} "
                      f"(was {self.psx.get('TowTurnRadius')})")
            self.send("TowTurnRadius", str(self.args.tow_turn_radius))
            await asyncio.sleep(0.5)

        self.log_enabled = True
        await self.release_parking_brake()

        tiller_raw_target = int(round(999 * self.args.tiller_pct / 100.0))
        self.log(f"Applying tiller = {tiller_raw_target} "
                 f"({self.args.tiller_pct}%), breakaway tla={self.args.tla}")
        self.set_tiller(tiller_raw_target)
        self.set_tla_all(self.args.tla)

        # Breakaway: hold power only until the aircraft is actually
        # rolling, then reduce to idle -- matches real-aircraft taxi
        # technique instead of holding power throughout.
        t_breakaway = time.time()
        while True:
            await asyncio.sleep(0.3)
            if len(self.raw_samples) >= 3:
                v = self.instant_speed_kt()
                if v is not None and v > 0.4:
                    if self.args.continuous_power:
                        self.log(f"Breakaway achieved at {v:.2f} kt "
                                 f"({time.time() - t_breakaway:.1f}s), "
                                 f"holding power (continuous-power mode)")
                    else:
                        self.log(f"Breakaway achieved at {v:.2f} kt "
                                 f"({time.time() - t_breakaway:.1f}s), reducing to idle")
                        self.set_tla_all(0)
                    break
            if time.time() - t_breakaway > 30.0:
                self.log("WARNING: no breakaway motion after 30s, "
                         "continuing at breakaway power")
                break

        heading_start = self.heading
        heading_prev = self.heading
        cumulative_turn = 0.0
        t_start = time.time()
        pilot_braking = False

        while abs(cumulative_turn) < math.radians(MAX_CUMULATIVE_TURN_DEG):
            await asyncio.sleep(0.3)
            if time.time() - t_start > MAX_TEST_DURATION_S:
                self.log("ABORT: duration timeout")
                break
            h = self.heading
            d = h - heading_prev
            if d > math.pi:
                d -= 2 * math.pi
            elif d < -math.pi:
                d += 2 * math.pi
            cumulative_turn += d
            heading_prev = h
            if len(self.raw_samples) >= 3:
                v = self.instant_speed_kt()
                if v is not None and v > MAX_SAFE_SPEED_KT:
                    self.log(f"ABORT: speed {v:.1f} kt exceeds safety limit")
                    break
                if self.args.real_pilot_mode and v is not None:
                    if not pilot_braking and v > self.args.brake_upper_kt:
                        self.log(f"Pilot mode: {v:.1f} kt > {self.args.brake_upper_kt}, "
                                 f"pulsing 50% brake")
                        self.send("Brakes", PILOT_BRAKE_PCT)
                        pilot_braking = True
                    elif pilot_braking and v <= self.args.brake_lower_kt:
                        self.log(f"Pilot mode: {v:.1f} kt <= {self.args.brake_lower_kt}, "
                                 f"releasing brake")
                        self.send("Brakes", "0;0")
                        pilot_braking = False

        t_end = time.time()
        self.log(f"Stopping: {math.degrees(cumulative_turn):.1f} deg turned "
                 f"in {t_end - t_start:.1f}s, {len(self.raw_samples)} samples")

        self.set_tla_all(0)
        if pilot_braking:
            self.send("Brakes", "0;0")
        self.log(f"Returning tiller to center")
        self.set_tiller(0)

        if self.args.real_pilot_mode:
            self.log("Pilot mode: braking smoothly to a stop")
            self.send("Brakes", PILOT_BRAKE_PCT)
            t_stop = time.time()
            while True:
                await asyncio.sleep(0.3)
                v = self.instant_speed_kt()
                if v is not None and v <= PILOT_BRAKE_STOP_KT:
                    self.log(f"Stopped ({v:.2f} kt)")
                    break
                if time.time() - t_stop > 60.0:
                    self.log("WARNING: not fully stopped after 60s of braking")
                    break

        self.log_enabled = False
        await asyncio.sleep(2.0)
        await self.set_parking_brake()

        self.analyze_and_report()
        self.dump_csv()

    def instant_speed_kt(self):
        if len(self.raw_samples) < 2:
            return None
        t1, lat1, lon1, _ = self.raw_samples[-2]
        t2, lat2, lon2, _ = self.raw_samples[-1]
        dt = t2 - t1
        if dt <= 0:
            return None
        d = haversine_m(lat1, lon1, lat2, lon2)
        return (d / dt) * 1.94384  # m/s -> kt

    async def abort(self):
        self.set_tla_all(0)
        self.log_enabled = False
        await asyncio.sleep(1.0)
        await self.set_parking_brake()
        self.dump_csv()

    def analyze_and_report(self):
        pts = self.raw_samples
        if len(pts) < SAMPLE_SMOOTH_WINDOW + 2:
            self.log("Not enough samples to analyze")
            return

        # Per-consecutive-pair: distance, dt, dheading -> speed, omega, radius
        records = []  # (t_mid, speed_kt, omega_rad_s, radius_m)
        for i in range(1, len(pts)):
            t1, lat1, lon1, h1 = pts[i - 1]
            t2, lat2, lon2, h2 = pts[i]
            dt = t2 - t1
            if dt <= 0:
                continue
            dist = haversine_m(lat1, lon1, lat2, lon2)
            speed_kt = (dist / dt) * 1.94384
            dh = h2 - h1
            if dh > math.pi:
                dh -= 2 * math.pi
            elif dh < -math.pi:
                dh += 2 * math.pi
            omega = dh / dt
            records.append((0.5 * (t1 + t2), speed_kt, omega))

        # Smooth speed and omega with a simple moving average.
        n = len(records)
        w = SAMPLE_SMOOTH_WINDOW
        smoothed = []
        for i in range(n):
            lo = max(0, i - w // 2)
            hi = min(n, i + w // 2 + 1)
            window = records[lo:hi]
            speed_avg = sum(r[1] for r in window) / len(window)
            omega_avg = sum(r[2] for r in window) / len(window)
            smoothed.append((records[i][0], speed_avg, omega_avg))

        results = []  # (speed_kt, radius_m, turn_rate_deg_s)
        for _t, speed_kt, omega in smoothed:
            if abs(omega) < math.radians(0.5):  # <0.5 deg/s, not really turning
                continue
            v_ms = speed_kt / 1.94384
            radius_m = abs(v_ms / omega)
            turn_rate_deg_s = math.degrees(abs(omega))
            results.append((speed_kt, radius_m, turn_rate_deg_s))

        if not results:
            self.log("No valid turning samples (omega always ~0)")
            return

        self.log("=" * 70)
        self.log(f"RESULT weight={self.args.weight_t}t "
                 f"tiller={self.args.tiller_pct}% tla={self.args.tla}")
        self.log(f"  {len(results)} valid (speed, radius, turn-rate) samples")

        # Bin by nearest whole knot, report median radius + turn rate per
        # bin (median is robust to the rare v/omega blowup right at a
        # brake-pulse transition).
        bins = {}
        for speed_kt, radius_m, turn_rate_deg_s in results:
            b = round(speed_kt)
            bins.setdefault(b, []).append((radius_m, turn_rate_deg_s))
        for b in sorted(bins):
            vals = bins[b]
            radii = [v[0] for v in vals]
            rates = [v[1] for v in vals]
            med_r = statistics.median(radii)
            med_rate = statistics.median(rates)
            self.log(f"  ~{b:2d} kt: radius median={med_r:6.2f} m "
                     f"({med_r*3.28084:6.1f} ft)  turn_rate={med_rate:5.2f} deg/s  "
                     f"n={len(vals)} min={min(radii):.2f} max={max(radii):.2f}")

        if 5 in bins:
            mean5 = statistics.median(v[0] for v in bins[5])
            self.log(f"  Sanity check @5kt: {mean5:.2f} m "
                     f"(reference ballpark: 23-25 m)")
        self.log("=" * 70)

    def dump_csv(self):
        with open(self.logfile, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "lat_deg", "lon_deg", "heading_deg"])
            for t, lat, lon, hdg in self.raw_samples:
                w.writerow([f"{t:.3f}", f"{math.degrees(lat):.7f}",
                            f"{math.degrees(lon):.7f}", f"{math.degrees(hdg):.2f}"])
        self.log(f"Log written: {self.logfile}")


async def main(args):
    h = TestHarness(args)
    h.psx.subscribe("PiBaHeAlTas", h.on_pibaal)
    h.psx.subscribe("Tla", h.on_tla)
    h.psx.subscribe("Tiller", h.on_tiller)
    h.psx.subscribe("FuelQty", h.on_fuelqty)
    h.psx.subscribe("TowTurnRadius")

    def on_connect():
        h.psx.send("name", "TEST:TurnRadius")
        h.psx.send("clientName", "TEST:TurnRadius")
        asyncio.create_task(run_and_exit(h))

    h.psx.onConnect = on_connect

    with h.psx:
        await h.psx.connect(HOST, args.port)


async def run_and_exit(h):
    try:
        await h.run()
    except Exception as exc:  # pylint: disable=broad-except
        h.log(f"EXCEPTION: {exc!r}")
        await h.abort()
    import os
    os._exit(0)  # pylint: disable=protected-access


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT,
                         help="PSX Main Server / router port")
    parser.add_argument("--weight-t", type=float, required=True)
    parser.add_argument("--tiller-pct", type=float, required=True)
    parser.add_argument("--tla", type=float, default=0.0,
                         help="Fixed Tla to hold on all 4 engines (0=idle)")
    parser.add_argument("--tow-turn-radius", type=float, default=None,
                         help="Override Qi275 (TowTurnRadius) before the run")
    parser.add_argument("--real-pilot-mode", action="store_true",
                         help="Pulse ~50%% brake to hold speed between "
                              "--brake-lower-kt and --brake-upper-kt")
    parser.add_argument("--brake-upper-kt", type=float, default=PILOT_BRAKE_UPPER_KT,
                         help="Start braking above this speed (kt)")
    parser.add_argument("--brake-lower-kt", type=float, default=PILOT_BRAKE_LOWER_KT,
                         help="Release brake once down to this speed (kt)")
    parser.add_argument("--continuous-power", action="store_true",
                         help="Keep --tla applied after breakaway instead of "
                              "dropping to idle (for high-speed sweeps)")
    cli_args = parser.parse_args()
    asyncio.run(main(cli_args))
