"""One Bronkhorst instrument: fluid selection, setpoints, readback.

Lessons from the GHE bench that this module encodes (each one cost data once):

* The fluidset INDEX differs per instrument. On one unit 0 = air, on another
  0 = N2. A fluid is therefore always selected by NAME, and the index found
  for it is cached per instrument serial number.
* Capacity is per fluid (one unit: 21.51 ln/min on air, 17.18 on CH4). It is
  read after the fluid is selected, never reused across fluids.
* A setpoint above capacity raises instead of being clamped to full scale.
* A failed read returns None, never 0: zero flow and "no answer" must stay
  distinguishable.
* The instrument HOLDS its last setpoint if your script dies. Use the unit or
  rig as a context manager, and run the watchdog for unattended runs.
"""

import json
import time
from pathlib import Path

try:
    import propar
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install the Bronkhorst driver: pip install propar") from exc


# propar parameter (DDE) numbers
P_SETPOINT = 9           # 0..32000 = 0..capacity
P_CAPACITY = 21          # capacity of the active fluid
P_FLUIDSET = 24          # index of the active fluid calibration (read/write)
P_FLUID_NAME = 25        # name of the active fluid
P_SERIAL = 92            # instrument serial number
P_USERTAG = 115          # free text, set in FlowSuite (e.g. "CH4")
P_CAPACITY_UNIT = 129    # e.g. "ln/min"
P_TEMPERATURE = 142
P_MEASURED = 205         # measured flow, capacity unit

FULL_SCALE = 32000
FLUIDSET_SLOTS = 10
CACHE_PATH = Path.home() / ".bronkhorst_mfc" / "fluidsets.json"

# Spellings instruments use for the same gas. Matching is on lower case.
FLUID_ALIASES = {
    "air": ("air",),
    "ch4": ("ch4", "methane"),
    "co2": ("co2", "carbon dioxide"),
    "o2": ("o2", "oxygen"),
    "n2": ("n2", "nitrogen"),
}


def fluid_matches(wanted, name):
    """True if the instrument's fluid `name` is the gas `wanted`.

    "o2" must not match "co2", so an alias matches only as the whole name or
    as a word inside it.
    """
    name = (name or "").strip().lower()
    for alias in FLUID_ALIASES.get(wanted.lower(), (wanted.lower(),)):
        if name == alias or alias in name.replace("-", " ").split():
            return True
    return False


class Unit:
    """One instrument, addressed by port and propar address."""

    def __init__(self, port, address, label=None, verbose=True):
        self.port = port
        self.address = address
        self.verbose = verbose
        self.inst = propar.instrument(port, address)
        self.serial = (self.read(P_SERIAL) or "").strip()
        self.usertag = (self.read(P_USERTAG) or "").strip()
        self.label = label or self.usertag or self.serial or f"{port}:{address}"
        self.flow_setpoint = 0.0
        self._fluid_index = {}

    # -- bus ---------------------------------------------------------------

    def read(self, param, tries=4):
        """Read a parameter; None if the instrument does not answer."""
        for _ in range(tries):
            try:
                value = self.inst.readParameter(param)
            except Exception:
                value = None
            if value is not None:
                return value
            time.sleep(0.1)
        return None

    def _write_setpoint(self, counts):
        counts = int(max(0, min(FULL_SCALE, counts)))
        try:
            self.inst.setpoint = counts
        except IndexError:
            # propar sometimes fails to parse the acknowledgement of a write
            # that was applied correctly.
            pass

    # -- fluid -------------------------------------------------------------

    def fluid(self):
        """Name of the active fluid as the instrument reports it."""
        return (self.read(P_FLUID_NAME) or "").strip()

    def capacity(self):
        """Capacity under the active fluid; raises if unreadable."""
        cap = self.read(P_CAPACITY)
        if cap is None:
            raise IOError(f"{self.label}: no answer on {self.port} address "
                          f"{self.address}. Check power, cable, and that "
                          f"FlowSuite or another script is not holding the port.")
        return cap

    def unit_name(self):
        return (self.read(P_CAPACITY_UNIT) or "").strip()

    def select_fluid(self, wanted):
        """Make `wanted` (e.g. "air", "O2", "CH4") the active fluid, by name.

        Raises if the instrument has no such calibration or the switch did not
        take. Never guesses an index.
        """
        if fluid_matches(wanted, self.fluid()):
            return
        index = self._find_index(wanted)
        try:
            self.inst.writeParameter(P_FLUIDSET, index)
        except Exception as exc:
            raise IOError(f"{self.label}: could not select {wanted}: {exc}") from exc
        time.sleep(1.0)   # the instrument re-ranges
        if not fluid_matches(wanted, self.fluid()):
            raise IOError(f"{self.label}: asked for {wanted}, instrument reports "
                          f"'{self.fluid()}'. Do not run until this is resolved.")

    def _find_index(self, wanted):
        cache = _load_cache()
        key = self.serial or f"{self.port}:{self.address}"
        cached = cache.get(key, {}).get(wanted.lower())
        if cached is not None:
            return cached

        # Scan the slots by writing the index and reading the name back. These
        # writes may go to EEPROM, so the result is cached and scanned once.
        original = self.read(P_FLUIDSET)
        table = {}
        for index in range(FLUIDSET_SLOTS):
            try:
                self.inst.writeParameter(P_FLUIDSET, index)
                time.sleep(0.2)
                table[index] = (self.inst.readParameter(P_FLUID_NAME) or "").strip()
            except Exception:
                continue
        if original is not None:
            try:
                self.inst.writeParameter(P_FLUIDSET, original)
                time.sleep(0.2)
            except Exception:
                pass

        if self.verbose:
            listing = " ".join(f"{i}={n}" for i, n in table.items())
            print(f"  {self.label} fluid table: {listing}")
        found = next((i for i, n in table.items() if fluid_matches(wanted, n)), None)
        if found is None:
            raise IOError(f"{self.label} has no '{wanted}' calibration "
                          f"(table: {table}). Pick another unit or fluid.")
        cache.setdefault(key, {})[wanted.lower()] = found
        _save_cache(cache)
        return found

    # -- flow --------------------------------------------------------------

    def counts_for(self, flow):
        """Setpoint counts for `flow` under the active fluid; raises if over capacity."""
        if flow < 0:
            raise ValueError(f"{self.label}: negative setpoint {flow}")
        cap = self.capacity()
        if flow > cap:
            raise ValueError(f"{self.label}: {flow:.3f} exceeds capacity "
                             f"{cap} {self.unit_name()} for {self.fluid()}.")
        return flow / cap * FULL_SCALE

    def set_flow(self, flow):
        """Command `flow` in the capacity unit (normally ln/min or ls/min)."""
        counts = self.counts_for(flow)
        self._write_setpoint(counts)
        self.flow_setpoint = flow

    def measured(self):
        """Measured flow, or None if the instrument did not answer."""
        return self.read(P_MEASURED)

    def temperature(self):
        return self.read(P_TEMPERATURE)

    def stop(self):
        self._write_setpoint(0)
        self.flow_setpoint = 0.0

    def info(self):
        """Dict for listings and logs."""
        return {
            "port": self.port, "address": self.address, "serial": self.serial,
            "usertag": self.usertag, "fluid": self.fluid(),
            "capacity": self.read(P_CAPACITY), "unit": self.unit_name(),
        }

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()
        return False


def _load_cache():
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache):
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except OSError:
        pass
