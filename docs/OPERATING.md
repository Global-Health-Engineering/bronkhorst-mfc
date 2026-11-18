# Operating the Bronkhorst mass flow controllers

Written 2026-09-25 from three days of running the ecoTrace campaign-2 bench (biogas: the
dual unit on one USB cable, address 3 = CH4 or air, address 4 = CO2). Everything here was
observed on that rig; where a number is a measurement it says so. COM numbers are those of
the bench PC; on another PC use `python -m bronkhorst_mfc list`.

The code examples use the bench interface, `bronkhorst_mfc.MassFlowController`
(`set_air`, `set_biogas`); for any other gas mix use `Rig` (README). `cal.py` and
`_gas_watchdog.py` are the bench harness in `ecotrace-dmrv/measurements`; here the watchdog is
`python -m bronkhorst_mfc watchdog`.

Read the **safety rules** first: the MFCs are the only thing on the bench that can waste gas
or damage the sensors.

## The hardware

| | |
|---|---|
| Bus | One USB–RS485 converter, **COM131** (USB serial `2053367F3253`), propar protocol, driver `src/mfc.py` |
| Address 3 | CH4 **or** air — the same instrument; which gas it meters is a *software fluidset*, which gas actually flows is a *physical lever* |
| Address 4 | CO2 |
| Capacity, addr 3 | **21.51 ln/min on the air fluidset, 17.18 ln/min on the methane fluidset** (per-fluid) |
| Capacity, addr 4 | 14.97 ln/min CO2 |
| Units | **standard** litres per minute (`ls/min`), **20 °C / 1013.25 mbar** -- read off both instruments 2026-09-25 (dde 244 "Standard Volume Flow", dde 245 = 20.0 °C, dde 246 = 1.01325 bar). An earlier version of this file said "normal litres, 0 °C", which is 7.3 % off. |
| Setpoints on the wire | counts 0..32000 = 0..capacity of the *currently selected* fluid |

Biogas is made by blending: `set_biogas(flow, x)` sends `flow·x` to address 3 (methane
fluidset) and `flow·(1−x)` to address 4. So the ceiling depends on composition:
`v_max = min(17.18/x, 14.97/(1−x))` — 18 L/min works at 40–65 % CH4, pure CH4 tops out at 17.18.

## Safety rules — not preferences

1. **Never command flow until the human has confirmed the physical state for THIS block**, in
   their own words: lever position (air vs CH4), both cylinder valves, bubbler in/bypassed,
   **outlet open**. The fluidset you select in software changes nothing physically. On
   2026-09-02 a flow command with the lever in the wrong position vented ~120 L of methane.
2. **The outlet must be open before any flow.** On 2026-09-23 a gas block started while the
   outlet was still plugged from a leak test; the chain went to regulator pressure (~1.4 bar
   gauge), something cracked audibly, and the sensors' MP3V5010s (40 kPa max rating) sat at
   3.5× their limit for 80 s. Since then every gas block runs with a **pressure guard**.
3. **When in doubt, set both lines to zero first, ask second.**
4. **Never run `cal.py check` with the lever on CH4**: its flow-tracking step commands 2 L/min.
5. **Never ask the human to move the lever while a sweep is running.** Say when the MFC is
   closed.
6. **Bronkhorst FlowSuite holds COM131 exclusively while it is open.** If a script fails with
   `PermissionError ... COM131`, something else has the port — FlowSuite, or a stale Python
   process of yours. Find it (`Get-CimInstance Win32_Process`), do not retry blindly.

## Basic use from Python

```python
import sys, json; sys.path.insert(0, "src")          # from calibration/
from mfc import MassFlowController
cfg = json.load(open("config.json"))["mfc"]
m = MassFlowController(port=cfg["port"], air_only=cfg.get("air_only", False),
                       air_address=cfg.get("air_address"), verbose=False)

m.set_air(6.44)                 # air fluidset on addr 3, addr 4 set to 0
m.set_biogas(10.73, 0.55)       # methane fluidset on addr 3, blend with addr 4
ok, meas, detail = m.verify_setpoint()   # waits 15 s, checks within 5 % (floor 0.15)
flow, ratio = m.measured()      # total L/min and CH4 fraction; (None, None) = bus did not answer
m.stop()                        # BOTH setpoints to 0 — always in a finally block
```

