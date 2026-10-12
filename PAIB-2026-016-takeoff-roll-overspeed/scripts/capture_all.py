"""Raw-socket full-firehose capture of every key=value line from PSX at
127.0.0.1:20747, with wall-clock timestamps -- used to diff the complete
variable set across a derate change and find which Q-code(s) carry the
derate selection itself (not just its downstream V-speed effect).
"""
import asyncio
import datetime

HOST = "127.0.0.1"
PORT = 20747
LOGFILE = "/tmp/claude-1000/-home-kronberg-psxhacks/14f85cf4-4177-4b10-b394-add6e88daf3a/scratchpad/all_traffic.log"


async def main():
    reader, writer = await asyncio.open_connection(HOST, PORT)
    writer.write(b"name=DERATEHUNT:Derate field hunt\n")
    await writer.drain()
    print(f"Connected to {HOST}:{PORT}, logging everything to {LOGFILE}")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        while True:
            line = await reader.readline()
            if not line:
                print("Connection closed by server")
                break
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            text = f"{ts}: {line.decode(errors='replace').rstrip()}"
            f.write(text + "\n")
            f.flush()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt as exc:
        raise SystemExit("Stopped by keyboard interrupt (Ctrl-C)") from exc
