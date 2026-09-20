"""Launch several simulated devices (each = a real agent with simulated GPS) and control them from one prompt.

  python run_all.py                 # 3 devices matching the seeded demo data:
                                    #   DEV-001 drives a route, DEV-002 stays in Delhi, DEV-003 stays in Mumbai
  python run_all.py --server http://localhost:8000

Prompt commands:
  offline 1 | online 1     cut / restore the network of device #1 (its display keeps playing cached content)
  goto 2 mumbai            teleport device #2's GPS (pauses its route)
  move 2 / stop 2          resume / pause device #2's route
  status                   print each device's state
  quit
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.join(ROOT, "..", "device", "agent.py")

DEVICES = [
    # id, registration token, display port, GPS args
    ("DEV-001", "DEMO-REG-001", 8101, ["--route", "chandigarh,delhi,jaipur,mumbai", "--steps", "8", "--dwell", "6"]),
    ("DEV-002", "DEMO-REG-002", 8102, ["--gps", "fixed", "--place", "delhi"]),
    ("DEV-003", "DEMO-REG-003", 8103, ["--gps", "fixed", "--place", "mumbai"]),
]


def call(port, path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--count", type=int, default=len(DEVICES))
    ap.add_argument("--base-port", type=int, default=8101, help="display port of the first device (others follow)")
    args = ap.parse_args()
    offset = args.base_port - 8101

    procs = []
    for did, token, port, gps in DEVICES[: args.count]:
        procs.append(subprocess.Popen([sys.executable, AGENT, "--server", args.server, "--device-id", did,
                                       "--token", token, "--port", str(port + offset), *gps]))
    ports = [d[2] + offset for d in DEVICES[: args.count]]
    time.sleep(1.5)
    print(__doc__)
    for (did, _, port, _), p in zip(DEVICES[: args.count], ports):
        print(f"  {did}: display -> http://localhost:{p}/")
    try:
        while True:
            try:
                cmd = input("\nsim> ").strip().lower().split()
            except EOFError:
                time.sleep(3600)
                continue
            if not cmd:
                continue
            if cmd[0] in ("quit", "exit"):
                break
            if cmd[0] == "status":
                for p in ports:
                    try:
                        s = call(p, "/api/state")
                        print(f"  :{p} {s['device_id']} online={s['online']} zone={(s['zone'] or {}).get('name')} "
                              f"playing={[i['name'] for i in s['items']]} pos={s['position']}")
                    except Exception as e:
                        print(f"  :{p} unreachable ({e})")
                continue
            try:
                n = int(cmd[1]) - 1
                port = ports[n]
                body = {"offline": {"offline": True}, "online": {"offline": False}, "move": {"moving": True},
                        "stop": {"moving": False}, "goto": {"goto": cmd[2] if len(cmd) > 2 else ""}}[cmd[0]]
                print(" ", call(port, "/api/control", body))
            except (KeyError, IndexError, ValueError):
                print("  unknown command")
            except Exception as e:
                print("  failed:", e)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