- Constructing the class prints the fluidset table it verified (`air=0, methane=1` on this
  unit, cached in `.fluidset_cache.json`). The indices are **per instrument**; an older copy
  of this driver hardcoded them and silently metered air as methane. Trust the printout.
- `set_air` / `set_biogas` **raise** on a setpoint above capacity rather than clamping. That
  is deliberate; lower the flow.
- `measured()` returning `None` means "unknown", **not** zero. Never record it as zero flow.
- Only one process may hold COM131. Close the controller (let the script exit) before the
  next one starts.

## Running a calibration block

Use the harness, not raw setpoints: `python cal.py collect --label <condition>` runs the grid
in `config.json` (`experiment.flows_lpm`, `ch4_ratios`, `air_only`) and writes one CSV with
every sensor plus the MFC readback (`mfc_flow_lpm`, `mfc_ratio`) per row.

For gas, wrap it the way this campaign did (scripts in the 2026-09-22 session scratchpad,
`gasblock.py`; recreate them if the scratchpad is gone):

- **Deadman watchdog** — `python _gas_watchdog.py <collect_pid> <limit_min>`. The instruments
  HOLD their last setpoint if the controlling process dies; the watchdog zeroes both lines
  when the collect process disappears or the time limit expires. It saved gas twice.
- **Pressure guard** — tail the live CSV and kill collect if any sensor's `pressure_kpa`
  column exceeds 80 (it is ×0.1 kPa, so 8 kPa). A blocked outlet is then caught in seconds.

The harness rejects a point whose flow is not reached after 15 s (`SETPOINT NOT REACHED`,
recorded as `phase=rejected`). Read those messages; they are diagnoses:

| Symptom | Meaning (seen on this rig) |
|---|---|
| Every point reads ~65 % of setpoint, ratio 1.000 | the **CO2 line delivers nothing** — cylinder valve closed. Stop and tell the human. |
| Commanded 17, measured 0.02 | the **CH4 cylinder is empty** |
| Measured 0.0, valve output high | no supply pressure at all — gas not turned on |
| Measured 20.15 at a setpoint of 18, bubbler in line | overshoot after 15 s with the humidifier; transient, point rejected |

## Reading pressure from the MFC itself (useful for leak tests)

The FlexiFlow has live pressure sensors, but **not** under the names the propar database
suggests:

| Quantity | Read | Unit |
|---|---|---|
| Inlet pressure | `m.mfc_main.read(34, 0, propar.PP_TYPE_FLOAT)` | bar absolute (sags ~2.48 → 2.1 under flow) |
| Outlet pressure | `m.mfc_main.read(35, 0, propar.PP_TYPE_FLOAT)` | bar absolute |
| Measured flow | `read(33, 0, …)` = dde 205 | L/min |

**Decoys:** dde 178 "Pressure inlet" = 2.5 and dde 179 "Pressure outlet" = 1.0 never move
(stored nominal values); dde 143 answers nothing; dde 107/proc 113 parm 18 "barometer"
reads 1009 hPa, a stored sea-level-ish number. Zurich's real station pressure is ~966 hPa —
the outlet sensor reads 0.966 bar(a) with the line open, which is correct, not an offset.

**Leak test with the MFC:** block the section under test, feed 1 L/min, watch outlet
pressure rise, then set 0 and log the decay. A tight section climbs steadily; a leaking one
plateaus where the leak equals the feed. Stop feeding at +15 kPa gauge if sensors are in the
section. The sensors' own MP3V5010 channels see only what is downstream of a block; the MFC
sees the section it feeds, so between them any segment can be bisected.

## Gas bookkeeping

Integrate `mfc_flow_lpm × mfc_ratio` over the CSV rows (one sensor's rows = one per second)
for litres of CH4 used; `(1 − ratio)` for CO2. A 7-point block at 4–5 min per point is about
300 L of mix. Keep a ledger per cylinder in the runbook: a 10 L cylinder at 230 bar is
~2200 L usable CH4; CO2 is never the constraint (4 kg ≈ 2000 L).

## After every block

1. Confirm the MFC is closed by reading, not by assuming: `m.stop(); print(m.measured())`.
2. Tell the human the MFC is closed before they touch the lever or the chain.
3. Log the block (file, gas used, setpoints rejected) in the runbook and manifest.
