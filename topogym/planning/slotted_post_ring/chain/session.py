"""Sessions of the Slotted rigid-chain settings and the scene (privileged state) the stages plan from."""
from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation as R

VARIATION = "slotted_post_ring_hard_chain"
ENTITY = "slotted_chain"
PARTS = ("ring", "bead_left", "bead_right", "disc_left", "disc_right")


def build_session(variation=VARIATION, *, headless=True, seed=0):
    """A Session of a chain setting from its reset, with the setting's own simulator settings and grasp assist
    (simulator_settings, grasp_assist()). headless: no cameras, so no GPU (the physics runs on the CPU either way)."""
    from topogym.planning.slotted_post_ring.runtime import tooling
    rcb = tooling()
    if headless:
        spec = rcb.TASKS["slotted_post_ring"]
        rcb.TASKS["slotted_post_ring"] = {**spec, "simulator": {**spec["simulator"], "enable_rgb": False,
                                                                "enable_depth": False}}
    return rcb.Session("slotted_post_ring", variation_id=variation, seed=seed, strict=True, max_steps=10**6)


@dataclass
class Scene:
    """A World state in the assembly frame: the chain's joint points (left eye first), the parts' poses and the
    fastest link (name, speed)."""
    points: np.ndarray
    poses: dict
    speed_m_s: float
    fastest: str = ""

    def pos(self, name):
        return self.poses[name][0]


def scene(session):
    task = session.env._task
    world = session.env.privileged.get("world")
    links = world["articulations"][ENTITY]["links"]
    poses = {name: (np.asarray(links[name]["position_m"], float)-task.origin,
                    R.from_quat(np.asarray(links[name]["quaternion_wxyz"], float)[[1, 2, 3, 0]])) for name in PARTS}
    speed, fastest = max((float(np.linalg.norm(link["linear_velocity_m_s"])), name) for name, link in links.items())
    return Scene(task.chain_points(world)-task.origin, poses, speed, fastest)
