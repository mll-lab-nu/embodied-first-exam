# Human-written reference solution for behavior-picking-up-trash-i00 (2026 BEHAVIOR Challenge task picking_up_trash,
# public instance 301). Runs inside Session.exec_code(): the primitives from rcb_behavior.Session.primitives() are in scope.
# Never shipped in the agent image (lives under solution/ only).
import math
import numpy as np

trash = TASK["trash"]

def log(*a):
    print("[oracle]", *a, flush=True)

def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

objs = objects()
log("objects:", {k: v["position"] for k, v in objs.items() if "soda" in k or "ashcan" in k})
settle()
# nearest can first (it is usually within reach of the start pose), then the others
robot_xy = get_robot_pose()[0][:2]
cans = sorted(TASK["cans"], key=lambda c: dist(objs[c]["position"], robot_xy))
done = []
delivery = None   # the base pose that worked for the first delivery is reused for the others (same frozen scene)
for can in cans:
    try:
        log("grasping", can, "at", objs[can]["position"])
        grasp(can)
        lift(0.25)
        try:
            lift(0.35)   # carry high: the extended arm then clears tables and sofa backs while the base navigates
        except Exception as exc:
            log("high carry skipped:", str(exc)[:100])
        log("placing", can, "into", trash, "| delivery pose", delivery)
        # lying down: three upright cans stack up past the top of the trash can's fillable volume (the `inside`
        # predicate tests it), three lying ones stay well below it
        place_inside(trash, base_pose=delivery, lay=True)
        if delivery is None:
            delivery = last_delivery_pose()
        try:
            settle(200)
        except Exception:
            pass
        done.append(can)
        cpos = get_object_pose(can)[0]; cc, ce = get_object_bbox(trash)
        log("placed", can, "| can at", np.round(cpos, 3).tolist(), "| trash bbox centre", np.round(cc, 3).tolist(), "extent", np.round(ce, 3).tolist(), "| status:", session.status())
    except Exception as exc:  # keep going with the other cans; the verifier only looks at the final state
        if session.episode_done:  # the env ends the episode the moment the BDDL goal holds (the last can just landed)
            log("episode ended during", can, "| status:", session.status()); break
        log("FAILED", can, "->", repr(exc)[:300])
        try:
            if object_in_hand() is not None:
                open_gripper(); settle(100)
        except Exception as exc2:
            log("cleanup failed:", str(exc2)[:120])
log("done:", done, "| final status:", session.status())
