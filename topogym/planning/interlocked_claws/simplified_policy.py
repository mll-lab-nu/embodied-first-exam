"""Measured rigid grasps, bounded object tracking and ordinary EE_ABS actions."""
import numpy as np
from scipy.spatial.transform import Rotation

from .simplified_routes import PARTS
from topogym.planning.rigid_reference.feedback import body_pose, tcp_pose


class SimplifiedClawsPolicy:
    def __init__(self, *, motions=(), initial=None, offsets=None, part="solve"):
        self.motions, self.initial, self.offsets, self.part = motions, initial, offsets, part
        self.phase = "created"
        self.tracking, self.samples = {}, []
        self.completed = False

    def initialize(self, context):
        spec = context["action_spec"]
        if spec["robot_id"] != "aloha" or spec["mode"] != "EE_ABS":
            raise ValueError("Claws reference requires original ALOHA and EE_ABS")
        if spec["grasp_assist"]["model"] != "contact_weld_v1" or context["mode"] != "unlimited":
            raise ValueError("Requires declared contact_weld_v1 and authorized world observations")
        self.dt = float(context["timing_spec"]["control_dt_s"])
        self.program = None
        self.bias = {s: np.zeros(3) for s in PARTS}
        self.angle_bias = {s: np.zeros(3) for s in PARTS}

    def bodies(self):
        return {s: body_pose(self.obs["privileged"]["world"]["bodies"][n]) for s, n in PARTS.items()}

    def act(self, obs):
        self.obs = obs
        if self.program is None:
            self.program = self.actions()
        if self.part == "solve" and any(obs["privileged"]["world"]["grasp"]["hands"][s]["phase"] != "holding" for s in PARTS):
            raise RuntimeError("Lost acquired grasp in "+self.phase)
        return next(self.program, None)

    def time(self):
        return float(self.obs["state"]["sim_time_s"])

    def command(self, desired):
        actual, action = self.bodies(), {}
        for s, (p, r) in desired.items():
            error = p-actual[s][0]
            angle = (r*actual[s][1].inv()).as_rotvec()
            self.bias[s] = np.clip(self.bias[s]+4*self.dt*error, -.03, .03)
            self.angle_bias[s] = np.clip(self.angle_bias[s]+4*self.dt*angle, -.20, .20)
            commanded_r = Rotation.from_rotvec(self.angle_bias[s]+.5*angle)*r
            position = p+self.bias[s]+.5*error+commanded_r.apply(self.offsets[s][0])
            rotation = commanded_r*self.offsets[s][1]
            action[s] = dict(position_world_m=position.tolist(),
                             orientation_wxyz=rotation.as_quat()[[3, 0, 1, 2]].tolist(), gripper_position_m=.002)
        self.last_reference = {s: dict(position_m=p.tolist(), quaternion_wxyz=r.as_quat()[[3,0,1,2]].tolist())
                               for s,(p,r) in desired.items()}
        return action

    def follow(self, motion):
        self.phase = motion.phase
        start = last_progress = self.time()
        elapsed = 0.
        while True:
            fraction = min(1., elapsed/motion.seconds)
            u = fraction**3*(10+fraction*(-15+6*fraction))
            desired = {"left": motion.at(u), "right": self.initial["right"]}
            actual = self.bodies()
            errors = {s: float(np.linalg.norm(p-actual[s][0]))+.18*float((r*actual[s][1].inv()).magnitude())
                      for s,(p,r) in desired.items()}
            maximum = max(errors.values())
            self.tracking = dict(phase=self.phase, progress=u, material_error_m=errors)
            if fraction >= 1. and maximum < .0004:
                self.samples.append(dict(time_s=self.time(), **self.tracking))
                return
            if maximum < .0008:
                elapsed = min(motion.seconds, elapsed+self.dt)
                last_progress = self.time()
            if self.time()-last_progress > 8. or self.time()-start > max(30., motion.seconds*12):
                raise RuntimeError("Claws tracking stalled: "+str(self.tracking))
            yield self.command(desired)

    def actions(self):
        if self.part == "acquire":
            self.phase = "acquire_pregrasps"
            start = self.time()
            while True:
                hands = self.obs["privileged"]["world"]["grasp"]["hands"]
                if all(hands[s]["phase"] == "holding" for s in PARTS) and self.time()-start >= .20:
                    self.completed = True
                    return
                if self.time()-start > 2.:
                    raise RuntimeError("Pregrasp acquisition failed: "+str(hands))
                yield {s: dict(gripper_position_m=.002) for s in PARTS}
        for motion in self.motions:
            yield from self.follow(motion)
        self.phase = "hold_in_goal"
        start = self.time()
        while self.time()-start < 5.:
            yield self.command({"left": self.motions[-1].end, "right": self.initial["right"]})
        self.completed = True

    def debug_reference(self):
        return dict(phase=self.phase, bodies=getattr(self, "last_reference", {}), tracking=self.tracking)
