"""Authoring-only: oracle audit and negative variants, each graded by a fresh-process ``replay.py``.

    python tools/check_oracle.py --traj solution/trajectory.npz --out-dir <dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

OPEN_UNDER = np.array([0.0, 0.0, 0.0, 0, 0.0, -0.1, 0, 0, 0, -0.1, 0, 0, 0, -0.1, 0, 0, 0, 0, -0.1, 0, 0, 0])
RF = slice(6, 28)  # right fingers (sharpa layout: right stage 6, right fingers 22, left stage 6, left fingers 22)


def audit(actions):
    """Replay in-process: stage timeline, peak unsupported bin fall, vacuum displacement, deepest penetration."""
    s = Session()
    m, d, ch = s.model, s.data, s.checker
    stages, peak_fall, max_disp, deepest, max_press = {}, 0.0, 0.0, 0.0, 0.0
    s.reset()
    for i, row in enumerate(actions):
        s.step(row)
        st = s.status()
        stages.setdefault(int(st["stage"]), i + 1)
        _, _, deep, _, bin_contacts = ch.contacts(d)
        vel = np.empty(6)
        mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, ch.bin, vel, 0)
        if bin_contacts == 0:
            peak_fall = max(peak_fall, -float(vel[5]))
        max_disp = max(max_disp, st["body_displacement_m"])
        deepest = max(deepest, -deep)
        max_press = max(max_press, st["max_button_travel_m"])
        if s.done:
            break
    return {"success": s.success, "steps": s.steps, "first_control_at_stage": stages,
            "peak_unsupported_fall_m_s": peak_fall, "max_body_displacement_m": max_disp,
            "max_bin_vacuum_penetration_m": deepest, "max_button_travel_m": max_press, "state_sha": s.state_sha()}


def variants(actions, initial, info):
    stages = info["first_control_at_stage"]
    out = {"float32": actions.astype(np.float32).astype(np.float64)}
    out["nop"] = np.repeat(initial[None], 300, axis=0)
    out["nop_full_budget"] = np.repeat(initial[None], 3000, axis=0)
    out["truncated_after_removal"] = actions[: stages[1] + 20]
    out["reseated_but_still_held"] = actions[: stages[2] + 5]
    out["one_row_short"] = actions[: info["steps"] - 1]
    drop = actions.copy()
    k = stages[1] + 60  # mid-carry: the bin held about 5 cm above the counter, away from the vacuum
    for j in range(12):  # the hand opens and pulls out from under the bin, then the oracle rows resume
        drop[k + j, RF] = OPEN_UNDER
        drop[k + j, 2] -= 0.02 * min(j + 1, 4)
        drop[k + j, 0] -= 0.015 * (j + 1)
    out["drop_and_catch_mid_carry"] = drop
    # no release press: the right hand stays 6 cm above its poke during the press window, the rest unchanged
    nopress = actions.copy()
    a, b = 165, 420
    nopress[a:b, :6] = actions[a, :6]
    nopress[a:b, 2] = actions[a, 2] + 0.06
    out["no_release_press"] = nopress
    # knock: from the start, the right hand drops beside the vacuum and sweeps across it
    start = initial.copy()
    knock = []
    for i in range(60):
        row = start.copy()
        row[0], row[1], row[2] = 0.15, -0.30, start[2] - 0.33 * min(1, (i + 1) / 30)
        knock.append(row)
    for i in range(80):
        row = knock[-1].copy()
        row[1] = -0.30 + 0.6 * min(1, (i + 1) / 40)
        knock.append(row)
    out["knock_vacuum"] = np.asarray(knock)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--traj", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    actions, hand, _ = hands.read_trajectory(args.traj, widths={"sharpa": 56, "wuji": 52}, max_rows=3000,
                                             task="vacuum_bin_reseat")
    info = audit(actions)
    (out / "audit.json").write_text(json.dumps(info, indent=1, default=str) + "\n")
    print(json.dumps(info, default=str))
    initial = np.asarray(json.loads((HERE / "task.json").read_text())["initial_targets"][hand], dtype=float)
    table, procs = {}, []
    for name, rows in variants(actions, initial, info).items():
        path = out / f"{name}.npz"
        hands.write_trajectory(path, rows, hand=hand, task="vacuum_bin_reseat")
        result = out / f"{name}.json"
        procs.append((name, result, subprocess.Popen(
            [args.python, str(HERE / "replay.py"), "--task", "vacuum_bin_reseat", "--traj", str(path), "--out",
             str(result)], cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)))
        if len(procs) >= 2:
            n0, r0, p0 = procs.pop(0)
            p0.wait()
            table[n0] = r0
    for n0, r0, p0 in procs:
        p0.wait()
        table[n0] = r0
    summary = {}
    for name, result in table.items():
        r = json.loads(result.read_text())
        summary[name] = {k: r.get(k) for k in ("success", "reason", "steps", "stage", "failure_detail", "state_sha",
                                               "bad_trajectory")}
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    for name, r in summary.items():
        print(name, r["success"], r["reason"], r["steps"], r["stage"], r.get("failure_detail"))


if __name__ == "__main__":
    main()
