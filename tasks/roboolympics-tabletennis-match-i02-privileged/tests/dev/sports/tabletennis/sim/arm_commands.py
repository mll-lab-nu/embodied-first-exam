"""The one table-tennis simulator core of every play mode and action level (docs/benchmarks/roboolympics-modes.md).

Layers, bottom up:
  physics + referee + opponent   rcb_tt.Session, rally.Rally, match.Match (Match also holds the stroke planner the
                                 high-level plugin uses);
  arm command layer (this file)  the only source of the robot's joint targets (9: [base_x, base_y, q1..q7]): one
                                 command at a time - `traj` (joint position targets stamped with absolute control
                                 steps, optionally followed by another command), `slew` (every arm joint towards q at
                                 a fraction of its speed limit within its acceleration limit, rcb_tt.seek, the base
                                 towards q's base position with the bounded go-to generator, rcb_tt.base_goto) or
                                 `hold`; a command whose first used target jumps by more than one step's speed limit,
                                 or changes the velocity beyond the acceleration limit, from the target in force is
                                 rejected (the previous one goes on); at the end of a point the command falls back to
                                 the level's rest command;
  action plugin                  action_low.py (switch off: the player's commands go straight to this layer) or
                                 action_high.py (switch on: the paddle state at contact -> IK + stroke planner ->
                                 a `traj` command, then a slew back to the ready pose).
Live service and replay both drive the match only through Core.apply (the plugin) and Core.rt_advance.
"""
from __future__ import annotations

import numpy as np

import match
import rcb_tt
from rcb_tt import BASE_VMAX, CONTROL_DT, VEL_LIMIT

STEP_LIM = VEL_LIMIT * CONTROL_DT       # per control step and joint (m for the base axes, rad for the arm)


class Core(match.Match):
    """match.Match whose arm targets come from the command layer; `plugin` is action_low or action_high."""

    def __init__(self, level: int = 1, plugin=None, lv_override: dict | None = None):
        super().__init__(level, lv_override)
        if plugin is None:
            import action_high as plugin
        self.plugin = plugin
        self.n_rejected = 0
        self.cmd = self.rest_command()

    # ------------------------------------------------------------------ the command layer
    def rest_command(self):
        """What the robot does when no command is in force: the plugin's rest (hold, or a slew of the arm to the ready
        pose with the base going to its rest position at full speed)."""
        r = self.plugin.REST
        return None if r is None else {"type": "slew", "q": np.r_[self.base_rest, self.s.inst["q0"]], "speed": r,
                                       "base_speed": 1.0, "rest": True}

    def set_base_rest(self, b) -> list:
        """`move`: the base's rest position (where it goes whenever no stroke is under way; home again at each point).
        A rest slew in force (or queued after the stroke under way) heads there at once."""
        self.base_rest = np.clip(np.asarray(b, float), rcb_tt.BASE_LO, rcb_tt.BASE_HI)
        for c in (self.cmd, (self.cmd or {}).get("then")):
            if isinstance(c, dict) and c.get("type") == "slew" and c.get("rest"):
                c["q"] = np.r_[self.base_rest, c["q"][2:]]
        return [round(float(x), 4) for x in self.base_rest]

    def traj_active(self) -> bool:
        c = self.cmd
        return c is not None and c["type"] == "traj" and self.k - c["k0"] < len(c["q"])

    def _arm_target(self):
        c = self.cmd
        if c is not None and c["type"] == "traj":
            i = self.k - c["k0"]
            if i >= len(c["q"]) and c.get("then") is not None:
                self.cmd = c = c["then"]                    # e.g. the high level's return to the ready pose
            elif i < 0:
                return self.s._target.copy()
            else:
                return c["q"][min(i, len(c["q"]) - 1)].copy()
        tgt = self.s._target
        if c is None:
            return tgt.copy()
        vel = self._target_vel()                            # slew: the arm joint by joint (speed x its velocity
        arm, _ = rcb_tt.seek(tgt[2:], vel[2:], c["q"][2:],  # limit, its acceleration limit), the base by the generator
                             VEL_LIMIT[2:] * c["speed"], rcb_tt.ARM_ACC, self.s.JOINT_LOW[2:], self.s.JOINT_HIGH[2:])
        b, _, _ = rcb_tt.base_goto(tgt[:2], vel[:2], c["q"][:2], vmax=BASE_VMAX * c.get("base_speed", c["speed"]),
                                   a=self._target_acc()[:2])
        return np.r_[b, arm]

    def submit(self, cmd: dict) -> dict:
        """At the start of control step self.k: `cmd` (validated) becomes the command in force, or is rejected."""
        if cmd["type"] == "hold":
            self.cmd = None
            return {"command": "hold"}
        if cmd["type"] == "slew":
            self.cmd = {"type": "slew", "q": np.asarray(cmd["q"], float), "speed": float(cmd["speed"])}
            if cmd.get("base_speed") is not None:
                self.cmd["base_speed"] = float(cmd["base_speed"])
            if cmd.get("rest"):
                self.cmd["rest"] = True
            return {"command": "slew"}
        Q = np.asarray(cmd["q"], float)
        k0 = int(cmd["k0"])
        j0 = max(0, self.k - k0)
        if j0 >= len(Q):
            self.n_rejected += 1
            return {"rejected": f"stale: the trajectory's last row was for step {k0 + len(Q) - 1}; this is step {self.k}"}
        jump = np.abs(Q[j0] - self.s._target)
        if (jump > STEP_LIM).any():
            j = int(np.argmax(jump / STEP_LIM))
            self.n_rejected += 1
            return {"rejected": f"discontinuous: row {j0} (step {self.k}) moves joint {j + 1} by {jump[j]:.5f} rad from "
                                f"the target in force (limit {STEP_LIM[j]:.5f} per step); the previous command goes on",
                    "first_row_used": j0}
        held = k0 > self.k                                 # before K0 the target in force is held (at rest)
        why = rcb_tt.rows_problem(Q[j0:j0 + 1], self.s._target, np.zeros(rcb_tt.NQ) if held else self._target_vel())
        if why:
            self.n_rejected += 1
            return {"rejected": f"beyond the limits where it joins the target in force (row {j0}, step "
                                f"{max(self.k, k0)}): {why}; the previous command goes on", "first_row_used": j0}
        then = cmd.get("then")                             # copied: set_base_rest edits it, never the caller's row
        if isinstance(then, dict):
            then = dict(then, q=np.asarray(then["q"], float))
        self.cmd = {"type": "traj", "q": Q, "k0": k0, "then": then}
        return {"command": "traj", "first_row_used": j0, "rows_left": int(len(Q) - j0)}

    def rt_advance(self, n_steps: int):
        n0 = len(self.points)
        out = super().rt_advance(n_steps)
        if len(self.points) > n0:
            self.cmd = self.rest_command()                 # a command does not carry over to the next point
        return out

    def apply(self, dec: dict) -> dict:
        """A validated player command (live: when it takes effect; replay: at its logged step)."""
        return self.plugin.apply(self, dec)

    def command_state(self) -> dict | str:
        c = self.cmd
        if c is None:
            return "hold"
        if c["type"] == "slew":
            return {"type": "slew", "q": [round(float(x), 5) for x in c["q"]], "speed": c["speed"],
                    "base_speed": c.get("base_speed", c["speed"])}
        i = self.k - c["k0"]
        return {"type": "traj", "k0": c["k0"], "rows": int(len(c["q"])),
                "next_row": int(i), "rows_left": int(max(0, len(c["q"]) - max(i, 0)))}
