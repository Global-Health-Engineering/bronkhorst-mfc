"""Tests against a fake propar, no hardware needed:  python -m unittest discover tests"""

import sys
import tempfile
import types
import unittest
from pathlib import Path

# Fake propar: two ports, instruments with their own fluid tables.
TABLES = {
    ("COM1", 3): ["AiR", "CH4", "O2", "H2", "Ar", "He", "AiR", "CO2", "N2", "N2"],
    ("COM1", 4): ["N2", "CH4", "O2", "H2", "Ar", "He", "CH4", "CO2", "N2", "N2"],
    ("COM2", 3): ["N2", "AiR", "O2", "H2", "Ar", "He", "CH4", "CO2", "N2", "N2"],
}
SERIALS = {("COM1", 3): "S-CH4", ("COM1", 4): "S-CO2", ("COM2", 3): "S-AUX"}
CAPS = {"CH4": 17.18, "AiR": 21.51, "O2": 20.0, "CO2": 14.97, "N2": 21.0}
STATE = {k: {"fluidset": 0, "setpoint": 0} for k in TABLES}


class FakeInstrument:
    def __init__(self, port, address=128, **_):
        self.key = (port, address)

    def readParameter(self, p):
        s, table = STATE[self.key], TABLES[self.key]
        name = table[s["fluidset"]]
        return {24: s["fluidset"], 25: name, 21: CAPS[name], 92: SERIALS[self.key],
                115: "", 129: "ln/min", 142: 21.0,
                205: s["setpoint"] / 32000 * CAPS[name]}.get(p)

    def writeParameter(self, p, v):
        if p == 24:
            STATE[self.key]["fluidset"] = v

    @property
    def setpoint(self):
        return STATE[self.key]["setpoint"]

    @setpoint.setter
    def setpoint(self, v):
        STATE[self.key]["setpoint"] = v


class FakeMaster:
    def __init__(self, port, baud):
        self.port = port

    def get_nodes(self):
        return [{"address": a, "serial": SERIALS[(p, a)], "type": "F", "id": ""}
                for (p, a) in TABLES if p == self.port]

    def stop(self):
        pass


fake = types.ModuleType("propar")
fake.instrument, fake.master = FakeInstrument, FakeMaster
sys.modules["propar"] = fake

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import bronkhorst_mfc.discovery as discover_mod  # noqa: E402
import bronkhorst_mfc.unit as unit_mod  # noqa: E402
from bronkhorst_mfc import Rig, MassFlowController  # noqa: E402

discover_mod.candidate_ports = lambda: [("COM1", "", ""), ("COM2", "", "")]
unit_mod.time.sleep = lambda s: None
unit_mod.CACHE_PATH = Path(tempfile.mkdtemp()) / "fluidsets.json"

CONFIG = {"units": {"ch4": {"serial": "S-CH4", "fluid": "CH4"},
                    "co2": {"serial": "S-CO2", "fluid": "CO2"},
                    "aux": {"serial": "S-AUX", "fluid": "O2"}}}


class RigTests(unittest.TestCase):
    def setUp(self):
        for s in STATE.values():
            s.update(fluidset=0, setpoint=0)

    def test_three_gases_found_by_serial_and_fluid(self):
        rig = Rig.from_config(CONFIG, verbose=False)
        self.assertEqual(rig["ch4"].fluid(), "CH4")
        self.assertEqual(rig["co2"].fluid(), "CO2")
        self.assertEqual(rig["aux"].fluid(), "O2")
        self.assertEqual(rig["aux"].port, "COM2")

    def test_o2_does_not_match_co2(self):
        self.assertFalse(unit_mod.fluid_matches("o2", "CO2"))
        self.assertTrue(unit_mod.fluid_matches("air", "AiR"))

    def test_mix_and_readback(self):
        rig = Rig.from_config(CONFIG, verbose=False)
        rig.set_mix(10, ch4=0.02, aux=0.98)
        m = rig.measured()
        self.assertAlmostEqual(m["ch4"], 0.2, places=2)
        self.assertAlmostEqual(m["aux"], 9.8, places=2)
        self.assertAlmostEqual(m["co2"], 0.0)
        self.assertAlmostEqual(rig.fractions()["ch4"], 0.02, places=3)
        rig.stop()
        self.assertEqual(sum(rig.measured().values()), 0)

    def test_over_capacity_writes_nothing(self):
        rig = Rig.from_config(CONFIG, verbose=False)
        with self.assertRaises(ValueError):
            rig.set_flows(ch4=1.0, aux=50.0)
        self.assertEqual(rig.measured()["ch4"], 0)

    def test_air_on_single_unit(self):
        cfg = {"units": {"aux": {"serial": "S-AUX", "fluid": "AIR"}}}
        rig = Rig.from_config(cfg, verbose=False)
        self.assertEqual(rig["aux"].fluid(), "AiR")

    def test_missing_serial_names_what_was_seen(self):
        with self.assertRaises(IOError) as ctx:
            Rig.from_config({"units": {"x": {"serial": "NOPE"}}}, verbose=False)
        self.assertIn("S-CH4", str(ctx.exception))

    def test_compat_refuses_co2_unit_on_wrong_gas(self):
        with self.assertRaises(IOError):
            MassFlowController("COM1", verbose=False)   # address 4 starts on N2

    def test_compat_biogas(self):
        STATE[("COM1", 4)]["fluidset"] = 7               # CO2
        m = MassFlowController("COM1", verbose=False)
        m.set_biogas(10, 0.55)
        total, ratio = m.measured()
        self.assertAlmostEqual(total, 10, places=2)
        self.assertAlmostEqual(ratio, 0.55, places=3)
        m.stop()


if __name__ == "__main__":
    unittest.main()
