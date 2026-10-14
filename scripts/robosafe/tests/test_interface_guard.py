#!/usr/bin/env python3
"""The RCB adapter serves RoboSafeBench under its control interface only: rcb_rsb.start refuses a key that asks for
another interface and an episode built under another (standard library only: RoboSafeBench is a stand-in here).

    python3 scripts/robosafe/tests/test_interface_guard.py
"""
import pathlib
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "shared/standard"))


class Ep:
    def __init__(self, interface):
        self.interface = interface


def fake_robosafe(build_as=None):
    pkg, verify = types.ModuleType("robosafe"), types.ModuleType("robosafe.verify")
    verify.start = lambda key: (None, None, Ep(build_as or dict(key).get("interface", "skill")))
    pkg.verify = verify
    sys.modules["robosafe"], sys.modules["robosafe.verify"] = pkg, verify


def refused(key) -> bool:
    try:
        rcb_rsb.start(key)
    except RuntimeError:
        return True
    return False


import rcb_rsb  # noqa: E402

checks = []
fake_robosafe()
checks.append(("a control key is served", not refused({"family": "f", "interface": "control"})))
checks.append(("a skill key is refused", refused({"family": "f", "interface": "skill"})))
checks.append(("a key without an interface is refused (RoboSafeBench's default is skill)", refused({"family": "f"})))
fake_robosafe(build_as="skill")
checks.append(("an episode built under skill is refused", refused({"family": "f", "interface": "control"})))
bad = 0
for name, ok in checks:
    print(("ok   " if ok else "FAIL ") + name)
    bad += not ok
print("all passed" if not bad else f"{bad} failed")
sys.exit(1 if bad else 0)
