"""sprint: stand still through "on your marks" and "set"; at the gun (the start lamp turns green: the task's phase
"running") command the running policy at 3.5 m/s and steer back to the lane's centre line from the pelvis pose. The
running policy needs about 0.3 s to move the pelvis 5 cm, so starting it at the gun is no false start."""
import numpy as np


def solve(s, vx: float = 3.5):
    typ, row = s.hold()
    while not s.done and s.state()["task"]["phase"] != "running":
        s.step(typ, row)
    while not s.done:
        x, y, _, yaw = s.state()["pelvis_xyz_yaw"]
        wz = float(np.clip(-1.5 * yaw - 1.0 * y, -0.5, 0.5))
        s.step("run", [vx, 0.0, wz, 0.0, 0.0])
