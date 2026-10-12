# PAIB/2026/016 — Takeoff Roll Overspeed Anomaly Investigation

Archive for the PSX 747-400 takeoff-roll acceleration investigation, opened
after flight-data telemetry from two unrelated takeoffs (VHHH 2026-10-10,
flown multi-crew; EDDF 2026-10-12, flown single-pilot; two days apart,
different pilots/crews) showed acceleration measurably above both a
matched-weight controlled baseline and published real-world 747-400
performance.

**Status: published, root cause identified.** Both anomalies were traced,
independently, to a brief out-of-range burst of `Qs357` (Brakes) sent by the
same installation's FrankenUSB 1.2.1, running behind the investigating
pilot's 30WEST/slavesim router node in both incidents — not the
installation of whoever was flying either incident, which was a different
person/crew in each case. The investigating pilot (who also flew the
follow-up tests below) has identified and is correcting a brake-axis
calibration fault in their own FrankenUSB configuration, and has separately
reported to the Aerowinx developer that PSX's flight-physics model should
not convert an out-of-range brake value into unbounded forward acceleration
in the first place — which the Board treats as the true underlying cause.
See the report's Discussion and Conclusions.

## Contents

- `PAIB-2026-016-takeoff-roll-overspeed-report.pdf` — the report.
- `paib_report.html` — HTML source the PDF was rendered from (Chromium
  headless `--print-to-pdf --no-pdf-header-footer`).
- `PAIB-rubberband.png` — PAIB logo (copy of the one used in prior reports).
- `scripts/record_qs121.py` — the main monitoring harness. Connects to a
  PSX Main Server / frankenrouter, subscribes to `PiBaHeAlTas`, `TrueZfw`,
  and `FuelQty` (via their *friendly names* — see the module docstring for
  why subscribing on the raw `Qs121`/`Qi123`/`Qs438` Q-codes is a silent
  no-op with `psx.py`), and logs every update with a wall-clock timestamp.
  Used for both the matched-weight baseline flight and the live
  negative-brake injection test (Section 3.5/3.9).
- `scripts/test_negative_brakes.py` — a scripted, automated version of the
  negative-brake injection test (5s baseline, one `Brakes=-997;-997` send,
  15s observation). Not the script actually used for the report's
  Section 3.9 result — that test was done manually by the investigating
  pilot, who flew a real takeoff and sent the negative value themselves after
  brake release, with `record_qs121.py` watching. Kept in the archive as a
  cleaner, repeatable alternative for anyone wanting to re-run the test
  without flying a full takeoff.
- `scripts/capture_all.py` — raw-socket full-firehose capture (every
  key=value line, timestamped), used to hunt for an assumed-temperature/
  derate-selection field on the network (none was found — see the report's
  Section 3.10, which only recovered the *downstream* V-speed effect of a
  derate selection, via `Qs396`, not the selection itself).
- `scripts/watch_qs396.py` — narrow watcher for `FmcTkofRef` (`Qs396`)
  alone, used to capture the V1/VR/V2 table in Section 3.10.
- `raw_data/eddf_takeoff_roll_traffic.log`, `vhhh_takeoff_roll_traffic.log`
  — windowed excerpts of each incident's master-router traffic log
  covering the full takeoff roll, including the `Qs357` burst and
  surrounding `Qs121` telemetry.
- `raw_data/eddf_brake_burst_window.txt`, `vhhh_brake_burst.txt` — the
  isolated `Qs357` burst lines quoted in report Section 3.7.
- `raw_data/baseline_and_live_brake_test_capture.log` — full
  `record_qs121.py` output from the matched-weight baseline flight and the
  live negative-brake injection test (Sections 3.5 and 3.9), back to back
  in one capture file.
- `raw_data/derate_qs396_watch.log` — raw `watch_qs396.py` output behind
  the Section 3.10 table.

## Not included

The original incident logs (`ftech1-2026-10-10.zip`, `Baker-logs-261010.zip`,
`logs.zip`, and the EDDF "jan-turbo" router logs) are the investigating
pilot's own private, multi-hundred-megabyte router traffic captures (shared
with the Board for investigation purposes; the incidents themselves were
flown by other pilots/crews, see the report's Section 1), containing a
full record of an entire flight's network traffic, not just the anomaly
window. They are not part of this public archive; the excerpts above are
the complete relevant subset. The two-hop client-identity tracing in report
Section 3.8 (matching `DATA FROM [n]` client slots across router hops via
each client's own `name=`/`clientName=` registration line) was done
directly against those full logs and is not separately scripted — it was a
manual `grep`-based trace, reproducible by anyone with access to the
originals using the exact log lines quoted in the report.

## Summary of findings

Both incidents' takeoff rolls accelerated at 3.5–3.7 m/s² (TAS-derived from
the Main Server's own `Qs121` telemetry), against a 2.4 m/s² matched-weight
controlled baseline and a ≈2.0–2.3 m/s² anecdotal real-world reference
range. Both anomalies coincide, to within a fraction of a second, with a
sub-one-second burst of `Qs357` (Brakes) ramping from a normal positive
value through zero to roughly -990 to -997 — traced in both cases,
independently, to the same client (FrankenUSB 1.2.1) on the investigating
pilot's installation (not the installation of whoever was flying either
incident). A deliberate live test injecting and holding a sustained
negative `Qs357` value reproduced a far more extreme version of the same
effect (peak 285 kt, >9,000 ft/min climb) before an abrupt full-situation
reset, confirming the mechanism directly. Root cause: a local brake-axis
calibration fault (being corrected) exposing an input-validation gap in
PSX's own flight physics (reported to Aerowinx) that converts an
out-of-range brake value into unbounded forward acceleration instead of
rejecting or clamping it.
