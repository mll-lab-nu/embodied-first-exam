"""Oracle (privileged mode): drive the base around the chairs' north side into the green goal square, reading the base's
pose from the state each step. Every move stays inside a 0.1 m disc, so the same actions are legal in standard mode.
Writes /app/output/trajectory.npz; run by solve.sh."""
import math

import numpy as np
from rcb_kinder import Session

WAYPOINTS = [(0.75, 4.5), (3.83, 4.5), (3.83, 3.83)]   # north of the chairs (a wall stands at y = 4.7), east, then south into the square
s = Session()
s.reset()
robot = next(o for o in s.state() if o.type.name == "mujoco_tidybot_robot")
with s.recording() as rec:
    for wx, wy in WAYPOINTS:
        success = False
        while not success and s.t < s.max_steps:
            st = s.state()
            dx, dy = wx - st.get(robot, "pos_base_x"), wy - st.get(robot, "pos_base_y")
            if math.hypot(dx, dy) < 0.08:
                break
            scale = min(1.0, 0.099 / math.hypot(dx, dy))   # inside the 0.1 m disc with room for round-off
            a = np.zeros(s.action_space.shape)
            a[:2] = dx * scale, dy * scale
            _, success, _ = s.step(a)
        if success:
            break
print(s.replay(rec.actions))
s.save_trajectory(rec.actions, "/app/output/trajectory.npz", {"source": "oracle: waypoints around the chairs"})
