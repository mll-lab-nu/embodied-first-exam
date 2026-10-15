"""Authoring controller for Wuji Hand 2.2: the Sharpa phase script with Wuji finger indices and fingertip geoms."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np

import demo
from runtime import Session

WUJI_ACT = {"thumb": list(range(6, 10)), "index": list(range(10, 14)), "middle": list(range(14, 18)),
            "ring": list(range(18, 22)), "pinky": list(range(22, 26))}
WUJI_TIPS = {"thumb": "thumb", "index": "index_finger", "middle": "middle_finger", "ring": "ring_finger",
             "pinky": "pinky"}
WUJI_CURLED = {"middle": [1.4, 0.0, 1.6, 1.2], "ring": [1.4, 0.0, 1.6, 1.2], "pinky": [1.4, 0.0, 1.6, 1.2]}


class WujiController(demo.Controller):
    tip_axis_sign = -1.0  # the Wuji tip mesh frame's z axis points back toward the palm

    def find_tips(self):
        return {f: self.m.geom(f"r_wuji_r_{n}_tip_sensor_frame_collision1").id for f, n in WUJI_TIPS.items()}

    pad_offset = 0.006

    def tip_point(self, d, finger, pad):
        """Tip mesh centre, or (pad=True) a point 6 mm toward the fingertip end (the mesh z axis points palmward)."""
        g = self.tip[finger]
        if not pad:
            return d.geom_xpos[g]
        return d.geom_xpos[g] - self.pad_offset * d.geom_xmat[g].reshape(3, 3)[:, 2]


def wuji_new_pick(c, q, spread=0.014, squeeze=-0.008, dz=0.003, clr_open=0.006, tilt=0.15, pad_offset=0.008):
    """Three-finger pick of the new cell: hand yaw aligned with the slot (fingers across the cell), thumb on the near
    side, index + middle on the far side spread along the slot axis. Closing turns the cell into line with the hand,
    so no turn is needed in the air."""
    A = WUJI_ACT
    c.pad_offset = pad_offset
    cell = c.body_pos("new_cell")
    Rr = c.d.xmat[c.m.body("remote").id].reshape(3, 3)
    yaw = float(np.arctan2(Rr[1, 0], Rr[0, 0]))
    axis = np.array([np.cos(yaw), np.sin(yaw), 0.0])
    across = np.array([-np.sin(yaw), np.cos(yaw), 0.0])
    R = demo.yaw_rotation(yaw - np.pi / 2)
    side = np.sign(R[:, 2] @ across) or 1.0
    up = np.array([0, 0, dz])
    down = np.array([0, 0, -1.0])

    def targets(clr):
        off = 0.007 + 0.008 + clr
        return {"thumb": cell - side * off * across + up,
                "index": cell + side * off * across + spread * axis + up,
                "middle": cell + side * off * across - spread * axis + up}

    axes = {"thumb": down * np.cos(tilt) + side * across * np.sin(tilt),
            "index": down * np.cos(tilt) - side * across * np.sin(tilt),
            "middle": down * np.cos(tilt) - side * across * np.sin(tilt)}
    var = list(range(6)) + A["thumb"] + A["index"] + A["middle"]
    seed = q.copy()
    seed[3:6] = c.wrist_euler_for(R)
    seed[A["middle"]] = [1.0, 0.0, 1.2, 0.8]
    q_open, e1, _ = c.solve(targets(clr_open), seed, var, R_hand=R, rot_weight=0.1, avoid=("table", "new_cell"),
                            avoid_margin=0.0008, pad=True, tip_axis=axes)
    q_close, e2, _ = c.solve(targets(squeeze), q_open, var, R_hand=R, rot_weight=0.1, avoid=("table",),
                             avoid_margin=0.0003, pad=True, tip_axis=axes)
    c.log(f"wuji new pick ik open={e1} close={e2}")
    above = q_open.copy()
    above[2] += 0.07
    c.execute(above, 90, "over the new cell")
    c.execute(q_open, 60, "three fingers beside the new cell")
    c.execute(q_close, 40, "pinch: the cell turns into line with the hand")
    c.hold(30, "stabilize the pinch")
    upq = q_close.copy()
    upq[2] += 0.07
    c.execute(upq, 60, "lift the new cell")
    return upq, q_open


def wuji_base_seed(c, R):
    seed = c.target.copy()
    seed[3:6] = c.wrist_euler_for(R)
    seed[WUJI_ACT["thumb"]] = [0.3, 0.0, 0.3, 0.3]
    seed[WUJI_ACT["index"]] = [1.0, 0.0, 1.2, 0.8]
    for f, v in WUJI_CURLED.items():
        seed[WUJI_ACT[f]] = v
    return seed


def install():
    demo.ACT = WUJI_ACT
    demo.CURLED = WUJI_CURLED
    demo.base_seed = wuji_base_seed


def make_demo(output, slack_rows=150, log=print, stop_after=None, new_pad_offset=0.008, new_boost=5.0,
              new_squeeze=-0.008, pick_kw=None):
    install()
    s = Session(hand="wuji")
    c = WujiController(s, log=log)
    # the generic solve() 'allow' filter matches Sharpa fingertip names; map it for Wuji
    orig_solve = c.solve

    def solve(tips, seed, variable, **kw):
        allow = kw.pop("allow", ())
        saved = c.hand_geoms
        c.hand_geoms = [g for g in saved if not any(c.m.geom(g).name.startswith(f"r_wuji_r_{WUJI_TIPS[f]}_tip")
                                                     or c.m.geom(g).name.startswith(f"r_wuji_r_{WUJI_TIPS[f]}_distal")
                                                     for f in allow)]
        try:
            return orig_solve(tips, seed, variable, **kw)
        finally:
            c.hand_geoms = saved

    c.solve = solve
    t0 = time.time()
    c.hold(25, "settle")
    c.pad_offset = 0.0
    q = demo.phase_open_cover(c)
    if stop_after != "open":
        q = demo.phase_old_to_tray(c, q)
    if stop_after not in ("open", "tray"):
        # weaker Wuji finger servos: deeper squeeze targets, stronger error boost, pad point near the tip end
        c.default_boost = new_boost
        c.release_slice = slice(6, 18)  # thumb + index + middle (Wuji)
        up, q_open = wuji_new_pick(c, q, squeeze=new_squeeze, pad_offset=new_pad_offset, **(pick_kw or {}))
        q = demo.phase_new_seat(c, up, q_open)
        c.pad_offset, c.default_boost = 0.0, 2.0
        q = demo.phase_close_cover(c, q)
        c.hold(120, "released hold")
    status = s.status()
    actions = np.asarray(s.actions)
    rows = np.concatenate([actions, np.repeat(actions[-1:], slack_rows, axis=0)])
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    s.save_trajectory(rows, out)
    np.savez_compressed(out.with_suffix(".phases.npz"), phases=np.asarray(c.phases + ["hold (slack)"] * slack_rows))
    summary = {"success": bool(s.success), "success_step": s.steps if s.success else None, "rows": int(len(rows)),
               "reason": status["reason"], "stage_steps": status.get("stage_steps"), "final_sha": s.state_sha(),
               "seconds": round(time.time() - t0, 1)}
    out.with_suffix(".live.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    log(json.dumps(summary, default=str))
    return s, c, summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--stop-after", choices=["open", "tray"])
    args = parser.parse_args()
    make_demo(args.out, stop_after=args.stop_after)
