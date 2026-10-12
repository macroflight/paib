"""Test: does sending Qs357 (Brakes) a deeply negative value produce any
unexpected acceleration/motion, isolated from throttle/TOGA input?

Connects, watches PiBaHeAlTas (Qs121) for a few seconds of baseline (should
be perfectly stationary -- TAS=0), then sends Brakes=-997;-997 once, then
keeps watching for any resulting motion for 15 more seconds.
"""
import asyncio
import datetime
import sys

sys.path.insert(0, "/home/kronberg/psxhacks")
from psx import Client  # noqa: E402  pylint: disable=wrong-import-position

LOGFILE = "/tmp/claude-1000/-home-kronberg-psxhacks/14f85cf4-4177-4b10-b394-add6e88daf3a/scratchpad/negative_brakes_test.log"


def log(line):
    print(line, flush=True)
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def on_pibahealtas(key, value):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log(f"{ts}: {key}={value}")


async def run_test(psx):
    log("Watching baseline for 5s (should be stationary, TAS=0)...")
    await asyncio.sleep(5.0)
    log(">>> SENDING Brakes=-997;-997 NOW <<<")
    psx.send("Brakes", "-997;-997")
    log("Watching for 15s after the send...")
    await asyncio.sleep(15.0)
    log("Test complete.")
    raise SystemExit(0)


print(f"Connecting to PSX at 127.0.0.1:20747, logging to {LOGFILE}")
with Client() as psx:
    psx.logger = lambda msg: print(f"   {msg}", flush=True)
    psx.subscribe("id")
    psx.subscribe("version", lambda key, value:
                  print(f"Connected to PSX {value} as client #{psx.get('id')}", flush=True))
    psx.subscribe("PiBaHeAlTas", on_pibahealtas)
    psx.onResume = lambda: asyncio.create_task(run_test(psx))

    async def main():
        connect_task = asyncio.create_task(psx.connect("127.0.0.1", 20747))
        await asyncio.sleep(2.0)
        await run_test(psx)
        await connect_task

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
