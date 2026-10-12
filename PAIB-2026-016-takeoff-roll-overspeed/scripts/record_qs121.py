"""Record raw PiBaHeAlTas (Qs121) updates from a live PSX connection, with
wall-clock timestamps. Also reports TrueZfw (Qi123) and FuelQty (Qs438) so
the gross weight for this run can be verified against the 249.7t baseline.

One-off data-collection script for comparing a real, plain PSX Main Server
takeoff against the VHHH/EDDF "turbo takeoff" anomaly traces. Not part of
the psxhacks addon suite -- lives in the scratchpad, not the repo.

NOTE: psx.py's Client._set() translates an incoming raw Q-code through the
Lexicon to its friendly name *before* dispatching to callbacks -- so we
must subscribe on the friendly names (PiBaHeAlTas, TrueZfw, FuelQty), not
the raw Q-codes (Qs121, Qi123, Qs438). Subscribing on the raw Q-code is
silently a no-op (see CLAUDE.md's psx.py subscription note).
"""
import asyncio
import datetime
import sys

sys.path.insert(0, "/home/kronberg/psxhacks")
from psx import Client  # noqa: E402  pylint: disable=wrong-import-position

LOGFILE = "/tmp/claude-1000/-home-kronberg-psxhacks/14f85cf4-4177-4b10-b394-add6e88daf3a/scratchpad/qs121_live_capture.log"


def log(line):
    print(line, flush=True)
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def on_pibahealtas(key, value):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log(f"{ts}: {key}={value}")


def on_weight_var(key, value):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log(f"{ts}: WEIGHT {key}={value}")


print(f"Connecting to PSX at 127.0.0.1:20747, logging to {LOGFILE}")
with Client() as psx:
    psx.logger = lambda msg: print(f"   {msg}", flush=True)
    psx.subscribe("id")
    psx.subscribe("version", lambda key, value:
                  print(f"Connected to PSX {value} as client #{psx.get('id')}", flush=True))
    psx.subscribe("PiBaHeAlTas", on_pibahealtas)
    psx.subscribe("TrueZfw", on_weight_var)
    psx.subscribe("FuelQty", on_weight_var)
    try:
        asyncio.run(psx.connect("127.0.0.1", 20747))
    except KeyboardInterrupt as exc:
        raise SystemExit("Stopped by keyboard interrupt (Ctrl-C)") from exc
