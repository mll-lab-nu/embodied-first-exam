"""Scripted expert of ``sleeve_pull_on_forearm``: pinch the pull tab of the cuff and pull the sleeve along the forearm.

The hand points down and forward by ``pinch_tilt_deg`` from the vertical and the pads close across the tab (both pads
outside the sleeve)::

    open -> pre-pinch (back along the tab's axis) -> slide in -> pinch -> closed-loop pulls (each sized from the cuff
    position measured when it starts) -> hold -> release -> retreat -> settle -> verdict

Policy numbers (``cfg["policy"]``): ``pre_dist``, ``pinch_depth`` (pad centre below the tab top), ``in_idle`` /
``pre_idle`` (IK convergence dwell), ``pull_steps`` / ``pull_max`` / ``pinch_overpull``, ``retreat``, ``final_settle``.
"""

from __future__ import annotations

from typing import List

import numpy as np

from ...soft.plan import INTERP, MOTIONGEN, Step, StepPolicy

__all__ = ["SleevePullOnForearmPolicy"]


class SleevePullOnForearmPolicy(StepPolicy):
    def pull_steps(self, d: np.ndarray, Rf) -> List[Step]:
        """Closed-loop pull: short moves along the pull direction, each sized from the cuff position measured when it
        starts.  The commanded position is integrated (not the live pose, whose orientation error would accumulate)."""
        task, p = self.task, self.p
        overpull = float(p.get("pinch_overpull", 0.015))
        pull_max = float(p.get("pull_max", 0.025))
        steps = []
        ref: dict = {}
        for k in range(int(p.get("pull_steps", 8))):

            def target(k=k):
                rem = task.cuff_remaining() + overpull
                move = float(np.clip(rem, 0.0, pull_max))
                if "c" not in ref:
                    ref["c"] = np.asarray(task.pad_mid(), dtype=np.float64)
                ref["c"] = ref["c"] + np.array([d[0], d[1], 0.0]) * move
                return (float(ref["c"][0]), float(ref["c"][1]), float(ref["c"][2]))

            steps.append(self.step_move(f"pull{k}", INTERP, target, Rf, post_idle=15, refine=0))
        return steps

    def build_plan(self) -> List[Step]:
        task, p = self.task, self.p
        pre_mode = int(p.get("pre_mode", 2))
        pre_dist = float(p.get("pre_dist", 0.14))
        depth = float(p.get("pinch_depth", 0.008))
        in_idle = int(p.get("in_idle", 200))
        pre_idle = int(p.get("pre_idle", 200))
        retreat = float(p.get("retreat", 0.09))
        d = task.pull_direction()
        d[2] = 0.0
        d /= max(np.linalg.norm(d), 1e-9)
        tilt_deg = float(p.get("pinch_tilt_deg", task.pinch_tilt_deg))
        t = np.radians(tilt_deg)
        R = self.R_pinch(
            approach=(float(np.sin(t)), 0.0, -float(np.cos(t))), normal=(float(np.cos(t)), 0.0, float(np.sin(t)))
        )
        Rf = lambda: R  # noqa: E731
        back = np.array([-np.sin(t), 0.0, np.cos(t)])  # up and behind: out along the approach axis (the tab's own axis)
        rim = task.rim_grip_point()
        # the targets follow the tab as it is now (the sleeve may still settle): evaluated when each step starts
        inn_now = lambda: np.asarray(task.rim_grip_point(), dtype=np.float64) - depth * back  # noqa: E731
        pre = lambda: tuple((inn_now() + pre_dist * back).tolist())  # noqa: E731
        inn = lambda: tuple(inn_now().tolist())  # noqa: E731
        end: dict = {}

        def remember():
            end["p"] = np.asarray(task.pad_mid(), dtype=np.float64)
            return None

        up = lambda: tuple((end["p"] + retreat * back).tolist())  # noqa: E731
        mode, converge = (MOTIONGEN, None) if pre_mode == 1 else (INTERP, True)
        self._log(
            f"tab top {np.round(rim, 3).tolist()}; pinch tilt {tilt_deg:.1f} deg; pull along {np.round(d, 2).tolist()}"
        )
        return [
            self.step_hand("open", "open"),
            self.step_move("pre_pinch", mode, pre, Rf, converge=converge, post_idle=pre_idle, refine=1),
            self.step_move("slide_in", INTERP, inn, Rf, post_idle=in_idle, refine=3, tol=0.006),
            self.step_hand("pinch", "close"),
            self.step_wait("settle_pinch", 10),
            *self.pull_steps(d, Rf),
            self.step_wait("hold", 5, on_done=remember),
            self.step_hand("release", "open", post_idle=20),
            self.step_move("retreat", INTERP, up, Rf, refine=0, post_idle=10),
            self.step_wait("settle", int(p.get("final_settle", 240))),
            self.verdict_step(),
        ]
