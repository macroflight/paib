"""Extended analysis: steady-state + convergence time (first sustained entry into +-10% band)."""
import csv, math, sys

def analyze(path, ref_deg, target_kt=None):
    rows = list(csv.DictReader(open(path)))
    t0 = float(rows[0]["t"])
    ref = math.radians(ref_deg)
    R = 6371000.0

    h0 = rows[0]["height"]
    release_t = None
    for r in rows:
        if r["height"] not in ("", h0):
            try:
                if float(r["height"]) < float(h0) - 1:
                    release_t = float(r["t"]) - t0
                    break
            except ValueError:
                pass
    if release_t is None:
        release_t = 0.0

    vals = []
    for i in range(1, len(rows)):
        r1, r2 = rows[i - 1], rows[i]
        t1, t2 = float(r1["t"]), float(r2["t"])
        dt = t2 - t1
        if dt <= 0 or dt > 1.0:
            continue
        lat1, lon1 = math.radians(float(r1["lat_deg"])), math.radians(float(r1["lon_deg"]))
        lat2, lon2 = math.radians(float(r2["lat_deg"])), math.radians(float(r2["lon_deg"]))
        lat_mid = (lat1 + lat2) / 2
        x = R * (lon2 - lon1) * math.cos(lat_mid)
        y = R * (lat2 - lat1)
        dist = math.hypot(x, y)
        if dist < 0.02:
            continue
        speed_kt = dist / dt * 1.94384
        track = math.atan2(x, y)
        rel = track - ref
        while rel > math.pi: rel -= 2 * math.pi
        while rel < -math.pi: rel += 2 * math.pi
        cross = speed_kt * math.sin(rel)
        og = int(r2["on_ground"])
        vals.append((t2 - t0, cross, og))

    cutoff = release_t + 6.0
    airborne = [v for v in vals if v[2] == 0 and v[0] > cutoff]
    mean = std = None
    if airborne:
        cvals = [v[1] for v in airborne]
        mean = sum(cvals) / len(cvals)
        std = (sum((x - mean) ** 2 for x in cvals) / len(cvals)) ** 0.5

    conv_t = None
    if mean is not None:
        band = 0.10 * abs(mean)
        post_release = [v for v in vals if v[2] == 0 and v[0] >= release_t]
        for i, v in enumerate(post_release):
            if abs(v[1] - mean) <= band:
                rest = post_release[i:i+5]
                if len(rest) >= 3 and all(abs(x[1] - mean) <= band * 1.5 for x in rest):
                    conv_t = v[0] - release_t
                    break

    return {"release_t": release_t, "n": len(airborne) if airborne else 0,
            "mean": mean, "std": std, "conv_t": conv_t}

if __name__ == "__main__":
    for path, ref in [
        ("crosswind_20260815_160020.csv", 57.76),
        ("crosswind_20260815_160611.csv", 57.75),
        ("crosswind_20260815_161021.csv", 57.5),
        ("crosswind_20260815_161210.csv", 57.75),
        ("crosswind_20260815_161336.csv", 57.74),
        ("crosswind_20260815_161449.csv", 57.69),
        ("crosswind_20260815_161627.csv", 57.50),
        ("crosswind_20260815_161721.csv", 57.50),
        ("crosswind_20260815_161823.csv", 57.75),
        ("crosswind_20260815_161951.csv", 57.74),
    ]:
        r = analyze(path, ref)
        print(f"{path}: release_t={r['release_t']:.2f}  n={r['n']}  mean={r['mean']}  std={r['std']}  conv_t={r['conv_t']}")
