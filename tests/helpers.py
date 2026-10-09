"""Configurazioni e utilità comuni ai test."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FULL = {"terminal": "4675204", "rate_control": "4679013", "actuator": "4063T95A0", "flowmeter": "46211P40000",
        "valve": "853T04A55", "pump": "97055201", "nozzles": ["AFC11002"]}
VALVE_ONLY = {"terminal": "4675202", "flowmeter": "46211P40000", "valve": "853T04A55", "pump": "97055201",
              "nozzles": ["WRC110025"]}
BARE = {"terminal": "4675202", "nozzles": ["WRC110025"]}


def example_path(name: str) -> str:
    return os.path.join(ROOT, "examples", name)


def read_example(name: str) -> bytes:
    with open(example_path(name), "rb") as fh:
        return fh.read()
