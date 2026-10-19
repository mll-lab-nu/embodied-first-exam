# Reference solution for banana_in_bowl (RoboLab BananaInBowlTask), seed-0 instance. Runs with the rcb_robolab primitives in
# scope (see Session.exec_code): objects(), get_object_points, grasp_point, grasp, place, hold, move_ee, ... Plan: pick the
# grasp point on the banana's body from its surface mesh (the pose / AABB centre lies in the concavity of the curved fruit),
# close the fingers across the local body direction with the fingertips almost at the table, lift slowly, carry the banana
# above the bowl, lower it to just above the rim, release, retreat. RoboLab's success term (object_in_container + gripper
# detached) terminates the episode by itself (177 actions, 12 s of simulated time).
# The task-level skills (grasp_point, grasp, place, ...) come from solution/ref_primitives.py: the agent's tooling
# has only thin primitives.
import sys

sys.path.insert(0, "/solution")
from ref_primitives import extend  # noqa: E402

globals().update(extend(session))

objs = objects()
banana, bowl = objs["banana"], objs["bowl"]
print(f"[oracle] banana at {banana['position']} size {banana.get('size')}, bowl at {bowl['position']} bounds {bowl.get('bounds')}")

# A banana is curved: its pose / bounding-box centre lies in the concavity, so the fingers would close on air. Take the grasp
# point from the mesh surface points instead (centroid of a slab across the body at a fraction of its length) and close the
# fingers across the local body direction. Try the middle first, then points towards either end. The fingertip frame is the
# end of the closed fingertips, so the frame goes almost down to the table for a 3.7 cm tall object.
table_z = TASK.get("table_top_z") or 0.0
pts = get_object_points("banana")
print(f"[oracle] banana surface points: {len(pts)}, xy extent {pts[:, :2].min(axis=0).round(3).tolist()} .. {pts[:, :2].max(axis=0).round(3).tolist()}")
off = None
for k, frac in enumerate((0.5, 0.35, 0.65, 0.25, 0.75)):
    if session.episode_done:
        break
    gp, yaw = grasp_point("banana", frac=frac)
    tip_z = table_z + (0.006 if k == 0 else 0.004)       # closed fingertips just above the table: the pads wrap the banana's body
    print(f"[oracle] attempt {k}: grasp point {gp.round(3).tolist()} (frac {frac}), closing yaw {yaw:.2f}, tip z {tip_z:.3f}")
    try:
        off = grasp("banana", point=[gp[0], gp[1], tip_z], yaw=yaw, hover=0.12, depth=0.0, lift=0.15, close_steps=30)
        print(f"[oracle] grasped the banana at frac {frac}; tip offset {off}")
        break
    except PrimitiveError as e:
        print(f"[oracle] grasp attempt {k}: {e}")
        open_gripper(10); hold(5)
if off is None and not session.episode_done:
    raise PrimitiveError("could not grasp the banana")

if not session.episode_done:
    b = objects()["bowl"]
    rim_z = b["bounds"][1][2] if b.get("bounds") else b["position"][2] + 0.06
    target = [b["position"][0], b["position"][1], rim_z + 0.04]      # object centre just above the rim, then release
    err = place(target, off, hover=0.10, release_gap=0.0, retreat=0.15)
    print(f"[oracle] released above the bowl (tip err {err})")
hold(30)
print("[oracle] status:", session.status())
