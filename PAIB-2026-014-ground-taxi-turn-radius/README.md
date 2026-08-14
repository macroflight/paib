# PAIB/2026/014 — Ground Taxi Turn Radius Performance Investigation

Archive for the PSX 747-400 ground taxi turn radius investigation, prepared
in response to PSX Forum reports of an "unrealistically large" turn radius.

## Contents

- `PAIB-2026-014-ground-taxi-turn-radius-report.pdf` — the final report.
- `paib_report.html` — HTML source the PDF was rendered from (Chromium
  headless `--print-to-pdf`).
- `PAIB-rubberband.png` — PAIB logo used on the report cover.
- `turn_radius_test.py` — the test harness. Connects directly to a PSX
  Main Server / frankenrouter, sets gross weight (`TrueZfw` + stepped
  `FuelQty` writes), releases the parking brake, drives tiller + engine
  power, and logs position/heading continuously. Turn radius is computed
  per-sample from `r = v/omega` rather than fitting one circle per run, so
  a single pass yields a full radius-vs-speed curve. See `--help` for all
  options (`--real-pilot-mode`, `--continuous-power`, `--brake-upper-kt` /
  `--brake-lower-kt`, `--tow-turn-radius`, `--port`).
- `raw_data/csv_tracks/` — per-run logged position/heading tracks
  (`t, lat_deg, lon_deg, heading_deg`), one CSV per test run.
- `raw_data/console_logs/` — full console output per run, including the
  per-speed-band radius/turn-rate summary the report's tables were built
  from.
- `references/boeing_D6-58326-1_RevF_747-400_airport_planning.pdf` —
  Boeing's publicly-published *747-400 Airplane Characteristics for
  Airport Planning* (Document D6-58326-1, Rev F, Dec 2024), downloaded
  directly from boeing.com. This is the primary source for the
  manufacturer clearance-radii comparison in report Section 3.5 (Ref. 1).
  Other figures in the report's References section (body gear steering
  angles/thresholds, tiller/rudder steering limits, documented
  minimum-radius turn technique) came from a real-aircraft Flight Crew
  Operations/Training Manual the pilot-community member supporting this
  investigation has access to; that manual is airline-specific and is
  **not** included here, and the report deliberately cites it generically
  (no airline/operator named) rather than by its specific edition.

## Reproducing a run

```
python3 turn_radius_test.py --port 10747 --weight-t 200 --tiller-pct 100 \
    --tla 0 --real-pilot-mode
```

Requires a PSX Main Server (or frankenrouter) reachable at `--port`, with
the aircraft on the ground, parking brake set, engines running, and no
obstacles nearby — the harness releases the parking brake and moves the
aircraft.

## Data provenance / known-bad runs

Two bugs in the weight-setting logic were found and fixed mid-investigation.
Runs made before each fix landed do **not** reflect their intended gross
weight and are **not** part of the dataset the report's tables are drawn
from. They are kept here for transparency, not as evidence.

1. **Fuel capacity clamp (~13:53–14:05 UTC-ish / early runs).** An early
   version guessed a flat 23,097 kg/tank main-tank capacity; PSX actually
   clamps per-tank, differently per tank, and the real total was lower
   than intended. Fixed by switching to modest (~2000 kg/tank) stepped
   writes with capacity discovered by read-back, plus `TrueZfw`
   compensation for any shortfall so gross weight always lands exactly on
   target regardless of tank limits.
2. **Stale fuel not drained on a heavy→light transition.** The stepped-fill
   routine only ever *added* fuel toward a target; it never drained a tank
   that already held more than the new target. Running a light (200t) test
   right after a heavy (380t) test left 30–40t of stale fuel in the mains
   and/or center tank, so the aircraft was actually ~35–40t heavier than
   logged. This affected:
   - The three bare-PSX (`--port 10747`) high-speed continuous-power
     sweeps at nominal 200t (tla=400, tla=700, and 50%/tla=500) — these
     were re-run after the fix and the superseded CSVs/logs are the ones
     with **earlier** timestamps for the same `roll_200t_..._tlaNNN_*`
     filename prefix.
   - One full-sim (`--port 10748`) low-speed (2-3kt) run, killed before
     completion once the discrepancy was spotted live (no CSV/log was
     produced for the killed attempt — nothing to disregard there beyond
     what's simply absent).

   Both `step_fill_tanks()` calls (mains, then center) now always target
   the tank explicitly (including 0), so a lighter test correctly drains
   a tank a heavier prior test filled.

`turn_test_200t_3kt_50pct_20260814_075128.csv` is from the very first
exploratory attempt (closed-loop TAS-based speed holding, before the
`psx._set()` local-cache bug was found and the methodology moved to the
roll-and-measure / real-pilot-braking approach used everywhere else). Not
part of the final dataset; kept for history only.

Every other CSV/log pair reflects a run made with the corrected weight
logic and is valid data. Where a configuration was run more than once
(e.g. repeated across bare-PSX and full-sim/MSFS-linked hosts, or as a
sanity re-check), all such runs are included — they agree with each other
to within measurement noise, which is itself part of the report's finding
that host/visual configuration has no effect.

The three most recent runs (`roll_200t_100pct_tla0_20260814_1050*.csv`,
`roll_200t_50pct_tla0_20260814_1053*.csv`, and
`roll_380t_100pct_tla800_20260814_1058*.csv`, all on `--port 10747`) were
taken with body gear steering directly disabled (AC + DC "BODY GR STRNG
ARM" circuit breakers pulled in the cockpit) — this is report Section 3.6,
the investigation's headline finding. Everything else in the archive is
with body gear steering in its normal, operative state.

## Summary of findings

See the report. Headline finding: disabling body gear steering increases
turn radius by 24–40% (weight-independent), closely matching both a forum
poster's own description ("like the body gear is not steering") and this
investigation's separately-measured high-speed (body-gear-deactivated)
condition — but the magnitude is 4–5x larger, proportionally, than the
manufacturer's own published inoperative-vs-operative comparison, which
may itself warrant engineering attention.

With body gear steering operative, turn radius otherwise matches
real-world reference data at every gross weight (200–380t) and host
configuration tested — including a direct comparison against Boeing's own
published clearance-radii table, where the measured 25.10 m falls right
between the manufacturer's main-gear (18.6 m) and nose-gear (27.7 m) radii
at maximum steering; is unaffected by `Qi275`/`TowTurnRadius`; and opens
up sharply above ~18kt in a way that is weight-independent and consistent
with known real-aircraft nosewheel/body-gear-steering speed limits.

The report's References section (Section 7) is explicit about what was
independently verified, what came from a real-aircraft manual, and what
was considered but rejected for lacking a traceable source.
