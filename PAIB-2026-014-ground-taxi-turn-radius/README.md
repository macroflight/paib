# PAIB/2026/014 — Ground Taxi Turn Radius Performance Investigation

Archive for the PSX 747-400 ground taxi turn radius investigation, prepared
in response to PSX Forum reports of an "unrealistically large" turn radius.

**Status: resolved.** PSX update 10.190 (released after initial publication)
addresses the investigation's findings; see report Section 7 (addendum,
15 August 2026) and the "Post-fix verification" note below.

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
- `evidence/ESSA-rw26-start.png`, `evidence/ESSA-rw26-stop.png` — the two
  screenshots behind report Section 3.7, the investigation's original
  single most significant finding (pre-fix). A manually-flown 180° turn at
  ESSA runway 26, using the exact documented minimum-radius technique
  (Ref. 3) with body gear steering confirmed operative, starting with the
  right outer main gear on the runway edge line. The MSFS ruler tool
  measured 61.0 m between the gear's start and end position, giving a
  measured outer main gear radius of 30.5 m — 64% larger than the 18.6 m
  Boeing publishes for that gear (a gear body gear steering does not
  affect either way).
- `evidence/ESSA-rw26-190-start.png`, `evidence/ESSA-rw26-190-stop.png` —
  the same test repeated after PSX update 10.190 (report Section 7). The
  ruler measured 45.77 m outer-gear displacement (a second independent run
  measured 47 m) — an essentially direct match for Boeing's own published
  46.3 m minimum-runway-width figure, and a dramatically different visual
  outcome: the aircraft stays on paved surface throughout, rather than
  ending up on the grass.
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

The runs timestamped `20260814_1050*`, `20260814_1053*`, and
`20260814_1058*` (`roll_200t_100pct_tla0`, `roll_200t_50pct_tla0`, and
`roll_380t_100pct_tla800` respectively, all on `--port 10747`) were taken
with body gear steering directly disabled (AC + DC "BODY GR STRNG ARM"
circuit breakers pulled in the cockpit) — this is report Section 3.6, the
investigation's original headline finding. Everything else prior to the
10.190 update is with body gear steering in its normal, operative state.

The four runs timestamped `20260815_152*` (two `roll_200t_100pct_tla0`
repeats, one `roll_200t_50pct_tla0`, one `roll_380t_100pct_tla800_...`)
are the post-fix harness verification against **PSX 10.190**, report
Section 7.1 — same bare PSX Main Server, same situ, same methodology as
the original trials, run after the developer's fix. These are the only
runs in the archive taken against the updated build; everything else
reflects the original (pre-10.190) behaviour.

## Summary of findings

**Resolution (Section 7, added 15 August 2026):** PSX update 10.190
addresses this investigation's findings. Re-verified via the same visual
technique at ESSA runway 26, the outer main gear's measured turn diameter
dropped from 61.0 m (original) to 45.77 m / 47 m (10.190, two independent
runs) — an essentially direct match for Boeing's own published 46.3 m
minimum-runway-width figure. Separately, the harness's own reference-point
measurement dropped from 25.10 m to 16.73–16.74 m (consistent across
weight, tiller, and repeat runs), in the same direction and rough
magnitude as the developer's own stated 14 m figure. The Board considers
the investigation's findings resolved.

**Original findings (pre-fix):** disabling body gear steering increased
turn radius by 24–40% (weight-independent), closely matching both a forum
poster's own description ("like the body gear is not steering") and this
investigation's separately-measured high-speed (body-gear-deactivated)
condition — but the magnitude was 4–5x larger, proportionally, than the
manufacturer's own published inoperative-vs-operative comparison. The
investigation's single most significant finding was a direct visual
measurement (Section 3.7) showing the outer main gear itself tracking 64%
wider than published, with body gear steering confirmed operative — a
discrepancy independent of body gear steering state, since that gear isn't
affected by it either way.

With body gear steering operative, the harness's own reference-point
turn radius otherwise matched real-world reference data at every gross
weight (200–380t) and host configuration tested; was unaffected by
`Qi275`/`TowTurnRadius`; and opened up sharply above ~18kt in a way that
was weight-independent and consistent with known real-aircraft
nosewheel/body-gear-steering speed limits.

The report's References section (Section 8) is explicit about what was
independently verified, what came from a real-aircraft manual, and what
was considered but rejected for lacking a traceable source.
