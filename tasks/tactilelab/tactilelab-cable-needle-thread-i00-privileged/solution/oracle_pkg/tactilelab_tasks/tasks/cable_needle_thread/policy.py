"""cable_needle_thread scripted policy: grasp the cable out of its clips, align the tip with the hole and push it through.

    settle -> open -> reach the grasp point -> close (calibrated pinch) -> lift -> align (tip on the hole axis, a few cm before the
    wall, the hand leaning back by ``pitch_back_deg``) -> approach -> re-align from the measured tip -> closed-loop push segments ->
    hold -> verdict

The hand never enters the wall: with ``wall_clear: auto`` the pad midpoint stops where the front of the hand (its collision
spheres below the wall top, in the commanded orientation) is ``clear_margin`` before the wall's near face.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ...soft.plan import INTERP, Step, StepPolicy


def _rot(axis, angle: float) -> np.ndarray:
    a = np.asarray(axis, dtype=np.float64)
    a = a / np.linalg.norm(a)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * K @ K


class Policy(StepPolicy):
    """Step plan of the needle-threading task (numbers in ``cfg["policy"]``)."""

    def __init__(self, cfg: Dict[str, Any], task=None, planner=None, verbose: bool = False):
        if not isinstance(cfg, dict):  # (task, cfg) order
            cfg, task = task, cfg
        super().__init__(task, cfg, planner=planner, verbose=verbose)
        p = self.p
        self.pre_gap = float(p.get("pre_gap", 0.025))
        self.through = float(p.get("through", 0.085))
        self.tip_clip = float(p.get("tip_clip", 0.05))
        wc = p.get("wall_clear", "auto")
        self.wall_clear_auto = str(wc).lower() == "auto"
        self.wall_clear = 0.0 if self.wall_clear_auto else float(wc)
        self.clear_margin = float(p.get("clear_margin", 0.005))
        self.pitch_back = np.radians(float(p.get("pitch_back_deg", 10.0)))
        pdz = p.get("push_dz", 0.005)
        self.push_dz = None if pdz is None else float(pdz)
        self.push_mode = str(p.get("push_mode", "closed")).lower()
        self.seg = float(p.get("push_seg", 0.01))
        self.seg_corr = float(p.get("push_seg_corr", 0.012))
        self.seg_ticks = int(p.get("push_seg_ticks", 8))
        self.max_seg = int(p.get("push_max_seg", 30))
        self.push_in_dz = float(p.get("push_in_dz", 0.005))
        self.grasp_idle = int(p.get("grasp_idle", 60))

    def attach(self, task) -> None:
        """Bind the policy to its task (for runners that build the policy before the task)."""
        self.task = task

    def _mid_now(self) -> np.ndarray:
        return self.task.mid_frame()[0]

    def _clearance(self, goal: np.ndarray, R: np.ndarray, push: np.ndarray, top: float) -> float:
        if self.wall_clear_auto:
            return self.task.hand_front_at(goal, R, push, z_max=top) + self.clear_margin
        return self.wall_clear

    def build_plan(self) -> List[Step]:
        task = self.task
        c0, R0 = task.mid_frame()
        hole = task.hole_center()
        push = np.array([hole[0] - c0[0], hole[1] - c0[1], 0.0])
        push /= np.linalg.norm(push)
        up = np.array([0.0, 0.0, 1.0])
        tilt = _rot(np.cross(up, push), -self.pitch_back) if self.pitch_back else np.eye(3)
        R = tilt @ R0
        near, top = task.wall_near_x(), task.wall_top_z()
        self._log(
            f"plan: tip_len {task.tip_len:.3f}, pitch back {np.degrees(self.pitch_back):.0f} deg, wall_clear {'auto' if self.wall_clear_auto else self.wall_clear}"
        )
        if getattr(task, "wrist_warning", None):
            self._log(f"warning: {task.wrist_warning}")

        def target(dx_tip_to_wall: float, final: bool = False):
            """Pad midpoint that puts the (measured) tip on the hole axis ``dx_tip_to_wall`` before the wall plane."""

            def f():
                tip, mid = task.tip(), self._mid_now()
                off_nom = tilt @ (task.tip_len * push)
                off = off_nom + np.clip((tip - mid) - off_nom, -self.tip_clip, self.tip_clip)
                goal = np.array([hole[0] - dx_tip_to_wall, hole[1], hole[2]]) - off
                if final and self.push_dz is not None:
                    goal[2] = hole[2] + self.push_dz
                lim = near - self._clearance(goal, R, push, top)
                if goal[0] > lim:
                    if final:
                        self._log(f"push: the hand stops {1e3 * (goal[0] - lim):.1f} mm short of the tip target")
                    goal[0] = lim
                return goal

            return f

        z_up = float(c0[2])
        plan = [
            self.step_wait("settle", 10),
            self.step_hand("open", "open", post_idle=10),
            self.step_move("reach", INTERP, lambda: task.grasp_point(), lambda: R0, post_idle=10),
            self.step_hand("grasp", "close", post_idle=self.grasp_idle),
            self.step_move("lift", INTERP, lambda: np.array([*task.grasp_point()[:2], z_up]), lambda: R0, post_idle=15),
            self.step_move("align", INTERP, target(0.06), lambda: R, post_idle=10),
            self.step_move("approach", INTERP, target(self.pre_gap), lambda: R, post_idle=10),
            self.step_move("realign", INTERP, target(self.pre_gap), lambda: R, post_idle=10),
        ]
        if self.push_mode == "closed":
            plan.append(self._push_segment(hole, near, top, R, push, {"k": 0, "entered": False, "backoffs": 0}))
        else:
            plan.append(self.step_move("push", INTERP, target(-self.through, final=True), lambda: R, post_idle=10))
        return plan + [self.step_wait("hold", 20), self.verdict_step()]

    def _push_segment(
        self, hole: np.ndarray, near: float, top: float, R: np.ndarray, push: np.ndarray, st: dict
    ) -> Step:
        """One closed-loop push segment.  Before the tip enters the hole the pads move by the tip's y / z error to the hole
        axis (at most ``push_seg_corr``) and advance ``push_seg`` (correcting in place when the tip is about to touch the wall
        face off the hole, backing off 1 cm when it already rests on it).  Once the tip is past the near face the pads only
        advance (and settle on the hole axis + ``push_in_dz``).  Ends when the tip is ``through`` beyond the wall plane, when
        the hand reaches its wall clearance, or after ``push_max_seg`` segments."""
        task = self.task
        r = float(task.g["radius"])
        hw, hh = (0.5 * v for v in task.hole_size())
        margin = min(hw, hh) - r - 0.003
        st["k"] += 1

        def build():
            tip, mid = task.tip(), self._mid_now()
            st["tip0"] = tip.copy()
            e = np.array([0.0, hole[1] - tip[1], hole[2] - tip[2]])
            if not st["entered"] and tip[0] > near + 0.003:
                st["entered"] = True
                self._log(
                    f"push {st['k']}: the tip is in the hole (y/z off the axis {1e3 * e[1]:+.1f} / {1e3 * e[2]:+.1f} mm)"
                )
            dx = self.seg
            if st["entered"]:
                e = np.array([0.0, hole[1] - mid[1], hole[2] + self.push_in_dz - mid[2]])
                e[1:] = np.clip(e[1:], -self.seg_corr, self.seg_corr)
            else:
                err = float(np.max(np.abs(e[1:])))
                if tip[0] > near - r - 0.003 and err > margin and st["backoffs"] < 3:
                    dx = -0.01
                    st["backoffs"] += 1
                    self._log(
                        f"push {st['k']}: the tip rests on the wall {1e3 * e[1]:+.1f} / {1e3 * e[2]:+.1f} mm off the hole axis, backing off"
                    )
                elif tip[0] > near - r - 0.012 and err > margin:
                    dx = 0.0
                else:
                    dx = min(dx, max(0.004, near - r - 0.002 - tip[0])) if err > margin else dx
                e[1:] = np.clip(e[1:], -self.seg_corr, self.seg_corr)
            goal = mid + e + dx * push
            st["dz"] = float(e[2])
            lim = near - self._clearance(goal, R, push, top)
            st["at_lim"] = goal[0] >= lim - 1e-4
            goal[0] = min(goal[0], lim)
            st["target"] = goal
            return self.move_mid(INTERP, goal, R, name=f"push_{st['k']}")

        def done():
            tip = task.tip()
            if tip[0] >= hole[0] + self.through:
                self._log(f"push {st['k']}: the tip is {1e3 * (tip[0] - hole[0]):.0f} mm beyond the wall plane")
                return None
            if st["at_lim"] and tip[0] - st["tip0"][0] < 0.002 and abs(st["dz"]) < 0.001:
                self._log(
                    f"push {st['k']}: the hand is at its wall clearance, tip {1e3 * (tip[0] - hole[0]):+.0f} mm from the wall plane"
                )
                return None
            if st["k"] >= self.max_seg:
                self._log(f"push: {st['k']} segments, tip {1e3 * (tip[0] - hole[0]):+.0f} mm from the wall plane")
                return None
            return [self._push_segment(hole, near, top, R, push, st)]

        return Step(name=f"push_{st['k']}", build=build, on_done=done, post_idle=self.seg_ticks)


__all__ = ["Policy"]
