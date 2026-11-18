"""A set of instruments used together: one role per gas.

Config (JSON), one entry per role. Identify each instrument by its serial
number (on the label; `python -m bronkhorst_mfc list` prints it):

    {
      "units": {
        "ch4": {"serial": "124M00030914TT", "fluid": "CH4"},
        "aux": {"serial": "M23xxxxxxx",    "fluid": "O2"}
      }
    }

`fluid` is selected by name on connect and checked. Instead of `serial` an
entry may give `port` and `address`, which only works on one PC.
"""

import json
import time
from pathlib import Path

from .discovery import discover, locate
from .unit import Unit


class Rig:
    def __init__(self, units, verbose=True):
        """`units`: dict role -> connected Unit."""
        self.units = units
        self.verbose = verbose

    @classmethod
    def from_config(cls, config, verbose=True):
        """Connect every unit in `config` (a dict or a path to a JSON file)."""
        if not isinstance(config, dict):
            config = json.loads(Path(config).read_text(encoding="utf-8"))
        entries = config["units"]
        found = None
        units = {}
        try:
            for role, entry in entries.items():
                if "serial" in entry:
                    if found is None:
                        found = discover(config.get("ports"))
                    port, address = locate(entry["serial"], found)
                else:
                    port, address = entry["port"], entry["address"]
                unit = Unit(port, address, label=role, verbose=verbose)
                if entry.get("fluid"):
                    unit.select_fluid(entry["fluid"])
                units[role] = unit
                if verbose:
                    print(f"{role}: {unit.serial} on {port} address {address}, "
                          f"fluid {unit.fluid()}, capacity {unit.capacity()} "
                          f"{unit.unit_name()}")
        except Exception:
            for unit in units.values():
                unit.stop()
            raise
        return cls(units, verbose)

    def __getitem__(self, role):
        return self.units[role]

    # -- setpoints ---------------------------------------------------------

    def set_flows(self, **flows):
        """Set every unit at once, e.g. set_flows(ch4=0.2, aux=9.8).

        Roles not named are set to 0, so a call always defines the whole mix.
        All setpoints are checked against capacity before any is written.
        """
        unknown = set(flows) - set(self.units)
        if unknown:
            raise KeyError(f"No unit for {sorted(unknown)}; have {sorted(self.units)}")
        counts = {role: unit.counts_for(flows.get(role, 0.0))
                  for role, unit in self.units.items()}
        for role, unit in self.units.items():
            unit._write_setpoint(counts[role])
            unit.flow_setpoint = flows.get(role, 0.0)

    def set_mix(self, total, **fractions):
        """Total flow split by volume fraction, e.g. set_mix(10, ch4=0.02, aux=0.98).

        Fractions must add up to 1. Roles not named get 0.
        """
        s = sum(fractions.values())
        if abs(s - 1.0) > 1e-6:
            raise ValueError(f"Fractions add up to {s}, not 1: {fractions}")
        self.set_flows(**{role: total * f for role, f in fractions.items()})

    def stop(self):
        """All units to zero."""
        for unit in self.units.values():
            unit.stop()

    # -- readback ----------------------------------------------------------

    def measured(self):
        """dict role -> measured flow; a value is None if that unit did not answer."""
        return {role: unit.measured() for role, unit in self.units.items()}

    def fractions(self, measured=None):
        """Measured volume fractions per role, or None if unknown or no flow."""
        m = self.measured() if measured is None else measured
        if any(v is None for v in m.values()):
            return None
        total = sum(m.values())
        if total < 1e-6:
            return None
        return {role: v / total for role, v in m.items()}

    def verify(self, settle_s=15.0, tol_frac=0.05, tol_floor=0.05):
        """Wait, then check every unit reached its setpoint.

        Returns (ok, measured, detail). An instrument that cannot reach a
        setpoint (empty cylinder, closed valve) holds its old value without
        complaint, so check after every change.
        """
        time.sleep(settle_s)
        m = self.measured()
        bad = []
        for role, unit in self.units.items():
            target = unit.flow_setpoint
            tol = max(tol_floor, abs(target) * tol_frac)
            if m[role] is None or abs(m[role] - target) > tol:
                bad.append(f"{role}: set {target:.3f}, measured {m[role]}")
        return (not bad), m, "; ".join(bad) or "all units at setpoint"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()
        return False
