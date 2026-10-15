"""Authoring controller: closed-loop palm pumping of the T handle, recorded as open-loop actuator rows.

The controller reads Session state (handle height, piston depth, pump pose) to place the palm over the T-handle
grip, then commands the wrist stage down and up through full strokes. Only motor targets are written; the
recorded rows are then replayed open-loop from the frozen reset (that replay is what is graded).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import Session  # noqa: E402


def smooth(a, b, n):
    """Cosine-eased interpolation from a to b over n controls (excludes a, includes b)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    t = (1 - np.cos(np.pi * np.arange(1, n + 1) / n)) / 2
    return a[None] + t[:, None] * (b - a)[None]


class Pumper:
    def __init__(self, session, params=None):
        self.s = session
        p = dict(
            palm_offset=(-0.0055, 0.0418),  # palm centroid relative to the wrist stage frame (x, y), palm-down mount
            palm_bottom=0.0256,             # palm surface below the wrist stage frame origin
            press_world_z=0.985,            # wrist stage world z at the bottom of a stroke
            top_world_z=1.215,              # wrist stage world z at the top of a stroke (handle at rest touches below)
            clear_world_z=1.32,             # wrist world z for approach/withdraw
            approach_n=60, descend_n=30, down_n=45, up_n=45, dwell_n=6, withdraw_n=40, hold_n=120,
            strokes=6, fingers=None,
        )
        p.update(params or {})
        self.p = p
        s = session
        self.origin = np.asarray(s.config["stage_origin"], float)
        self.rows = []
        self.target = s.initial_targets.copy()
        if p["fingers"] is not None:
            self.target[6:] = p["fingers"]

    def go(self, xyz_world, n, fingers=None):
        goal = self.target.copy()
        goal[:3] = np.asarray(xyz_world, float) - self.origin
        if fingers is not None:
            goal[6:] = fingers
        for row in smooth(self.target, goal, n):
            self.rows.append(row)
            self.s.step(row)
            if self.s.done:
                break
        self.target = goal

    def hold(self, n):
        for _ in range(n):
            self.rows.append(self.target.copy())
            self.s.step(self.target)
            if self.s.done:
                break

    def run(self):
        s, p = self.s, self.p
        m, d = s.model, s.data
        handle = d.geom_xpos[m.geom("t_handle").id].copy()
        xy = handle[:2] - np.asarray(p["palm_offset"])
        fingers = self.target[6:].copy()
        self.go([xy[0], xy[1], p["clear_world_z"]], p["approach_n"], fingers)
        self.go([xy[0], xy[1], p["top_world_z"]], p["descend_n"])
        if p.get("grip") is not None:
            # Wrap the fingers over the far side of the T-handle grip (a power grasp from above).
            self.go([xy[0], xy[1], p["top_world_z"]], p.get("grip_n", 25), np.asarray(p["grip"], float))
        for k in range(p["strokes"]):
            # Re-centre on the measured handle each stroke (closed loop on the simulated pump pose).
            # Push straight down over the pump's foot (closed loop on the simulated pump pose): pushing along a
            # leaning handle would lever the narrow-footed pump further over.
            base = d.xpos[m.body("pump").id].copy()
            xy = base[:2] - np.asarray(p["palm_offset"]) + np.asarray(p.get("xy_bias", (0.0, 0.0)))
            self.go([xy[0], xy[1], p["press_world_z"]], p["down_n"])
            self.hold(p["dwell_n"])
            self.go([xy[0], xy[1], p["top_world_z"]], p["up_n"])
            self.hold(p["dwell_n"])
            if s.done:
                break
        if p.get("grip") is not None:
            self.go([xy[0], xy[1], p["top_world_z"]], p.get("grip_n", 25), fingers)
        self.go([xy[0], xy[1], p["clear_world_z"]], p["withdraw_n"])
        self.hold(p["hold_n"])
        return np.asarray(self.rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hand", default="sharpa")
    parser.add_argument("--out")
    parser.add_argument("--params", default="{}")
    parser.add_argument("--extra-hold", type=int, default=100)
    args = parser.parse_args()
    s = Session(hand=args.hand)
    pumper = Pumper(s, json.loads(args.params))
    rows = pumper.run()
    status = s.status()
    print(json.dumps({k: status[k] for k in ("success", "reason", "steps", "strokes", "tire_gauge_pa", "stage",
                                             "failure_detail", "stroke_controls", "max_depth_m", "pump_tilt_rad",
                                             "pump_displacement_m")}, indent=1))
    if args.out and status["success"]:
        rows = np.vstack([rows, np.repeat(rows[-1:], args.extra_hold, axis=0)])
        s.save_trajectory(rows, args.out)
        check = Session(hand=args.hand).replay(rows)
        print("open-loop replay:", check["success"], check["reason"], check["steps"], len(rows))


if __name__ == "__main__":
    main()
