"""The simplest `hit` skill from the provided tools (the core-skill boundary test), in the deliverable's form: the
base to the stance for the requested contact, the toolkit's IK for the requested blade pose (pos, normal) at that
base position, then `slew` there at full speed and wait. It ignores t and vel (no swing: the paddle meets the ball
nearly still) and has no step()."""
import sys

import numpy as np

_S = {}


def hit(t, pos, normal, vel, *, state, spec):
    if not _S:
        lib = spec.get("toolkit", {}).get("ik_library", {}).get("file", "/opt/robot/lib/tt_kinematics.py")
        sys.path.insert(0, lib.rsplit("/", 1)[0])
        from tt_kinematics import PaddleKinematics
        _S["K"] = PaddleKinematics(spec.get("toolkit", {}).get("robot_model", "/opt/robot/robot_only.xml"))
        _S["vlim"] = np.array(spec["limits"]["joint_speed_limit"], float)[2:]
    K = _S["K"]
    q_now = np.asarray(state["q_target"], float)
    base = K.stance(pos, q_now[:2])
    qa, _ = K.solve_near(pos, normal=normal, q_ref=q_now[2:], base=base, vel_limit=_S["vlim"])
    return {"type": "slew", "q": [round(float(x), 6) for x in np.r_[base, qa]], "speed": 1.0}
