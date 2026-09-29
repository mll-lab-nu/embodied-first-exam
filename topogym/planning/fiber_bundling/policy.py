"""Fiber Bundling observation policy built on BuzzWirePolicy's generic parts.

Only the grasped body changes: here it is a sheath link of the fiber_bundle
articulation. Reused unchanged: planned open-hand transfer, grasp approach that
stops on registration, closing and finger settling, and FK-checked joint
reference following. No route or Buzz geometry is used.
"""
import numpy as np

from topogym.planning.buzz_wire_3d.policy import BuzzWirePolicy, rotation
from .keyframes import GRASP_LINK


class FiberPolicy(BuzzWirePolicy):
    def __init__(self, *, part, link=GRASP_LINK, grasp_pose=None, plans=(), pauses=(), **kwargs):
        super().__init__(route=None, origin=np.zeros(3), part=part, **kwargs)
        self.link, self.grasp_pose = link, grasp_pose
        self.plans, self.pauses = list(plans), list(pauses)

    def body(self):
        b = self.obs["privileged"]["world"]["articulations"]["fiber_bundle"]["links"][self.link]
        return np.asarray(b["position_m"]), rotation(b["quaternion_wxyz"])

    def actions(self):
        if self.part == "pickup":
            yield from self.pickup_actions()
        elif self.part == "references":
            self.grip = .8*self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]["last_fraction"]
            for plan, pause in zip(self.plans, self.pauses):
                self.plan = plan
                yield from self.joint_reference_actions()
                self.phase = "pause"
                yield from self.hold(pause)
        else:
            yield from super().actions()

    def pickup_actions(self):
        self.phase, self.grip = "open_at_home", 0.
        yield {"arm": {"gripper_position_rad": self.grip}}
        yield from self.hold(.5)
        self.stop_after_transfer = True
        yield from self.acquire_actions()
        p, r = self.grasp_pose
        yield from self.approach_grasp((np.asarray(p), rotation(r)))
        self.phase = "close_on_sheath"
        yield from self.acquire_grip()
        hand = self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]
        if hand["phase"] != "holding":
            raise RuntimeError("Sheath grasp failed: "+str(hand))
        self.phase = "settle_closed_gripper"
        yield from self.settle_gripper()
        if self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]["phase"] != "holding":
            raise RuntimeError("Grasp lost while the fingers settled")
