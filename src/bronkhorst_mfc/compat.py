"""The two-instrument biogas interface of the GHE bench harness, on top of Unit.

Kept so existing scripts (`cal.py`, `runner.py`) keep working:

    m = MassFlowController(port="COM131")          # address 3 = CH4/air, 4 = CO2
    m.set_air(6.0); m.set_biogas(10.0, 0.55); m.measured(); m.stop()

New work should use `Rig`, which handles any number of gases.
"""

import time

from .unit import Unit


class MassFlowController:
    def __init__(self, port, air_only=False, air_address=None,
                 main_address=3, co2_address=4, verbose=True):
        self.port = port
        self.air_only = air_only
        self.main = Unit(port, air_address or (1 if air_only else main_address),
                         label="CH4/air", verbose=verbose)
        self.co2 = None if air_only else Unit(port, co2_address, label="CO2", verbose=verbose)
        if self.co2 is not None and "co2" not in self.co2.fluid().lower():
            raise IOError(f"The CO2 unit is on '{self.co2.fluid()}', not CO2. "
                          f"Set it to CO2 in FlowSuite before running.")
        self.flow_setpoint = 0.0
        self.ratio = 0.0
        self.main.select_fluid("air")
        if verbose:
            for u in (self.main, self.co2):
                if u is not None:
                    print(f"  {u.label}: {u.serial} fluid {u.fluid()} "
                          f"capacity {u.capacity()} {u.unit_name()}")

    def active_fluid_name(self):
        return self.main.fluid()

    def set_air(self, flow_lpm):
        self.main.select_fluid("air")
        counts = self.main.counts_for(flow_lpm)
        self.main._write_setpoint(counts)
        self.main.flow_setpoint = flow_lpm
        if self.co2 is not None:
            self.co2.stop()
        self.flow_setpoint, self.ratio = flow_lpm, 1.0

    def set_biogas(self, flow_lpm, ch4_ratio):
        if self.co2 is None:
            raise RuntimeError("Created with air_only=True: no CO2 unit to blend with.")
        if not 0.0 <= ch4_ratio <= 1.0:
            raise ValueError(f"ch4_ratio must be between 0 and 1, got {ch4_ratio}")
        # Fluid first (capacity is per fluid), then check both before writing either.
        self.main.select_fluid("ch4")
        c_main = self.main.counts_for(flow_lpm * ch4_ratio)
        c_co2 = self.co2.counts_for(flow_lpm * (1.0 - ch4_ratio))
        self.main._write_setpoint(c_main)
        self.co2._write_setpoint(c_co2)
        self.main.flow_setpoint = flow_lpm * ch4_ratio
        self.co2.flow_setpoint = flow_lpm * (1.0 - ch4_ratio)
        self.flow_setpoint, self.ratio = flow_lpm, ch4_ratio

    def max_total_flow(self, ch4_ratio):
        if self.co2 is None:
            return self.main.capacity()
        limits = []
        if ch4_ratio > 0:
            limits.append(self.main.capacity() / ch4_ratio)
        if ch4_ratio < 1:
            limits.append(self.co2.capacity() / (1.0 - ch4_ratio))
        return min(limits)

    def measured(self):
        """(total, ratio); (None, None) if the bus did not answer."""
        main = self.main.measured()
        if main is None:
            return None, None
        if self.co2 is None:
            return main, 1.0
        co2 = self.co2.measured()
        if co2 is None:
            return None, None
        total = main + co2
        return total, (main / total if total > 1e-7 else None)

    def measured_flow(self):
        return self.measured()[0]

    def measured_ratio(self):
        return self.measured()[1]

    def measured_temperature(self):
        return self.main.temperature()

    def verify_setpoint(self, settle_s=15.0, tol_frac=0.05, tol_floor=0.15):
        time.sleep(settle_s)
        measured = self.measured_flow()
        if measured is None:
            return False, None, "no response from the MFCs"
        tol = max(tol_floor, abs(self.flow_setpoint) * tol_frac)
        ok = abs(measured - self.flow_setpoint) <= tol
        return ok, measured, (f"commanded {self.flow_setpoint:.2f} L/min, "
                              f"measured {measured:.2f} (tolerance {tol:.2f})")

    def verify_flow_tracking(self, test_setpoint=2.0, settle_s=12.0, tol=0.5):
        """Flows a little AIR to check the unit is flow-controlling. Air only."""
        self.set_air(test_setpoint)
        time.sleep(settle_s)
        measured = self.main.measured()
        ok = measured is not None and abs(measured - test_setpoint) <= tol
        self.set_air(0)
        if not ok:
            print(f"  WARNING: commanded {test_setpoint}, measured {measured}. "
                  f"Pressure-control mode, stuck valve or no supply pressure?")
        return ok, measured

    def stop(self):
        self.main.stop()
        if self.co2 is not None:
            self.co2.stop()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()
        return False
