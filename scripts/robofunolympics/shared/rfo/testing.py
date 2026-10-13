"""Helpers for the families' referee tests (scripts/robofunolympics/tests/): run a world under a scripted driver, or
set the simulator's state by hand to show that a referee says yes to the right thing and no to the wrong ones. These
"injections" (teleporting a ball, giving the robot a velocity) are referee tests, not solutions: an agent has no such
access to the graded episode."""
from __future__ import annotations

import numpy as np

from rfo import load_task
from rfo.world import Actions, World


def make(family: str, **params):
    """(world, actions) of a family with its default parameters (overridden by params)."""
    w = World(load_task(family), {"params": params} if params else None)
    return w, Actions(w.robot)


def hold(w, A, seconds: float | None = None, grips=None) -> None:
    """Hold the command in force (the nop agent) for `seconds`, or to the end of the episode."""
    typ, row = A.hold(w)
    if grips is not None:
        row[-2:] = grips
    n = None if seconds is None else int(round(seconds / w.CONTROL_DT))
    while not w.done and (n is None or n > 0):
        w.step(A.to_raw(typ, row, w))
        n = None if n is None else n - 1


def act(w, A, typ: str, row, steps: int = 1) -> None:
    for _ in range(steps):
        if w.done:
            return
        w.step(A.to_raw(typ, A.clip(typ, row), w))


def kick_robot(w, vel=(0.0, 0.0, 0.0), angvel=(0.0, 0.0, 0.0)) -> None:
    """Give the whole robot a velocity (a "ghost" jump: the pelvis' free joint; the joints keep theirs)."""
    r = w.robot
    w.d.qvel[r.fv:r.fv + 3] = vel
    w.d.qvel[r.fv + 3:r.fv + 6] = angvel


def move_robot(w, x=None, y=None, z=None, yaw=None, held=False) -> None:
    """Teleport the standing robot (its joints and velocities kept). held: what its hands grip is moved with it (over
    metres a grip's weld would otherwise throw the object after the robot, faster than the simulator's sanity bound)."""
    r, d = w.robot, w.d
    p0 = d.qpos[r.fq:r.fq + 3].copy()
    for i, v in enumerate((x, y, z)):
        if v is not None:
            d.qpos[r.fq + i] = v
    for name in {n for n in w.held.values() if held and n in w.free}:
        qa, _ = w.free[name]
        d.qpos[qa:qa + 3] += d.qpos[r.fq:r.fq + 3] - p0
    if yaw is not None:
        d.qpos[r.fq + 3:r.fq + 7] = [np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)]


def verdict(w) -> dict:
    ref = w.ref
    return {"success": ref.success, "failed": ref.failed, "stages": list(ref.stages), "metrics": dict(ref.metrics)}
