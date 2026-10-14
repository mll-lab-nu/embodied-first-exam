#!/usr/bin/env python3
"""Authoring tool: freeze the Wuji Hand 2.2 start of sweep_dustpan into assets/reset_wuji.npz (deterministic bytes).

The Wuji start keeps every arm, tool, debris and bristle coordinate and every arm target of the frozen (Sharpa) reset
bit for bit; only the 40 Wuji finger joints and their 40 targets are declared. The finger joints come from a grasp
formation in physics: from the frozen reset carried over to the Wuji composition by name, the Wuji fingers start open
(thumb swung clear of the shaft, other fingers neutral) and their targets ramp to the closing targets below in 0.3 s,
then rest 0.7 s, while the broom and the dustpan are re-set to their frozen poses every step (authoring only, so the
fingers close onto the frozen shafts). The rested finger joints become the start. The runtime then starts from them
with nothing holding the tools (no weld, applied force or scripted motion); runtime.Session._check_hand_reset refuses a
file that changes any frozen non-finger coordinate or target.

    PYTHONPATH=<family>:<scripts/dexhand/shared> python tools/build_wuji_reset.py   # writes assets/reset_wuji.npz
                                                                                      # and its manifest.json entry
Validation (w-wuji, 2026-10-14): 80 s hold of these targets without any failure until the 160,000-row horizon
(min 5 force-bearing grip contacts per tool, grip drift <= 4.4 mm, rotation <= 0.022 rad); hold replays deterministic
in two fresh processes. Targets chosen by a random search of closing targets (lowest grip creep, most contacts).
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import mujoco
import numpy as np

FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY))
from runtime import Session  # noqa: E402

# Closing targets per hand in vendor order: THJ0..3 (thumb CMC flexion, CMC abduction, MCP, IP), then FFJ0..3, MFJ0..3,
# RFJ0..3, LFJ0..3 (MCP flexion, MCP abduction, PIP, DIP).
TARGETS = {
    "l": [0.4, -0.2, 1.5, 1.5] + [1.5699, 0.0, 1.4, 1.2] * 4,  # dustpan (MCP 1e-4 inside the 1.57 bound: float32-safe)
    "r": [0.81396, -1.226907, 0.690919, 1.24506,  # broom
          1.196168, -0.085486, 1.991473, 1.323529, 1.531669, 0.096463, 2.016547, 0.724206,
          0.910529, -0.090424, 1.566791, 1.267014, 1.193769, 0.004004, 1.877283, 0.668485],
}
OPEN = [-1.1, -0.6, 0.0, 0.0] + [0.0] * 16
RAMP_STEPS, REST_STEPS = 600, 1400
KEYS = ("TH", "FF", "MF", "RF", "LF")


def finger_index(s, side):
    prefix = f"{side}_wuji_{side}_"
    return [s.actuator_names.index(prefix + f"{k}J{j}") for k in KEYS for j in range(4)]


def base_state(s):
    """The frozen reset carried over to the Wuji composition by name, Wuji fingers neutral."""
    m, d, saved = s.model, s.data, s._reset
    mujoco.mj_resetData(m, d)
    by_name = {str(n): saved["initial_qpos"][int(a):int(a) + int(k)]
               for n, a, k in zip(saved["joint_names"], saved["joint_qposadr"], saved["joint_qposdim"])}
    for j in range(m.njnt):
        if m.joint(j).name in by_name:
            adr = int(m.jnt_qposadr[j])
            d.qpos[adr:adr + len(by_name[m.joint(j).name])] = by_name[m.joint(j).name]
    mujoco.mj_forward(m, d)
    known = {str(n): float(v) for n, v in zip(saved["actuator_names"], saved["initial_ctrl"])}
    for i, name in enumerate(s.actuator_names):
        joint = int(m.actuator_trnid[i, 0])
        d.ctrl[i] = known.get(name, np.clip(d.qpos[m.jnt_qposadr[joint]], *s.ctrl_range[i]))


def form(s):
    m, d = s.model, s.data
    base_state(s)
    fingers = {side: finger_index(s, side) for side in ("l", "r")}
    for side, idx in fingers.items():
        d.qpos[m.jnt_qposadr[m.actuator_trnid[idx, 0]]] = OPEN
        d.ctrl[idx] = OPEN
    mujoco.mj_forward(m, d)
    tools = {}
    for name in ("broom", "dustpan"):
        j = int(m.body_jntadr[m.body(name).id])
        tools[name] = (int(m.jnt_qposadr[j]), int(m.jnt_dofadr[j]), d.qpos[int(m.jnt_qposadr[j]):int(m.jnt_qposadr[j]) + 7].copy())
    start, goal = d.ctrl.copy(), d.ctrl.copy()
    for side, idx in fingers.items():
        goal[idx] = np.clip(TARGETS[side], s.ctrl_range[idx, 0], s.ctrl_range[idx, 1])
    for k in range(RAMP_STEPS + REST_STEPS):
        d.ctrl[:] = start + min(1.0, (k + 1) / RAMP_STEPS) * (goal - start)
        mujoco.mj_step(m, d)
        for a, v, pose in tools.values():
            d.qpos[a:a + 7] = pose
            d.qvel[v:v + 6] = 0.0
    formed = {side: d.qpos[m.jnt_qposadr[m.actuator_trnid[idx, 0]]].copy() for side, idx in fingers.items()}
    base_state(s)
    for side, idx in fingers.items():
        d.qpos[m.jnt_qposadr[m.actuator_trnid[idx, 0]]] = formed[side]
    return d.qpos.copy(), goal


def write_npz(path, arrays):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in arrays.items():
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, value, allow_pickle=False)
            info = zipfile.ZipInfo(name + ".npy", date_time=(2026, 10, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, buffer.getvalue())


def main():
    s = Session(hand="wuji", allow_unsupported_hand=True)  # the composition without a declared start
    qpos, ctrl = form(s)
    m = s.model
    out = FAMILY / "assets" / "reset_wuji.npz"
    write_npz(out, {
        "initial_qpos": qpos.astype(np.float64), "initial_ctrl": ctrl.astype(np.float64),
        "joint_names": np.array([m.joint(j).name for j in range(m.njnt)]),
        "joint_qposadr": np.array([int(m.jnt_qposadr[j]) for j in range(m.njnt)], dtype=np.int64),
        "joint_qposdim": np.array([{0: 7, 1: 4}.get(int(m.jnt_type[j]), 1) for j in range(m.njnt)], dtype=np.int64),
        "actuator_names": np.array(s.actuator_names)})
    manifest_path = FAMILY / "assets" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["reset_wuji.npz"] = hashlib.sha256(out.read_bytes()).hexdigest()
    if "reset_wuji.npz" not in manifest["derivation"]:
        manifest["derivation"] += ("; reset_wuji.npz: the Wuji Hand 2.2 start (the frozen arm/tool/debris/bristle "
                                   "coordinates with the formed Wuji finger joints) and its holding motor targets")
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n")
    print(out, manifest["files"]["reset_wuji.npz"])


if __name__ == "__main__":
    main()
