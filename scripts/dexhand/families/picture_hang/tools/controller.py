"""Authoring-only closed-loop scripted controller for picture_hang (reads Session state, records open-loop rows).

Grasp: both palms squeeze the outer faces of the side rails above the frame's centre of mass (the frame hangs
between the palms like a pendulum), fingers lightly curled against the rails, thumbs tucked. The controller lifts the
frame, carries it to the wall with the D-ring pivots inside the hook capture window, slides both rings over their
hook saddles, lowers until the hooks carry the frame, opens the squeeze and withdraws. Corrections use only the
observed frame/ring poses; the deliverable is the list of rows that were sent (replayed open-loop by graders).

Usage: python tools/controller.py --hand sharpa --out rows.npz [--log log.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from runtime import Session  # noqa: E402

SHARPA_FINGERS = ["thumb_CMC_FE", "thumb_CMC_AA", "thumb_MCP_FE", "thumb_MCP_AA", "thumb_IP",
                  "index_MCP_FE", "index_MCP_AA", "index_PIP", "index_DIP",
                  "middle_MCP_FE", "middle_MCP_AA", "middle_PIP", "middle_DIP",
                  "ring_MCP_FE", "ring_MCP_AA", "ring_PIP", "ring_DIP",
                  "pinky_CMC", "pinky_MCP_FE", "pinky_MCP_AA", "pinky_PIP", "pinky_DIP"]
HOOK_Y = 0.255
HOOK_Z = 1.38
WALL_X = 0.74


THUMB = {"fe": 0.5, "aa": 0.35, "mcp": 1.0, "ip": 0.3}  # tucked Sharpa thumb (CMC flexion, abduction, MCP, IP)


def sharpa_pose(curl=0.0, thumb=1.0, tuck=None):
    tuck = THUMB if tuck is None else tuck
    v = dict.fromkeys(SHARPA_FINGERS, 0.0)
    v.update({"thumb_CMC_FE": -0.17 + (tuck["fe"] + 0.17) * thumb, "thumb_CMC_AA": tuck["aa"],
              "thumb_MCP_FE": tuck["mcp"] * thumb, "thumb_IP": tuck["ip"] * thumb})
    for f in ("index", "middle", "ring", "pinky"):
        v[f + "_MCP_FE"] = curl
        v[f + "_PIP"] = 0.3 * curl / 0.3 if curl else 0.0
        v[f + "_DIP"] = 0.15 * curl / 0.3 if curl else 0.0
    return np.array([v[k] for k in SHARPA_FINGERS])


def wuji_pose(curl=0.0, thumb=1.0, tuck=None):
    # Wuji per-finger joints: J0 flex (MCP), J1 abduction, J2 PIP, J3 DIP; thumb THJ0..3.
    v = np.zeros(20)
    v[0:4] = [0.3, 0.0, 0.4 * thumb, 0.3 * thumb]
    for k in range(4):
        base = 4 + 4 * k
        v[base:base + 4] = [curl, 0.0, curl, 0.5 * curl]
    return v


class Controller:
    DEFAULTS = dict(
        x0=-0.03, z0=-0.005, open_in=0.025, squeeze_in=0.058, lift=0.04, curl=0.3,
        window_z=1.3757, insert_ring_x=0.7325, rest_drop=0.016, release_out=0.0,
        k_z=0.08, k_pitch=0.08, k_roll=0.06, k_y=0.06, load_share=0.75,
    )

    def __init__(self, s: Session, params=None):
        self.s = s
        self.p = dict(self.DEFAULTS)
        self.p.update(params or {})
        self.tuck = {key: self.p.get("thumb_" + key, value) for key, value in THUMB.items()}
        self.pose = sharpa_pose if s.hand == "sharpa" else wuji_pose
        self.nf = (s.action_dim - 12) // 2
        # Commanded stage offsets shared by both hands (frame-level) and corrections.
        self.cmd = dict(x=self.p["x0"], y=0.0, z=self.p["z0"], squeeze=self.p["open_in"] - 0.03,
                        pitch=0.0, roll=0.0, curl=0.0, thumb=0.0)
        self.rows = []
        self.log = []

    # -------------------------------------------------------------- observations
    def obs(self):
        m, d = self.s.model, self.s.data
        rings = {sd: d.xpos[m.body(sd + "_d_ring").id].copy() for sd in "lr"}
        R = d.xmat[m.body("picture").id].reshape(3, 3)
        pitch = float(np.arctan2(R[0, 2], R[2, 2]))  # + = top toward the wall
        return rings, pitch

    # -------------------------------------------------------------- action
    def row(self):
        c = self.cmd
        r = np.zeros(self.s.action_dim)
        # left stage: inward = -y ; right stage: inward = +y
        r[0:6] = [c["x"], c["y"] - c["squeeze"], c["z"] + c["roll"], 0.0, c["pitch"], 0.0]
        r[6:12] = [c["x"], c["y"] + c["squeeze"], c["z"] - c["roll"], 0.0, c["pitch"], 0.0]
        fingers = self.pose(c["curl"], c["thumb"], self.tuck)
        r[12:12 + self.nf] = fingers
        r[12 + self.nf:] = fingers
        return np.clip(r, self.s.ctrl_lo, self.s.ctrl_hi)

    def send(self, tag=""):
        r = self.row()
        self.rows.append(r)
        self.s.step(r)
        if self.s.steps % 10 == 0 or self.s.done:
            f = self.s.features
            rings, pitch = self.obs()
            self.log.append(dict(t=self.s.steps, tag=tag, stage=self.s.checker.stage, reason=self.s.status()["reason"],
                                 origin=np.round(f["origin"], 4).tolist(), pitch=round(pitch, 4),
                                 roll=round(f["roll_deg"], 3), rings={k: np.round(v, 4).tolist() for k, v in rings.items()},
                                 threaded=f["threaded"], load=f["hook_load_share"], hand=f["hand_contacts"],
                                 hold=self.s.checker.hold, cmd={k: round(v, 4) for k, v in self.cmd.items()}))
        return self.s.done

    def ramp(self, seconds, tag, **targets):
        start = {k: self.cmd[k] for k in targets}
        n = max(1, round(seconds / self.s.control_dt))
        for i in range(1, n + 1):
            t = i / n
            t = t * t * (3 - 2 * t)
            for k, v in targets.items():
                self.cmd[k] = start[k] + (v - start[k]) * t
            if self.send(tag):
                return True
        return False

    def servo(self, seconds, tag, z_target=None, x_target=None, y_lock=True, pitch_lock=True, roll_lock=True,
              until=None, max_rate=0.0015):
        """Closed-loop corrections from the observed ring pivots and frame pitch."""
        n = max(1, round(seconds / self.s.control_dt))
        for _ in range(n):
            rings, pitch = self.obs()
            mean = (rings["l"] + rings["r"]) / 2
            if z_target is not None:
                self.cmd["z"] += float(np.clip(self.p["k_z"] * (z_target - mean[2]), -max_rate, max_rate))
            if x_target is not None:
                self.cmd["x"] += float(np.clip(self.p["k_z"] * (x_target - mean[0]), -max_rate, max_rate))
            if y_lock:
                self.cmd["y"] += float(np.clip(self.p["k_y"] * (0.0 - mean[1]), -max_rate, max_rate))
            if pitch_lock:
                self.cmd["pitch"] += float(np.clip(self.p["k_pitch"] * (0.0 - pitch), -0.004, 0.004))
            if roll_lock:
                dz = rings["l"][2] - rings["r"][2]
                self.cmd["roll"] += float(np.clip(-self.p["k_roll"] * dz, -max_rate, max_rate))
            if self.send(tag):
                return True
            if until is not None and until():
                return False
        return False

    # -------------------------------------------------------------- episode
    def run(self):
        p = self.p
        steps = [
            lambda: self.ramp(1.0, "approach", squeeze=p["open_in"], thumb=1.0),
            lambda: self.ramp(1.0, "squeeze", squeeze=p["squeeze_in"], curl=p["curl"]),
            lambda: self.ramp(1.0, "lift", z=self.cmd["z"] + p["lift"]),
            lambda: self.ramp(3.0, "carry", x=p["x0"] + 0.15, z=p["z0"] + 0.195),
            lambda: self.servo(2.0, "align", z_target=p["window_z"], until=self.aligned),
            lambda: self.servo(6.0, "insert", z_target=p["window_z"], x_target=p["insert_ring_x"],
                               until=self.inserted, max_rate=0.0004),
            lambda: self.servo(3.0, "lower", z_target=p["window_z"] - p["rest_drop"], x_target=p["insert_ring_x"],
                               pitch_lock=False, until=self.loaded, max_rate=0.0004),
            lambda: self.ramp(1.0, "release", squeeze=p["release_out"], curl=0.0),
            lambda: self.ramp(1.0, "withdraw", x=self.cmd["x"] + p.get("withdraw_dx", -0.08),
                              z=self.cmd["z"] + p.get("withdraw_dz", -0.05)),
            lambda: self.ramp(4.0, "hold"),
        ]
        for step in steps:
            if step():
                break
        return self.s.status()

    def aligned(self):
        rings, pitch = self.obs()
        mean = (rings["l"] + rings["r"]) / 2
        return (abs(mean[2] - self.p["window_z"]) < 0.0008 and abs(rings["l"][2] - rings["r"][2]) < 0.001
                and abs(mean[1]) < 0.0015 and abs(pitch) < 0.006)

    def inserted(self):
        f = self.s.features
        return all(f["threaded"].values())

    def loaded(self):
        f = self.s.features
        return all(f["threaded"].values()) and sum(f["hook_load_share"].values()) >= self.p["load_share"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--out")
    ap.add_argument("--log")
    ap.add_argument("--params", default="{}")
    args = ap.parse_args()
    s = Session(hand=args.hand)
    c = Controller(s, json.loads(args.params))
    st = c.run()
    print(json.dumps({k: v for k, v in st.items() if k != "features"}))
    for entry in c.log[-3:]:
        print(entry)
    if args.out:
        s.save_trajectory(np.array(c.rows), args.out)
    if args.log:
        Path(args.log).write_text("\n".join(json.dumps(e) for e in c.log) + "\n")


if __name__ == "__main__":
    main()
