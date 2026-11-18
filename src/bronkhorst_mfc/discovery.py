"""Find Bronkhorst instruments on any COM port, by serial number.

COM numbers differ between PCs (COM131 on one laptop is COM5 on the next), so
instruments are identified by the serial number stored in each instrument,
the same one printed on its label.
"""

import propar
from serial.tools import list_ports


def candidate_ports():
    """All serial ports, as (device, usb_serial, description)."""
    return [(p.device, p.serial_number or "", p.description or "")
            for p in list_ports.comports()]


def scan_port(port):
    """Instruments on one port: list of dicts with address, serial, type, id.

    Empty list if the port cannot be opened or nothing answers.
    """
    try:
        master = propar.master(port, 38400)
    except Exception:
        return []
    try:
        nodes = master.get_nodes()
    except Exception:
        nodes = []
    finally:
        try:
            master.stop()
        except Exception:
            pass
    return [{"port": port, "address": n["address"], "serial": str(n["serial"]).strip(),
             "type": n.get("type"), "id": n.get("id")} for n in nodes]


def discover(ports=None):
    """Scan `ports` (default: every serial port) and return all instruments found.

    Scanning opens each port briefly. A microcontroller board on another port
    may reset when its port is opened; pass `ports` to limit the scan.
    """
    found = []
    for device, usb_serial, _desc in (candidate_ports() if ports is None
                                      else [(p, "", "") for p in ports]):
        for node in scan_port(device):
            node["usb_serial"] = usb_serial
            found.append(node)
    return found


def locate(serial, found=None, ports=None):
    """(port, address) of the instrument with this serial number; raises if absent."""
    found = discover(ports) if found is None else found
    for node in found:
        if node["serial"] == serial or node["serial"].endswith(serial):
            return node["port"], node["address"]
    seen = ", ".join(f"{n['serial']} ({n['port']}:{n['address']})" for n in found) or "none"
    raise IOError(f"Instrument {serial} not found. Instruments seen: {seen}. "
                  f"Check power and USB, and close FlowSuite (it locks the port).")
