# Oracle for putting_shoes_on_rack (BEHAVIOR-1K 2026 challenge, public instance 301, house_double_floor_lower).
# BDDL goal: every gym shoe and sandal touches the hall tree and not the floor; the two gym shoes are nextto each other,
# and so are the two sandals. nextto = the gap between the two AABBs is at most mean(sum of their extents) / 6
# (~6.3 cm for the gym shoes, ~5.3 cm for the sandals) with nothing between them along a horizontal axis.
#
# Plan: one shoe at a time: grasp it from the floor, carry it to the hall tree, turn the hand so the shoe's long axis
# runs along the hall tree (world y), and set it down on the seat. The two shoes of a pair go end to end along y with
# a ~2 cm gap: at release the fingers hold the shoe's middle, 12-15 cm away from its neighbour, so they cannot knock it.
# The second shoe's spot comes from where the first one actually landed. Where the seat is (height, depth, extent
# along the wall) is measured, not assumed: downward rays over the hall tree's footprint before anything moves.
import math

import numpy as np

T = TASK
RACK = T["rack"]
PAIRS = [T["gym_shoes"], T["sandals"]]
GAP = 0.02            # target AABB gap between the two shoes of a pair (nextto allows ~5-6 cm)
RELEASE_DZ = 0.03     # shoe bottom this far above the seat when the gripper opens
HOVER = 0.18          # approach height above the release pose
STANDOFF = 0.45       # base centre to the seat's front edge (x), horizontally
EDGE = 0.05           # shoe's near side this far behind the seat's front edge
MARGIN = 0.08         # keep the pairs this far from the ends of the seat (the alcove's side walls)


def log(*a):
    print("[oracle]", *a, flush=True)


DEBUG_DIR = __import__("os").environ.get("RCB_ORACLE_DEBUG_DIR")   # development only: views of the seat after each put


def snap(label):
    if not DEBUG_DIR:
        return
    try:
        import omnigibson as og
        import omnigibson.utils.transform_utils as TU
        import torch
        from PIL import Image
        cam = og.sim.viewer_camera
        c, e = aabb(RACK)
        target = np.array([c[0] + e[0] / 2 - 0.2, c[1], 0.6])
        eye = target + np.array([1.5, 1.2, 0.9])
        f = target - eye; f /= np.linalg.norm(f)
        zc = -f; xc = np.cross([0, 0, 1.0], zc); xc /= np.linalg.norm(xc); yc = np.cross(zc, xc)
        cam.set_position_orientation(position=torch.tensor(eye, dtype=torch.float32),
                                     orientation=TU.mat2quat(torch.tensor(np.stack([xc, yc, zc], axis=1), dtype=torch.float32)))
        for _ in range(6):
            og.sim.render()
        obs = cam.get_obs()
        obs = obs[0] if isinstance(obs, tuple) else obs
        rgb = obs["rgb"].cpu().numpy()[..., :3].astype(np.uint8)
        path = f"{DEBUG_DIR}/{label}.png"
        Image.fromarray(rgb).save(path)
        log("snapshot", path)
    except Exception as exc:  # noqa: BLE001
        log("snapshot failed:", repr(exc)[:120])


def yaw_of(q):
    x, y, z, w = [float(v) for v in q]
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def rot_z(q, a):
    x, y, z, w = [float(v) for v in q]
    c, s_ = math.cos(a / 2), math.sin(a / 2)
    return np.array([c * x - s_ * y, c * y + s_ * x, c * z + s_ * w, c * w - s_ * z])


def aabb(name):
    c, e = get_object_bbox(name)
    return np.asarray(c, float), np.asarray(e, float)


def dims(name):
    """(length, width, height) of the object in its own frame (the model's native bounding box times its scale)."""
    o = s.get_object(name)
    nb = np.asarray(o.native_bbox, dtype=float) * np.asarray(o.scale, dtype=float)
    return float(nb[0]), float(nb[1]), float(nb[2])


