# PAIB/2026/015 — Crosswind Landing Downwind Drift Rate Investigation

Archive for the PSX 747-400 crosswind-landing downwind drift investigation,
opened in response to a pilot report that the aircraft drifts downwind
"much quicker than in real life (or FFS for that matter)" during crosswind
de-crab.

**Status: open, follow-up recommended.** The passive (fully hands-off) test
methodology used here found no anomaly in the aircraft's bare response to
ambient crosswind, but cannot confirm or refute the pilot's actual
complaint, which concerns behaviour during an *active*, continuously
corrected de-crab. See report Section 4 and Recommendation 1.

## Contents

- `PAIB-2026-015-crosswind-landing-drift-report.pdf` — the report.
- `paib_report.html` — HTML source the PDF was rendered from (Chromium
  headless `--print-to-pdf`, with `--no-pdf-header-footer` to suppress the
  browser's own date/title/page-number overlay — the flag name changed
  from `--print-to-pdf-no-header` on the Chromium version used for this
  report, 151.0.7922.108).
- `crosswind_monitor.py` — the monitoring harness. Connects to a PSX Main
  Server / frankenrouter in a **purely passive** role: subscribes to
  `PiBaHeAlTas` (position/attitude), `OnGround`, `AcftHeight`, `Offpath`,
  and `Afds`, and logs every update, but never sends a single write to the
  simulator. All test conditions (positioning, wind, autopilot, motion
  freeze) were set up and executed manually by the reporting pilot. See
  `--help` — the only option is `--port`.
- `analyze_run.py` — post-processing script: derives ground speed/track
  from consecutive lat/lon samples, resolves it against the run's captured
  reference heading into crosswind/along-track components, and reports the
  steady-state mean/std (airborne samples from 6s after motion release to
  touchdown) plus time-to-convergence (first sustained entry into ±10% of
  the steady-state mean). Edit the file list at the bottom to point at
  different CSVs.
- `raw_data/csv_tracks/` — one CSV per run (`t, lat_deg, lon_deg,
  heading_deg, bank_deg, pitch_deg, tas_kt, on_ground, height, offpath`).
- `raw_data/console_logs/` — full console output per run, including the
  live-computed drift readout the harness prints once per second and the
  reference-heading capture message.

## Run index

| File prefix | Commanded wind | Notes |
|---|---|---|
| `run1_30kt_uncorrected_wind` | 30 kt @ runway hdg + 90° (true, unverified against ND) | Steady-state 29.33 kt — motivated the Section 2.1 true/magnetic check |
| `run2_30kt` | 30 kt @ 150° (pilot-verified via ND) | 30.69 kt |
| `run3_30kt` | 30 kt @ 150° | 30.11 kt |
| `run4_30kt_DISCARDED_badrefheading` | 30 kt @ 150° | **Discarded** — harness locked its reference heading during ground rollout from run 3, before repositioning; fixed immediately after (see `crosswind_monitor.py`'s `wait_ready`/`capture_reference_heading`, which now wait for a stable airborne heading before capturing) |
| `run5_30kt` | 30 kt @ 150° | 30.76 kt |
| `run6_40kt` | 40 kt @ 150° | 40.70 kt |
| `run7_20kt` | 20 kt @ 150° | 20.66 kt |
| `run8_10kt` | 10 kt @ 150° | 10.22 kt |
| `run9_5kt` | 5 kt @ 150° | 5.21 kt |
| `run10_45deg30kt` | 30 kt @ 105° (45° quartering) | 22.82 kt measured vs. 22.03 kt geometric prediction |
| `run11_calmwind_control` | 0 kt | +0.05 kt — harness baseline noise floor |

Runway heading was captured fresh at the start of every run (via a 10-sample
circular mean while airborne under AP/ILS control) rather than assumed from
a published value; captured values clustered tightly at 57.5–57.8° across
all eleven runs, consistent with EHAM runway 06's nominal magnetic heading.

## Reproducing a run

```
python3 crosswind_monitor.py --port 10747
```

Requires a PSX Main Server (or frankenrouter) reachable at `--port`, with
the aircraft established on autopilot/ILS on the extended centerline and
motion freeze engaged. The harness waits for a stable airborne reference
heading, then logs continuously until ~5 seconds after touchdown, writing
a timestamped CSV to its working directory.

## Known-bad run

`run4_30kt_DISCARDED_badrefheading` — the monitor was restarted immediately
after the previous run's touchdown, before the aircraft had been
repositioned for the next approach. It captured its 10-sample reference
heading while the aircraft was still rolling out on the ground (60.62°
instead of the ~57.5–57.8° seen in every other run), which inflates that
run's logged drift figures by the resulting ~3° reference error. The
underlying position data is otherwise unremarkable — recomputing with the
correct ~57.5° reference gives a result consistent with runs 2/3/5 — but
the raw log's `drift(cross)` column should not be read at face value. Kept
for transparency; not used in the report's tables. The harness fix
(`wait_ready()` now blocks until `on_ground == 0`, and
`capture_reference_heading()` restarts its sample window if the aircraft is
found back on the ground mid-capture) is in the checked-in
`crosswind_monitor.py` and was not needed again.

## Summary of findings

With autopilot disengaged and no corrective control input applied at any
point, the aircraft's downwind drift rate converges to the commanded
crosswind component to within ~2–4% and does so within 1.6 seconds of
motion release across every condition tested (5–40 kt direct crosswind,
30 kt at 45°). A calm-wind control run showed effectively zero drift,
confirming the harness itself introduces no bias. The Board considers this
consistent with ordinary wind-triangle physics for a wings-level aircraft
with no active correction — not evidence of a defect in this specific
(fully hands-off) configuration — but notes this methodology cannot speak
to the pilot's actual complaint, which concerns an *actively* de-crabbed
landing. See the report's Discussion, Conclusions, and Recommendation 1 for
the full reasoning and the recommended follow-up test.
