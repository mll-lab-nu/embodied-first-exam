"""cable_route_channel scripted policy: pick the cable up segment by segment and press it into the slot.

For each pick (arc length ``s_k`` from the fixed end): above the cable -> descend -> pinch -> lift -> carry over the slot point
of the same arc length (the pads turn with the slot heading) -> lower to ``press_dz`` above the slot floor -> partial open ->
retreat.  With ``pick_mode: adaptive`` the pick points are read from the live cable when the pick starts (``Task.next_pick``:
mid-span between two clips, or on the hose hanging from the slot to the far post); a pick slot with no cable left on the
support is skipped.  ``release_gap`` releases with a partial open to that gel-face gap (the fully open fingers would sweep the
clips beside the slot); the picks descend with that gap too.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ...soft.plan import INTERP, MOTIONGEN, Step, StepPolicy


class Policy(StepPolicy):
    """Step plan of the cable-routing task (numbers in ``cfg["policy"]``)."""

    def __init__(self, cfg: Dict[str, Any], task=None, planner=None, verbose: bool = False):
        if not isinstance(cfg, dict):  # (task, cfg) order
            cfg, task = task, cfg
        super().__init__(task, cfg, planner=planner, verbose=verbose)
        p = self.p
        self.picks = [float(s) for s in p.get("picks", [0.08, 0.15, 0.21])]
        self.pick_mode = str(p.get("pick_mode", "adaptive"))
        self.max_picks = int(p.get("max_picks", len(self.picks)))
        self.pick_margin = float(p.get("pick_margin", 0.015))
        self.hover = float(p.get("hover", 0.07))
        self.lift = float(p.get("lift", 0.06))
        self.grip_dz = float(p.get("grip_dz", 0.026))
        self.press_dz = float(p.get("press_dz", self.grip_dz))
        self.release_gap = float(p.get("release_gap", 0.02))
        self.first_mode = INTERP if str(p.get("first_move", "motiongen")) == "interp" else MOTIONGEN
        self._s_prev = 0.0

    def attach(self, task) -> None:
        """Bind the policy to its task (for runners that build the policy before the task)."""
        self.task = task

    def _R_of(self, tan_xy) -> np.ndarray:
        n = np.array([-tan_xy[1], tan_xy[0], 0.0])
        return self.R_pinch(approach=(0.0, 0.0, -1.0), normal=n)

    def _pick_steps(self, k: int) -> List[Step]:
        task = self.task
        z_floor = task.table_z
        z_grip = z_floor + self.grip_dz
        state: Dict[str, Any] = {}

        def choose():
            """The pick's arc length, decided once when its first step starts (None: skip this pick)."""
            if "s" in state:
                return state["s"]
            if self.pick_mode == "adaptive":
                s = task.next_pick(
                    self._s_prev, self.pick_margin, self.grip_dz, self.release_gap if self.release_gap > 0.0 else 0.082
                )
                if s is None:
                    self._log(
                        f"pick {k}: no cable left on the support beyond s = {self._s_prev:.3f} (routed {task.routed():.3f} m): skipped"
                    )
                else:
                    self._log(f"pick {k}: s = {s:.3f} m on the live cable (routed {task.routed():.3f} m)")
            else:
                s = self.picks[k] if k < len(self.picks) else None
            state["s"] = s
            if s is not None:
                self._s_prev = float(s)
            return s

        def pick_target(dz):
            def f():
                s = choose()
                if s is None:
                    return None
                p, t = task.cable_point_at(s)
                state["p"], state["t"] = p, t
                return np.array([p[0], p[1], max(z_grip, p[2]) + dz])

            return f

        def pick_R():
            if "t" not in state:
                p, t = task.cable_point_at(choose())
                state["p"], state["t"] = p, t
            return self._R_of(state["t"])

        def place_target(z):
            def f():
                s = choose()
                if s is None:
                    return None
                c, t = task.centerline_point(s)
                state["c"], state["ct"] = c, t
                return np.array([c[0], c[1], z])

            return f

        def place_R():
            if "ct" not in state:
                c, t = task.centerline_point(choose())
                state["c"], state["ct"] = c, t
            return self._R_of(state["ct"])

        def hand(name, what):
            if what == "open" and self.release_gap > 0.0:
                base = self.step_hand(name, "close", gap=self.release_gap)  # partial open
            else:
                base = self.step_hand(name, what)
            build = base.build
            base.build = lambda: None if choose() is None else build()
            return base

        return [
            self.step_move(
                f"above{k}", self.first_mode if k == 0 else INTERP, pick_target(self.hover), pick_R, post_idle=10
            ),
            self.step_move(f"descend{k}", INTERP, pick_target(0.0), pick_R, post_idle=5),
            hand(f"pinch{k}", "close"),
            self.step_wait(f"settle{k}", 10),
            self.step_move(f"lift{k}", INTERP, pick_target(self.lift), pick_R, post_idle=5),
            self.step_move(f"carry{k}", INTERP, place_target(z_grip + self.lift), place_R, post_idle=5),
            self.step_move(f"press{k}", INTERP, place_target(z_floor + self.press_dz), place_R, post_idle=10),
            hand(f"release{k}", "open"),
            self.step_move(f"retreat{k}", INTERP, place_target(z_grip + self.hover), place_R, post_idle=10),
        ]

    def step_move(self, name, mode, pos_fn, R_fn, refine=None, tol=None, **kw) -> Step:
        """``StepPolicy.step_move`` whose target function may return None: the step is then idle-only (a skipped pick)."""
        step = super().step_move(name, mode, pos_fn, R_fn, refine=refine, tol=tol, **kw)
        build, on_done = step.build, step.on_done
        holder: Dict[str, bool] = {}

        def build2():
            holder["skip"] = pos_fn() is None
            return None if holder["skip"] else build()

        step.build = build2
        step.on_done = lambda: None if holder.get("skip") else on_done()
        return step

    def build_plan(self) -> List[Step]:
        self._s_prev = 0.0
        steps = [self.step_hand("open", "open")]
        n = self.max_picks if self.pick_mode == "adaptive" else len(self.picks)
        for k in range(n):
            steps += self._pick_steps(k)
        steps.append(self.step_wait("settle_end", 30))
        steps.append(self.verdict_step())
        return steps


__all__ = ["Policy"]