# ---------------------------------------------------------------- the seat, measured before anything moves
def find_seat():
    """The top of the hall tree's shoe cabinet: the HIGHEST large upward-facing hall-tree surface below 0.9 m (the
    shelves inside the cabinet lie under it, out of reach from above): (z, x_lo, x_hi, y_lo, y_hi)."""
    from omnigibson.utils.sampling_utils import raytest_batch
    hall = s.get_object(RACK)
    hp = hall.prim_path
    c, e = aabb(RACK)
    lo, hi = c - e / 2, c + e / 2
    xs = np.arange(lo[0] + 0.02, hi[0] - 0.01, 0.02)
    ys = np.arange(lo[1] + 0.02, hi[1] - 0.01, 0.02)
    starts = [[float(x), float(y), float(hi[2] + 0.2)] for x in xs for y in ys]
    ends = [[float(x), float(y), -0.05] for x in xs for y in ys]
    hits = raytest_batch(starts, ends, only_closest=False)
    pts = []
    for k, hs in enumerate(hits):
        for h in hs or []:
            if h.get("hit") and str(h.get("rigidBody", "")).startswith(hp) and float(h["normal"][2]) > 0.8:
                z = float(h["position"][2])
                if 0.15 < z < 0.9:
                    i, j = divmod(k, len(ys))
                    pts.append((float(xs[i]), float(ys[j]), z))
    if not pts:
        raise RuntimeError("no upward-facing hall-tree surface between 0.15 and 0.9 m")
    pts = np.array(pts)
    bands = {}
    for p in pts:
        bands.setdefault(round(p[2] / 0.02), []).append(p)
    big = [k for k, v in bands.items() if len(v) >= 300]
    if not big:
        raise RuntimeError(f"no large surface; bands {sorted((k * 0.02, len(v)) for k, v in bands.items())}")
    b = np.array(bands[max(big)])
    seat = (float(np.median(b[:, 2])), float(b[:, 0].min()), float(b[:, 0].max()), float(b[:, 1].min()), float(b[:, 1].max()))
    log(f"seat z {seat[0]:.3f}, x {seat[1]:.2f}..{seat[2]:.2f}, y {seat[3]:.2f}..{seat[4]:.2f} ({len(b)} rays); "
        f"other bands: {sorted((round(k * 0.02, 2), len(v)) for k, v in bands.items() if len(v) > 10)}")
    return seat


SEAT_Z, SX0, SX1, SY0, SY1 = find_seat()
FRONT_X = SX1                                 # the seat's front edge (+x side, towards the corridor)
BASE_YAW = math.pi                            # face the wall (-x)


def where(name):
    c, e = aabb(name)
    return (f"centre {np.round(c, 3).tolist()} bottom z {c[2] - e[2] / 2:.3f}; eef {np.round(get_eef_pose()[0], 3).tolist()}, "
            f"held {object_in_hand()}")


def on_rack(name):
    """The shoe rests on the seat: its bottom at the seat's height and its centre over the seat."""
    c, e = aabb(name)
    return abs((c[2] - e[2] / 2) - SEAT_Z) < 0.03 and SX0 - 0.02 < c[0] < SX1 + 0.02 and SY0 - 0.02 < c[1] < SY1 + 0.02


def gap3(a, b):
    """The distance between two AABBs, as OmniGibson's nextto measures it."""
    (ca, ea), (cb, eb) = aabb(a), aabb(b)
    d = np.maximum(0.0, np.abs(ca - cb) - (ea + eb) / 2)
    return float(np.linalg.norm(d))


# ---------------------------------------------------------------- one shoe
TOP_DOWN = np.array([1.0, 0.0, 0.0, 0.0])   # eef pointing down; at yaw 0 the fingers close along world y
GRASP_DEPTHS = (0.06, 0.045, 0.075)          # eef this far below the top of the shoe's AABB, tried in this order
CARRY = dict()                               # carry()'s defaults: the drops in transit were the gripper command, not
                                             # the carry pose (fixed in the tooling: Session.keep_grip)


