# Reference solution for stack_cubes (RoboWits task 14), evaluation scene 00. Runs with the rcb_robowits primitives in scope
# (see Session.exec_code) plus the task-level grasp / place skills of solution/ref_primitives.py. All three cubes lie on the
# left half of the table, so the left arm does everything. Plan: base cube 1 -> axis-aligned on the marker; base cube 2 ->
# flush against its +x face; apex cube -> on top of base cube 1, centred on the marker; retreat so nothing is "held" at the end.
import math
import sys

sys.path.insert(0, "/solution")
from ref_primitives import extend  # noqa: E402

globals().update(extend(session))

ARM = "left"
YAW = math.pi / 2          # fingers close along world y -> placed cubes are axis-aligned
objs = objects()
tgt = objs["apex target"]["position"]
cube = objs["base cube 1"]["size"][2]          # 0.05
rest_z = TASK["table_z"] + cube / 2             # centre height of a cube resting on the table

def pick_place(name, target_center, **kw):
    off = None
    for tilt in (0.0, 0.35, 0.7):               # a fully vertical approach is not reachable everywhere
        try:
            off = grasp(ARM, name, tilt=tilt); break
        except PrimitiveError as e:
            print(f"[oracle] grasp {name} tilt={tilt}: {e}")
            open_gripper(ARM, 10)
    if off is None:
        raise PrimitiveError(f"could not grasp {name}")
    err = place(ARM, target_center, off, closing_yaw=YAW, tilt=tilt, **kw)
    print(f"[oracle] placed {name} at {objects()[name]['position']} (tip err {err:.3f} m)")
    return tilt

pick_place("base cube 1", [tgt[0], tgt[1], rest_z])
b1 = objects()["base cube 1"]
pick_place("base cube 2", [b1["position"][0] + cube + 0.004, b1["position"][1], rest_z])
b1 = objects()["base cube 1"]
pick_place("apex cube", [tgt[0], tgt[1], b1["bounds"][1][2] + cube / 2], retreat=0.12)
hold(30)
print("[oracle] status:", session.status())
