"""Wuji Hand 2.2 witness for essential_rotary_gait (privileged mode): regenerate /app/output/trajectory.npz.

Only finger position targets are produced (the six wrist targets stay at the locked pose). The controller is a
closed-loop two-finger gait: the index and middle fingers follow periodic joint-space orbits in antiphase (MCP
flexion, MCP abduction and PIP/DIP), so each finger alternately presses on the knob's rear rim and lifts off while the
other keeps contact (overlapping handoffs). The gait phase advances while the measured knob angle is short of the
goal; at the goal the targets freeze and the knob comes to rest inside the window. Then the fingers return to the
start grasp and a second orbit (found separately) turns the knob back by one revolution, and the targets freeze again
for the terminal hold. The orbit parameters were found by a cross-entropy search over gait parameters on the
simulator (authoring); this script contains no search and is deterministic.

Usage: python wuji_gen.py [--out <file>]   (needs the task tooling, /opt/tools, on PYTHONPATH); it rewrites
../solution/wuji/trajectory.npz byte for byte.
"""
import argparse
import math
import sys

import numpy as np

sys.path.insert(0, "/opt/tools")
from rcb_dexhand import Session  # noqa: E402

FORWARD = {"T": 41.9078, "psi": 2.1172, "i_m0": -0.1244, "i_Am": 0.2438, "i_a0": -0.0094, "i_Aa": 0.2776,
           "i_p0": -0.0754, "i_Ap": -0.4, "m_m0": -0.2696, "m_Am": 0.3198, "m_a0": -0.07, "m_Aa": 0.3038,
           "m_p0": 0.0376, "m_Ap": -0.0246}
REVERSE = {"T": 90.0, "psi": -0.0188, "i_m0": -0.1484, "i_Am": 0.2967, "i_a0": -0.0153, "i_Aa": 0.0369,
           "i_p0": -0.177, "i_Ap": 0.4, "m_m0": 0.0709, "m_Am": 0.2875, "m_a0": -0.0553, "m_Aa": 0.1215,
           "m_p0": 0.1783, "m_Ap": -0.0279}
STOP_FORWARD = 12.50   # rad: freeze when the knob reaches this angle (stage window 12.446..12.686)
STOP_REVERSE = 6.35    # rad: freeze when the knob comes back to this angle (window 6.163..6.403)
FREEZE_FORWARD = 12    # controls held after the forward freeze (the stage needs 5)
FREEZE_REVERSE = 40    # controls held after the reverse freeze (5 + terminal 25)
BLEND = 25             # controls from the frozen pose back to the start grasp before reversing
FINGERS = ((10, "i", 0.0), (14, "m", math.pi))  # (first action index: MCP flex, MCP abd, PIP, DIP; key; phase)


def orbit(base, p, k):
    """Finger targets of the periodic orbit at control k (other actuators keep the start grasp)."""
    row = base.copy()
    w = 2 * math.pi / p["T"]
    for off, key, phase in FINGERS:
        th = w * k + phase
        row[off + 0] = base[off + 0] + p[key + "_m0"] + p[key + "_Am"] * math.sin(th)
        row[off + 1] = base[off + 1] + p[key + "_a0"] + p[key + "_Aa"] * math.sin(th + p["psi"])
        row[off + 2] = base[off + 2] + p[key + "_p0"] + p[key + "_Ap"] * math.sin(th)
        row[off + 3] = base[off + 3] + p[key + "_Ap"] * 0.5 * math.sin(th)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/app/output/trajectory.npz")
    args = parser.parse_args()
    s = Session("essential_rotary_gait", hand="wuji")
    base = s.hold_action()  # the declared Wuji start grasp (wuji_reset.json) incl. its gravity feed-forward
    lo, hi = s.model.actuator_ctrlrange.T
    rows = []

    def emit(row):
        row = np.clip(row, lo, hi)
        row[:6] = base[:6]  # locked wrist
        rows.append(row.copy())
        return s.step(row)

    def gait(p, sign, stop, limit=6000):
        start = rows[-1].copy() if rows else base.copy()
        for k in range(limit):
            w = min(1.0, (k + 1) / (p["T"] / 2))  # ramp from the current command into the orbit
            target = orbit(base, p, k)
            if emit(start + (target - start) * w if w < 1 else target)["done"]:
                return False
            turn = s.features()["turn"]
            if (sign > 0 and turn >= stop) or (sign < 0 and turn <= stop):
                return True
        return False

    def freeze(n):
        last = rows[-1].copy()
        for _ in range(n):
            if emit(last)["done"]:
                break

    assert gait(FORWARD, +1, STOP_FORWARD), s.status()
    freeze(FREEZE_FORWARD)
    start = rows[-1].copy()
    for k in range(BLEND):
        emit(start + (base - start) * (k + 1) / BLEND)
    assert gait(REVERSE, -1, STOP_REVERSE), s.status()
    freeze(FREEZE_REVERSE)
    status = s.status()
    print({k: status[k] for k in ("success", "reason", "steps", "stage", "state_sha")})
    s.save_trajectory(np.array(rows), args.out)
    print(f"saved {len(rows)} wuji rows to {args.out}")


if __name__ == "__main__":
    main()