def pick(name):
    """Top-down grasp at the shoe's pose origin (the middle of these models) with the fingers closing across its
    width. The upstream grasp puts the eef at the TOP of the AABB with a fixed yaw: the fingertips (1.9 cm below the
    eef) then close above most of the upper and catch nothing. Measured on gym_shoe_1: 4 cm lower, it holds."""
    pos, q = get_object_pose(name)
    c, e = aabb(name)
    x, y, z, w = [float(v) for v in q]
    upright = 1 - 2 * (x * x + y * y) > 0.8        # the shoe's local z axis still points up
    if upright:
        qq = rot_z(TOP_DOWN, yaw_of(q)); xy = pos[:2]
    else:                                            # knocked over: close across the narrower side of its footprint
        qq = rot_z(TOP_DOWN, 0.0 if e[1] < e[0] else math.pi / 2); xy = c[:2]
        log(f"pick {name}: not upright ({where(name)}); grasping at the AABB centre across its narrow side")
    top = float(c[2] + e[2] / 2)
    for depth in GRASP_DEPTHS:
        g = np.array([xy[0], xy[1], top - depth])
        pre = g + np.array([0.0, 0.0, 0.15])
        if not in_reach(pre, qq):
            navigate_to_object(name, eef_pose=(pre, qq), standoffs=(0.65, 0.8, 0.55, 0.95))
        move_hand_direct(pre, qq, ignore_objects=[name])
        move_hand_direct(g, qq, ignore_objects=[name])
        close_gripper()
        try:
            settle(150)
        except Exception:  # noqa: BLE001  (still swaying a little is fine)
            pass
        if object_in_hand() == name:
            break
        log(f"pick {name}: nothing in hand at depth {depth:.3f}; opening and trying the next depth")
        open_gripper()
        move_hand_direct(pre, qq, ignore_objects=[name])
    else:
        raise RuntimeError(f"pick({name}): nothing in hand after {len(GRASP_DEPTHS)} closes")
    lift(0.25)
    carry(**CARRY)
    c, e = aabb(name)
    log(f"holding {name}: aabb centre {np.round(c, 3).tolist()} extent {np.round(e, 3).tolist()}")


def put(name, centre_xy):
    """Set the held shoe down with its AABB centre at centre_xy on the seat and its long axis along world y. The base
    stands in front of the spot facing the wall; if the arm cannot get the shoe there (no IK, or more than 4 cm off),
    the shoe is pulled back to the body and the base tries a few other spots nearby."""
    last = None
    for bdx, bdy in ((0.0, 0.0), (0.0, 0.15), (0.0, -0.15), (-0.08, 0.0), (0.0, 0.3), (0.0, -0.3), (0.08, 0.0)):
        if object_in_hand() != name:   # dropped on the way (v2: a sandal): pick it up again where it lies
            log(f"put {name}: not in hand any more ({where(name)}); picking it up again")
            pick(name)
        try:
            navigate_to_pose(FRONT_X + STANDOFF + bdx, float(centre_xy[1]) + bdy, BASE_YAW)
        except Exception as exc:  # noqa: BLE001
            last = f"navigation (base offset {bdx:+.2f}, {bdy:+.2f}): {str(exc)[:100]}"
            log("put:", last)
            back_up(0.3)
            continue
        eef, q = get_eef_pose()
        c, e = aabb(name)
        _, sq = get_object_pose(name)
        # the shoe's long axis is its local x; turn the hand so it ends up along world y (either way round, whichever
        # is the smaller turn), and turn the held offset (measured now, after the base has turned) with it
        d = wrap(math.pi / 2 - yaw_of(sq))
        if abs(d) > math.pi / 2:
            d = wrap(d + math.pi)
        off = c - eef
        cd, sd = math.cos(d), math.sin(d)
        off_r = np.array([cd * off[0] - sd * off[1], sd * off[0] + cd * off[1], off[2]])
        q2 = rot_z(q, d)
        target_c = np.array([centre_xy[0], centre_xy[1], SEAT_Z + float(e[2]) / 2 + RELEASE_DZ])
        eef_t = target_c - off_r
        hover = eef_t + np.array([0.0, 0.0, HOVER])
        if not in_reach(hover, q2) and (bdx, bdy) != (0.08, 0.0):
            # the hand must be able to rise straight out of the released shoe from here (v7: no IK for the lift, the
            # low hand then swept the shoe off the seat as the base backed away): try another base pose
            last = f"hover pose out of reach at base offset ({bdx:+.2f}, {bdy:+.2f})"
            log("put:", last)
            continue
        log(f"put {name} (base offset {bdx:+.2f}, {bdy:+.2f}): turn hand {math.degrees(d):.0f} deg, shoe centre target "
            f"{np.round(target_c, 3).tolist()}, eef target {np.round(eef_t, 3).tolist()} (held offset {np.round(off_r, 3).tolist()})")
        try:
            try:
                move_hand(hover, q2, low_precision=True, attempts=2)
            except Exception as exc:  # noqa: BLE001
                log("planned hover failed, direct:", str(exc)[:100])
                move_hand_direct(hover, q2)
            move_hand_direct(eef_t, q2)
        except Exception as exc:  # noqa: BLE001
            last = f"base offset ({bdx:+.2f}, {bdy:+.2f}): {str(exc)[:100]}"
            log("put:", last)
            carry(**CARRY)  # the shoe back at the body before the base moves again
            continue
        c_now, _ = aabb(name)
        err = math.hypot(c_now[0] - target_c[0], c_now[1] - target_c[1])
        if err > 0.04:
            last = f"shoe {err:.3f} m off the spot at base offset ({bdx:+.2f}, {bdy:+.2f})"
            log("put:", last)
            move_hand_direct(hover, q2)
            carry(**CARRY)
            continue
        log(f"at release: shoe centre {np.round(c_now, 3).tolist()} ({err * 100:.1f} cm off the spot)")
        break
    else:
        raise RuntimeError(f"put({name}): no base pose worked; last: {last}")
    open_gripper()
    try:
        settle(200)
    except Exception:  # noqa: BLE001
        pass
    log(f"  after open: {where(name)}")
    # straight up first, in 5 cm steps: the open fingers still surround the shoe, and one long joint-space move (or
    # backing the base away now) sweeps the hand sideways and knocks the shoe off the seat (v2: gym shoe 1 on the floor)
    up, uq = get_eef_pose()
    try:
        move_hand(up + np.array([0.0, 0.0, 0.18]), uq, low_precision=True, attempts=1)   # collision-aware
    except Exception as exc:  # noqa: BLE001
        log("  planned lift failed, stepping up:", str(exc)[:60])
        for k in range(1, 8):
            try:
                move_hand_direct(up + np.array([0.0, 0.0, 0.025 * k]), uq)
            except Exception as exc2:  # noqa: BLE001
                log("  lift step failed:", str(exc2)[:80]); break
    if get_eef_pose()[0][2] < up[2] + 0.08:
        log(f"  WARNING the hand rose only {get_eef_pose()[0][2] - up[2]:.3f} m before backing away")
    log(f"  after lift: {where(name)}")
    back_up(0.4)
    back_up(0.4)   # tuck_arm sweeps the whole arm through joint space: v3 knocked a shoe off the seat tucking 0.4 m away
    log(f"  after back-up: {where(name)}")
    try:
        tuck_arm()
    except Exception as exc:  # noqa: BLE001
        log("tuck skipped:", str(exc)[:80])
    log(f"  after tuck: {where(name)}")
    c_after, e_after = aabb(name)
    log(f"{name} landed at {np.round(c_after, 3).tolist()} extent {np.round(e_after, 3).tolist()}")
    snap(f"after_{name}")
    return c_after, e_after


