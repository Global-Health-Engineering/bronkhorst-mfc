"""Deadman watchdog: zero every unit when your script stops or a time limit passes.

The instruments HOLD their last setpoint. If a sweep script crashes or is
killed, gas keeps flowing. Start this next to any run you leave alone:

    python -m bronkhorst_mfc watchdog rig.json <pid of your script> [minutes]

It does not touch the serial ports while your script runs; it opens them only
to zero the units after the script is gone.
"""

import json
import os
import sys
import time
from pathlib import Path

import propar

from .discovery import discover, locate


def pid_alive(pid):
    if os.name == "nt":
        import subprocess
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                             capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def zero_all(config, reason):
    print(f"WATCHDOG: {reason} -- zeroing all units", flush=True)
    for attempt in range(10):
        try:
            targets = _targets(config)
            for port, address in targets:
                propar.instrument(port, address).setpoint = 0
            time.sleep(2)
            flows = [propar.instrument(p, a).readParameter(205) for p, a in targets]
            print(f"WATCHDOG: measured now {flows}", flush=True)
            if all((f or 0) < 0.05 for f in flows):
                return True
        except Exception as exc:
            print(f"WATCHDOG: attempt {attempt + 1} failed ({exc})", flush=True)
            time.sleep(3)
    print("WATCHDOG: COULD NOT CONFIRM ZERO FLOW -- CLOSE THE CYLINDER VALVES BY HAND",
          flush=True)
    return False


def _targets(config):
    found = None
    out = []
    for entry in config["units"].values():
        if "serial" in entry:
            found = discover(config.get("ports")) if found is None else found
            out.append(locate(entry["serial"], found))
        else:
            out.append((entry["port"], entry["address"]))
    return out


def run(config_path, pid, limit_min=45.0):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    limit_s, start = 60 * limit_min, time.time()
    print(f"watchdog armed: pid {pid}, limit {limit_min:.0f} min", flush=True)
    while True:
        time.sleep(5)
        if not pid_alive(pid):
            time.sleep(3)   # let the script's own stop() run first
            zero_all(config, f"process {pid} is gone")
            return
        if time.time() - start > limit_s:
            zero_all(config, "time limit reached; investigate before restarting")
            return


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]) if len(sys.argv) > 3 else 45.0)
