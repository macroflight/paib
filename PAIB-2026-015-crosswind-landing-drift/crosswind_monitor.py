"""Passive PSX monitor for the crosswind-drift investigation.

Does NOT control PSX in any way (no weight/wind/AP/motion-freeze writes --
the user drives all of that manually). Connects, logs aircraft state
continuously at high rate, and prints a live-computed downwind drift rate
(crosswind component of the actual ground track, relative to the runway
heading captured at startup) so the user can watch it converge toward the
commanded crosswind value in real time.

Stops automatically a few seconds after OnGround transitions to 1
(touchdown), or can be stopped manually with Ctrl-C at any time -- the full
raw log is flushed either way.

Usage:
  python3 crosswind_monitor.py --port 10747
"""
import argparse
import asyncio
import csv
import math
import sys
import time

sys.path.insert(0, "/home/kronberg/psxhacks")
from psx import Client  # noqa: E402

HOST = "127.0.0.1"
R_EARTH_M = 6371000.0
MS_TO_KT = 1.94384

REFERENCE_HEADING_SAMPLES = 10   # samples averaged at startup for runway heading
STATUS_PERIOD_S = 1.0
TOUCHDOWN_LINGER_S = 5.0         # keep logging this long after OnGround=1
MAX_DURATION_S = 1200


def wrap_pi(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


class Monitor:
    def __init__(self, args):
        self.args = args
        self.psx = Client()
        self.psx.logger = lambda msg: None
        self.lat = None
        self.lon = None
        self.heading = None
        self.bank = None
        self.pitch = None
        self.tas_kt = None
        self.on_ground = None
        self.acft_height = None
        self.offpath = None
        self.afds = None
        self.samples = []  # (t, lat, lon, heading, bank, pitch, tas_kt, on_ground, height, offpath)
        self.runway_heading = None
        self.touchdown_t = None
        t0 = time.strftime("%Y%m%d_%H%M%S")
        self.logfile = (
            "/tmp/claude-1000/-home-kronberg-psxhacks/"
            "a46b2231-3315-403e-9129-33c916b96cba/scratchpad/"
            f"crosswind_{t0}.csv"
        )

    def ts(self):
        return time.strftime("%H:%M:%S", time.localtime()) + f".{int(time.time()*1000)%1000:03d}"

    def log(self, msg):
        print(f"{self.ts()}  {msg}", flush=True)

    def on_pibaal(self, _k, value):
        p = value.split(";")
        self.pitch = math.degrees(float(p[0]) / 1_000_000)
        self.bank = math.degrees(float(p[1]) / 1_000_000)
        self.heading = float(p[2])  # radians
        self.tas_kt = float(p[4]) / 1000.0
        self.lat = float(p[5])
        self.lon = float(p[6])
        t = time.time()
        self.samples.append((t, self.lat, self.lon, self.heading, self.bank,
                              self.pitch, self.tas_kt, self.on_ground,
                              self.acft_height, self.offpath))

    def on_ground_cb(self, _k, value):
        prev = self.on_ground
        self.on_ground = int(value)
        if prev == 0 and self.on_ground == 1 and self.touchdown_t is None:
            self.touchdown_t = time.time()
            self.log(f"*** TOUCHDOWN DETECTED (OnGround 0->1) ***")

    def on_height(self, _k, value):
        self.acft_height = value

    def on_offpath(self, _k, value):
        self.offpath = value

    def on_afds(self, _k, value):
        self.afds = value

    def instant_ground_vel(self):
        """Return (speed_kt, track_rad) from the last two samples, or None."""
        if len(self.samples) < 2:
            return None
        t1, lat1, lon1 = self.samples[-2][0:3]
        t2, lat2, lon2 = self.samples[-1][0:3]
        dt = t2 - t1
        if dt <= 0:
            return None
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        lat0 = (lat1 + lat2) / 2
        x = R_EARTH_M * dlon * math.cos(lat0)   # east
        y = R_EARTH_M * dlat                     # north
        dist = math.hypot(x, y)
        speed_ms = dist / dt
        track = math.atan2(x, y)  # radians, 0=north, clockwise
        return speed_ms * MS_TO_KT, track

    def crosswind_component_kt(self):
        v = self.instant_ground_vel()
        if v is None or self.runway_heading is None:
            return None
        speed_kt, track = v
        rel = wrap_pi(track - self.runway_heading)
        cross_kt = speed_kt * math.sin(rel)
        along_kt = speed_kt * math.cos(rel)
        return cross_kt, along_kt

    async def wait_ready(self):
        while self.lat is None or self.on_ground is None:
            await asyncio.sleep(0.2)
        while self.on_ground != 0:
            await asyncio.sleep(0.3)

    async def capture_reference_heading(self):
        headings = []
        while len(headings) < REFERENCE_HEADING_SAMPLES:
            await asyncio.sleep(0.3)
            if self.on_ground != 0:
                # Repositioned back onto the ground mid-capture (stale
                # rollout from a prior run) -- restart the capture once
                # airborne again so we never lock a ground-roll heading.
                headings = []
                continue
            if self.heading is not None:
                headings.append(self.heading)
        # circular mean
        sin_sum = sum(math.sin(h) for h in headings)
        cos_sum = sum(math.cos(h) for h in headings)
        self.runway_heading = math.atan2(sin_sum, cos_sum)
        self.log(f"Reference (runway) heading captured: "
                 f"{math.degrees(self.runway_heading):.2f} deg "
                 f"(from {len(headings)} samples)")

    async def status_loop(self):
        while self.touchdown_t is None or (time.time() - self.touchdown_t) < TOUCHDOWN_LINGER_S:
            await asyncio.sleep(STATUS_PERIOD_S)
            cw = self.crosswind_component_kt()
            cw_str = ""
            if cw is not None:
                cross_kt, along_kt = cw
                cw_str = (f"  drift(cross)={cross_kt:+6.2f}kt  "
                          f"along={along_kt:+6.2f}kt")
            self.log(f"hdg={math.degrees(self.heading or 0):6.1f}  "
                     f"bank={self.bank or 0:+5.1f}  "
                     f"tas={self.tas_kt or 0:5.1f}kt  "
                     f"height={self.acft_height}  "
                     f"onground={self.on_ground}{cw_str}")
            if time.time() - (self.samples[0][0] if self.samples else time.time()) > MAX_DURATION_S:
                self.log("Safety timeout reached, stopping.")
                break
        self.log("Monitoring complete.")
        self.dump_csv()
        import os
        os._exit(0)  # pylint: disable=protected-access

    def dump_csv(self):
        with open(self.logfile, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "lat_deg", "lon_deg", "heading_deg", "bank_deg",
                        "pitch_deg", "tas_kt", "on_ground", "height", "offpath"])
            for row in self.samples:
                t, lat, lon, hdg, bank, pitch, tas, og, height, offpath = row
                w.writerow([f"{t:.3f}", f"{math.degrees(lat):.7f}",
                            f"{math.degrees(lon):.7f}", f"{math.degrees(hdg):.2f}",
                            f"{bank:.2f}", f"{pitch:.2f}", f"{tas:.2f}",
                            og, height, offpath])
        self.log(f"Log written: {self.logfile} ({len(self.samples)} samples)")


