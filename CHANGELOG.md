# Changelog

## 0.1.0

- Extracted from the GHE bench harness (`ecotrace-dmrv/measurements`, `tools/bench-harness/calibration/src/mfc.py`).
- `Unit`: one instrument; fluid selected by name, fluidset index cached per instrument serial.
- `Rig`: any number of units, one role per gas, found by serial number on any COM port;
  `set_flows`, `set_mix`, `verify`, `measured`, `stop`.
- `python -m bronkhorst_mfc list | stop | watchdog`.
- `MassFlowController`: the bench's two-unit biogas interface (`set_air`, `set_biogas`), unchanged.