# ---------------------------------------------------------------- both pairs
# pair 0 (gym shoes) from the -y end of the seat, pair 1 (sandals) from the +y end: the pairs stay apart
def spot_x(width):
    return FRONT_X - EDGE - width / 2


def first_spot(pair_idx, length, width):
    if pair_idx == 0:
        return np.array([spot_x(width), SY0 + MARGIN + length / 2])
    return np.array([spot_x(width), SY1 - MARGIN - length / 2])


def place(name, spot_fn, tries=2):
    """pick + put until the shoe stays on the seat. spot_fn() gives the target, recomputed on every try."""
    for k in range(tries):
        if object_in_hand() != name:
            pick(name)
        put(name, spot_fn())
        if on_rack(name):
            return aabb(name)
        log(f"{name} did not stay on the seat ({where(name)}); try {k + 2} of {tries}")
    raise RuntimeError(f"{name}: not on the seat after {tries} tries")


try:
    for k, pair in enumerate(PAIRS):
        a, b = pair
        la, lb = dims(a)[0], dims(b)[0]
        log(f"pair {k}: {a} {np.round(dims(a), 3).tolist()}, {b} {np.round(dims(b), 3).tolist()} (step {s.status()['sim_steps']})")
        ca, ea = place(a, lambda: first_spot(k, la, dims(a)[1]))
        sign = 1.0 if k == 0 else -1.0          # the second shoe goes towards the middle of the seat

        def second():
            c1, e1 = aabb(a)                    # where the first one really is now
            return np.array([spot_x(dims(b)[1]), c1[1] + sign * (e1[1] / 2 + GAP + lb / 2)])
        place(b, second)
        log(f"pair {k}: AABB gap {gap3(a, b):.3f} m (nextto needs <= ~{np.mean(aabb(a)[1] + aabb(b)[1]) / 6:.3f}); "
            f"status {s.status()}")
except Exception as exc:  # noqa: BLE001
    log("stopped:", type(exc).__name__, str(exc)[:200])
log("final status", s.status())
