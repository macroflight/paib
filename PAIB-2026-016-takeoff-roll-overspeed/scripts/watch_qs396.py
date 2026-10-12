"""Watch FmcTkofRef (Qs396) live, with timestamps, to catch a before/after
derate change on the real PSX Main Server at 127.0.0.1:20747.
"""
import asyncio
import datetime
import sys

sys.path.insert(0, "/home/kronberg/psxhacks")
from psx import Client  # noqa: E402  pylint: disable=wrong-import-position

LOGFILE = "/tmp/claude-1000/-home-kronberg-psxhacks/14f85cf4-4177-4b10-b394-add6e88daf3a/scratchpad/qs396_watch.log"


def on_change(key, value):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = f"{ts}: {key}={value}"
    print(line, flush=True)
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


print(f"Connecting to PSX at 127.0.0.1:20747, watching FmcTkofRef (Qs396), logging to {LOGFILE}")
with Client() as psx:
    psx.logger = lambda msg: print(f"   {msg}", flush=True)
    psx.subscribe("id")
    psx.subscribe("version", lambda key, value:
                  print(f"Connected to PSX {value} as client #{psx.get('id')}", flush=True))
    psx.subscribe("FmcTkofRef", on_change)
    try:
        asyncio.run(psx.connect("127.0.0.1", 20747))
    except KeyboardInterrupt as exc:
        raise SystemExit("Stopped by keyboard interrupt (Ctrl-C)") from exc