async def main(args):
    m = Monitor(args)
    m.psx.subscribe("PiBaHeAlTas", m.on_pibaal)
    m.psx.subscribe("OnGround", m.on_ground_cb)
    m.psx.subscribe("AcftHeight", m.on_height)
    m.psx.subscribe("Offpath", m.on_offpath)
    m.psx.subscribe("Afds", m.on_afds)

    def on_connect():
        m.psx.send("name", "TEST:CrosswindMonitor")
        m.psx.send("clientName", "TEST:CrosswindMonitor")

        async def run():
            await m.wait_ready()
            m.log(f"Ready. lat={math.degrees(m.lat):.6f} lon={math.degrees(m.lon):.6f} "
                  f"hdg={math.degrees(m.heading):.1f} on_ground={m.on_ground}")
            m.log("Capturing reference (runway) heading from current AP-tracked heading...")
            await m.capture_reference_heading()
            m.log("READY FOR TEST. Waiting for wind change / AP off / motion freeze release.")
            m.log("Monitoring continuously -- will auto-stop shortly after touchdown.")
            asyncio.create_task(m.status_loop())
        asyncio.create_task(run())

    m.psx.onConnect = on_connect
    with m.psx:
        await m.psx.connect(HOST, args.port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=10747)
    cli_args = parser.parse_args()
    try:
        asyncio.run(main(cli_args))
    except KeyboardInterrupt:
        pass
