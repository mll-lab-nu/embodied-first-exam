"""Discrete, collision-checked free-hand approach corridors for physical runs.

These change the route to the same measured grasp, not the playback speed or
camera. They preserve the support/extraction roles and never move puzzle bodies.
"""
import numpy as np

from .robot_motion import Kinematics
from .robot_clearance import RobotClearance


ROUTES = {
    "F1": dict(name="high_approach", waypoint_m=[-.08, .06, .44]),
    "F2": dict(name="outer_approach", waypoint_m=[-.22, .20, .25]),
    "F3": dict(name="rear_approach", waypoint_m=[-.10, -.20, .22]),
}


def plan(cfg, template, scale, start, end, frame, family, *, offset_m=(0, 0, 0)):
    if family not in ROUTES:
        raise ValueError(f"Unknown route family: {family}")
    kin = Kinematics(cfg)
    kin.q = np.asarray(start).copy()
    _, rotation = kin.pose("left")
    point = np.asarray(ROUTES[family]["waypoint_m"])+offset_m
    error = kin.solve("left", point, rotation)
    if error[0] > .0005 or error[1] > .005:
        raise RuntimeError(f"{family}: unreachable corridor waypoint: {error}")
    via = kin.q.copy()
    checker = RobotClearance(cfg, template, scale)
    first, a = checker.joint_transfer(start, via, "left", frame, fps=20)
    second, b = checker.joint_transfer(via, end, "left", frame, fps=20)
    return first+second, dict(family_id=family, waypoint_m=point.tolist(),
        waypoint_qpos=via.tolist(), segments=[a, b],
        scope="sampled robot/table/puzzle clearance; physical guards remain required")


def execute(motion, target):
    from .physical_plan import body_frame
    from .gravity_demo import array
    family = motion.instance["parameters"]["family_id"]
    end = array(motion.robot.get_qpos()).copy()
    end[:6] = target
    trajectory, proof = plan(motion.cfg.robot_control, motion.task.assembly.template,
        float(motion.cfg.task.scale), array(motion.robot.get_qpos()), end, body_frame(motion), family,
        offset_m=motion.instance["parameters"]["route_offset_m"])
    motion.events.append(dict(time_s=motion.step_count*motion.dt, family_route=proof))
    motion.phase = "family_"+family+"_corridor"
    print(f"{motion.step_count*motion.dt:.2f}s {motion.phase}", flush=True)
    for index, target in enumerate(trajectory):
        if index == proof["segments"][0]["frames"]:
            motion.phase = "family_"+family+"_ring_approach"
        q = motion.q.copy()
        q[:6] = target[:6]
        motion.joint_segment(q, .05)
