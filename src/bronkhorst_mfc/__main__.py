"""Command line.

    python -m bronkhorst_mfc list [--port COM5 ...]       instruments on every port
    python -m bronkhorst_mfc stop rig.json                 all units in rig.json to zero
    python -m bronkhorst_mfc watchdog rig.json PID [MIN]   zero when PID exits
"""

import argparse
import json
from pathlib import Path

from .discovery import candidate_ports, discover
from .unit import Unit
from . import watchdog


def cmd_list(args):
    ports = args.port or None
    if ports is None:
        print("Ports:", ", ".join(f"{d} ({desc})" for d, _s, desc in candidate_ports()) or "none")
    nodes = discover(ports)
    if not nodes:
        print("No Bronkhorst instruments found. Power on? USB in? FlowSuite closed?")
        return
    print(f"{'port':8} {'addr':>4}  {'serial':18} {'tag':10} {'fluid':10} capacity")
    for n in nodes:
        u = Unit(n["port"], n["address"], verbose=False)
        i = u.info()
        print(f"{i['port']:8} {i['address']:>4}  {i['serial']:18} {i['usertag']:10} "
              f"{i['fluid']:10} {i['capacity']} {i['unit']}")


def cmd_stop(args):
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    watchdog.zero_all(config, "stop requested")


def main():
    p = argparse.ArgumentParser(prog="bronkhorst_mfc")
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("list", help="find instruments")
    pl.add_argument("--port", action="append", help="only scan this port (repeatable)")
    ps = sub.add_parser("stop", help="zero all units in a rig config")
    ps.add_argument("config")
    pw = sub.add_parser("watchdog", help="zero all units when a process exits")
    pw.add_argument("config")
    pw.add_argument("pid", type=int)
    pw.add_argument("minutes", type=float, nargs="?", default=45.0)
    args = p.parse_args()
    if args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "stop":
        cmd_stop(args)
    else:
        watchdog.run(args.config, args.pid, args.minutes)


if __name__ == "__main__":
    main()
