# bronkhorst-mfc

Python control of the Bronkhorst mass flow controllers (MFCs) in the GHE lab: find the units,
set a gas mix, check it was reached, log what actually flowed.

## Install

```
pip install git+https://github.com/Global-Health-Engineering/bronkhorst-mfc@v0.1.0
```

Use a tagged version and write it down with your data.

## First run

1. Power the MFCs, plug in their USB cables, **close Bronkhorst FlowSuite** (it locks the port).
2. List what is connected:

   ```
   python -m bronkhorst_mfc list
   ```

   Every unit with its port, address, serial number, active gas and capacity. The serial
   number is the one on the unit's label; it is how your scripts find the unit on any PC.
3. Copy [`examples/rig.example.json`](examples/rig.example.json) to `rig.json` and fill in
   one entry per gas, with the serial number and the gas the unit must run:

   ```json
   {"units": {
     "ch4": {"serial": "124M00030914TT", "fluid": "CH4"},
     "aux": {"serial": "<single unit>",  "fluid": "O2"}
   }}
   ```

   `fluid` is selected by name and checked on connect (`AIR`, `O2`, `CH4`, `CO2`, `N2`).

## Use from Python

```python
from bronkhorst_mfc import Rig

with Rig.from_config("rig.json") as rig:      # all units go to zero when the block ends
    rig.set_mix(10.0, ch4=0.02, aux=0.98)    # 10 ln/min total, 2 % CH4
    ok, measured, detail = rig.verify()      # waits 15 s, checks every unit
    print(detail, measured)                   # {'ch4': 0.2, 'aux': 9.8}
    rig.set_flows(ch4=0.1, aux=4.9)           # or flows per unit directly
```

A full sweep that logs to CSV: [`examples/sweep.py`](examples/sweep.py).

## Rules

- **Before the first flow, check by hand:** cylinder valves, which gas goes to which unit,
  and that the **outlet is open**. Software cannot see any of this.
- **The units keep flowing if your script crashes.** Always use `with Rig...`. For runs you
  leave alone, start the watchdog next to your script; it zeroes everything when the script
  exits or after the time limit:

  ```
  python -m bronkhorst_mfc watchdog rig.json <PID of your script> 45
  ```

- To stop everything by hand: `python -m bronkhorst_mfc stop rig.json`.
- Flows are **standard litres per minute at 20 °C / 1013.25 mbar** (check the unit `list`
  prints). Log the measured flow, not the setpoint.
- A setpoint above a unit's capacity raises an error. A unit that cannot reach its setpoint
  (empty cylinder, closed valve) does not complain; that is what `verify()` is for.
- Low setpoints (below about 2 % of a unit's capacity) are not controlled reliably.
- `None` in a reading means the unit did not answer, never zero flow.

More detail, symptoms and their causes: [`docs/OPERATING.md`](docs/OPERATING.md).

## Development

Branches `main` and `dev`; work on `dev`, pull request into `main`, tag `vX.Y.Z` on `main`.
Tests run without hardware: `python -m unittest discover tests`.
Origin: the GHE bench harness (`ecotrace-dmrv/measurements`, `tools/bench-harness`), 2026.
