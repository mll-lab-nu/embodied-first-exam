"""Scripted expert of ``cloth_fold_half``: the rolling carry.

The fingertips point along the fold line (``roll_approach_y`` = -1: from the +y side of the layout), the pads straddle
the middle of the flap's free edge and the whole hand turns about the fold line together with the flap, so the sheet
leaves the pinch through the pads' open side at every angle.  At ``roll_release_deg`` - before the inner finger reaches
the pinned half - the pinch opens a little (``roll_open_gap``), the hand slides out along the fold line and the flap falls
the rest of the way about its crease::

    open (to roll_approach_gap) -> clear -> pre-pinch -> slide in -> pinch -> roll_1 .. roll_N -> release (partial open)
    -> slide out -> settle -> verdict

Planned in the layout frame of the task (fold line along +y, flap toward -x) and turned into the world with the layout.
"""

from __future__ import annotations

from typing import List

import numpy as np

from ...soft.plan import INTERP, MOTIONGEN, Step, StepPolicy

__all__ = ["ClothFoldHalfPolicy"]


class ClothFoldHalfPolicy(StepPolicy):
    def build_plan(self) -> List[Step]:
        task, p = self.task, self.p
        in_dx = float(p.get("in_dx", 0.006))
        in_idle = int(p.get("in_idle", 120))
        pre_mode = int(p.get("pre_mode", 2))
        seg = int(p.get("arc_segments", 8))
        ay = float(p.get("roll_approach_y", -1.0))
        tilt = float(np.radians(float(p.get("roll_tilt_deg", 0.0))))
        phi_rel = float(np.radians(float(p.get("roll_release_deg", 120.0))))
        margin = float(p.get("roll_margin", 0.98))
        pre_dy = float(p.get("roll_pre_dy", 0.07))
        out_dy = float(p.get("roll_out_dy", 0.13))
        clear_dy = float(p.get("roll_clear_dy", 0.10))
        clear_dz = float(p.get("roll_clear_dz", 0.06))
        open_gap = float(p.get("roll_open_gap", 0.014))
        app_gap = p.get("roll_approach_gap", 0.02)
        Lr = task.layout_rot()
        to_l, to_w = task.to_layout, task.from_layout
        tip = to_l(task.flap_tip())
        root = to_l(task.fold_root())
        rel = tip - root
        r_tip = float(np.hypot(rel[0], rel[2]))
        phi0 = float(np.arctan2(rel[2], -rel[0]))
        y_mid = float(tip[1])
        nrm = lambda phi: np.array([np.sin(phi), 0.0, np.cos(phi)])  # noqa: E731  the flap's upper face, turning about +y
        A_at = lambda phi: (
            np.sin(tilt) * np.array([np.cos(phi), 0.0, -np.sin(phi)]) + ay * np.cos(tilt) * np.array([0.0, 1.0, 0.0])
        )  # noqa: E731
        R_at = lambda phi: lambda: self.R_pinch(approach=Lr @ A_at(phi), normal=Lr @ nrm(phi))  # noqa: E731
        arc = {"R": r_tip - in_dx}

        def at(phi: float, rad: float) -> np.ndarray:
            return np.array([root[0] - rad * np.cos(phi), y_mid, root[2] + rad * np.sin(phi)])

        mid0 = at(phi0, arc["R"])
        pre = mid0 - A_at(phi0) * pre_dy  # beside the flap, the fingertips short of its side edge

        def start_arc():
            c, _ = task.mid_frame()
            d = to_l(c) - root
            arc["R"] = float(np.hypot(d[0], d[2]))
            self._log(
                f"pinched at {np.round(c, 3).tolist()} (rel. to the fold line {np.round(d, 3).tolist()}); roll radius {arc['R']:.3f}"
            )
            return None

        def open_partial():
            return self.hand("close", task.set_gripper_gap(open_gap))

        phis = [phi0 + k / seg * (phi_rel - phi0) for k in range(1, seg + 1)]
        end = lambda: at(phi_rel, arc["R"] * margin)  # noqa: E731
        out = lambda: to_w(end() - A_at(phi_rel) * out_dy)  # noqa: E731
        home: dict = {}

        def clear_pos():
            c, R = task.mid_frame()
            home["R"] = R
            return np.asarray(c, dtype=np.float64) + Lr @ np.array([0.0, -ay * clear_dy, clear_dz])

        mode, converge = (MOTIONGEN, None) if pre_mode == 1 else (INTERP, True)
        self._log(
            f"flap tip {np.round(tip, 3).tolist()} root {np.round(root, 3).tolist()} (layout); phi0 {np.degrees(phi0):.1f} deg, radius {arc['R']:.3f}"
        )
        open_first = (
            self.step_hand("open", "open") if app_gap is None else self.step_hand("open", "close", gap=float(app_gap))
        )
        steps = [
            open_first,
            self.step_move("clear", INTERP, clear_pos, lambda: home["R"], post_idle=10, refine=0),
            self.step_move("pre_pinch", mode, lambda: to_w(pre), R_at(phi0), converge=converge, post_idle=60, refine=1),
            self.step_move("slide_in", INTERP, lambda: to_w(mid0), R_at(phi0), post_idle=in_idle, refine=3, tol=0.005),
            self.step_hand("pinch", "close"),
            self.step_wait("settle_pinch", 10, on_done=start_arc),
        ]
        for k, phi in enumerate(phis, 1):
            last = k == seg
            steps.append(
                self.step_move(
                    f"roll_{k}",
                    INTERP,
                    (lambda phi=phi: to_w(at(phi, arc["R"] * margin))),
                    R_at(phi),
                    refine=1 if last else 0,
                    post_idle=15 if last else 5,
                )
            )
        steps += [
            Step(name="release", build=open_partial, post_idle=20),
            self.step_move("slide_out", INTERP, out, R_at(phi_rel), refine=0, post_idle=5),
            *([self.step_hand("open", "open", post_idle=10)] if app_gap is None else []),
            self.step_wait("settle", int(p.get("final_settle", 90))),
            self.verdict_step(),
        ]
        return steps
