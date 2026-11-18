"""Example sweep: methane at low fractions in air or O2, logged to CSV.

    python examples/sweep.py rig.json out.csv

Edit TOTALS, CH4_FRACTIONS and DWELL_S below. Each point: set the mix, check it
was reached, then log measured flows once per second for DWELL_S seconds.
"""

import csv
import sys
import time
from datetime import datetime, timezone

from bronkhorst_mfc import Rig

TOTALS = [2.0, 5.0, 10.0]            # total flow, ln/min
CH4_FRACTIONS = [0.0, 0.01, 0.02, 0.04]
DWELL_S = 60


def main(config_path, out_path):
    with Rig.from_config(config_path) as rig, open(out_path, "w", newline="") as f:
        roles = list(rig.units)
        w = csv.writer(f)
        w.writerow(["time_utc", "total_set", "ch4_frac_set", "point_ok"]
                   + [f"{r}_set" for r in roles] + [f"{r}_measured" for r in roles])
        for total in TOTALS:
            for x in CH4_FRACTIONS:
                rig.set_mix(total, ch4=x, aux=1 - x)
                ok, _m, detail = rig.verify(settle_s=15)
                print(f"{total} ln/min, CH4 {x:.0%}: {detail}")
                for _ in range(DWELL_S):
                    m = rig.measured()
                    w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                total, x, ok]
                               + [rig[r].flow_setpoint for r in roles]
                               + ["" if m[r] is None else m[r] for r in roles])
                    f.flush()
                    time.sleep(1)
    print("done, all units at zero")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
