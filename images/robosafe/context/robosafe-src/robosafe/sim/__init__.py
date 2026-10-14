"""The arm lane: a MuJoCo bench world with a UR5e and a Robotiq 2F-85, driven by rows of joint position targets.

    from robosafe.sim import World, skills
    world = World(scene)
    status = skills.run(world, skills.pick(world, "tube1"))
    world.state_hash()

See `docs/MOTION.md`.
"""
import os

os.environ.setdefault("MUJOCO_GL", "egl")   # head-less rendering; must be set before mujoco is imported

from .world import (CONTROL_DT, GRIPPER_MAX, PHYSICS_DT, ROW_SIZE, SUBSTEPS, RowRejected, SimulationUnstable,  # noqa: E402
                    World)

__all__ = ["World", "CONTROL_DT", "PHYSICS_DT", "SUBSTEPS", "ROW_SIZE", "GRIPPER_MAX", "RowRejected", "SimulationUnstable"]
