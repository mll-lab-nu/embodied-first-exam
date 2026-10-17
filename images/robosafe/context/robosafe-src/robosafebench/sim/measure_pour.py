"""Steady-pour on two YAM arms (`python -m robosafebench.sim.measure_two_hands pour ...`): the left hand holds a cup, the
right hand pours a glass of water into it.

Cells: where the cup stands (a grid in the middle and on the left half) x how it is held (`table`: it stays standing,
held by its side; `air`: held by its side and raised 8 cm). The glass stands on the right half.

`rows` (control interface): the right hand takes the glass by its side (level or tipped, `rows.hold_by_side`) and
lifts it; then a tilt about a level axis through the point of its rim nearest the cup is searched for, among eight
directions of that axis, as poses of the glass that IK can follow every 10 degrees up to 115 degrees, free of
collisions, from 50 degrees on (the glass is tipped that far above, before it comes down), that rim point held 4 cm above
the middle of the cup's mouth (what flows lands in the cup from any height); the glass is carried there, tipped,
held 2 s, brought back upright and set down. `skills`: `hold` the cup, `pick` the glass, `pour` into the cup, and for
`air` a `move` of the cup up by 8 cm first.
"""
from __future__ import annotations

import math

import numpy as np

CUPS = [(x, y) for x in (-0.12, -0.06, 0.0, 0.05) for y in (-0.08, 0.0, 0.07)]
# `table` / `air`: a cup held by its side; `pot`: a saucepan held still by its long handle (towards the holding arm)
CELLS = [(x, y, how) for how in ("pot", "table", "air") for (x, y) in CUPS]
POT = {"radius": 0.085, "height": 0.095, "handle": 0.17}
GLASS_AT = (0.24, -0.02)
WATER_ML = 120.0
CUP = {"radius": 0.036, "height": 0.095, "color": "white"}
GLASS = {"radius": 0.034, "height": 0.12}


def pour_scene(x, y, assist=True, how="table"):
    recv = ({"name": "cup", "kind": "pot", "params": POT, "pos": [x, y, 0.0], "yaw_deg": 180.0} if how == "pot"
            else {"name": "cup", "kind": "cup", "params": CUP, "pos": [x, y, 0.0]})
    scene = {"robot": {"type": "yam_bimanual"}, "assist": bool(assist), "objects": [
        recv,
        {"name": "glass", "kind": "glass", "params": GLASS, "pos": [GLASS_AT[0], GLASS_AT[1], 0.0]}]}

    def setup(ep):
        ep.state.vessel_from_meta("cup", {})
        ep.state.vessel_from_meta("glass", {"water": WATER_ML})
    return scene, setup


def _judge(ep, row):
    st = ep.state
    row["in_cup_ml"] = round(st.vessels["cup"].total(), 1)
    row["spilled_ml"] = round(st.poured(how="spill") + st.poured(how="overflow"), 1)
    row["left_in_glass_ml"] = round(st.vessels["glass"].total(), 1)
    row["cup_tilt_deg"] = round(float(st.tilt_deg("cup")), 1)
    row["success"] = bool(row["in_cup_ml"] >= 50.0 and row["spilled_ml"] < 1.0 and row["cup_tilt_deg"] < 15.0)
    return row


def _side_point(w, obj):
    meta = w.objects[obj]["meta"]
    g = next(g for g in meta["grasps"] if g["type"] == "side")
    return w.locate(obj)[0] + np.asarray(g["pos"], dtype=np.float64), float(g["width"])


NEED_DEG = 100.0            # a tilt that reaches this far is taken (past level: the glass empties)


def tilt_plan(R, name, vessel: str, target_mouth, clear: float = 0.04, max_deg: float = 115.0, step_deg: float = 10.0, ignore=(),
              need: float = NEED_DEG, start_deg: float = 50.0):
    """Poses of the hand that tip the held `vessel` about a level axis through a point of its rim, that point held
    `clear` above `target_mouth`; the first of eight axis directions for which IK follows the whole tilt without a
    collision as far as `need` (and on to `max_deg` where it can). Returns (hand poses from upright, lean direction,
    the furthest angle any direction reached); (None, None, that angle) when none reaches `need`."""
    from robosafebench.sim import tf
    a = R.arm(name)
    w = R.world
    tcp = a.tcp_pose()
    vp, vq = w.locate(vessel)
    in_hand = tf.compose(tf.inverse(tcp), (vp, vq))                       # the vessel in the hand's frame
    meta = w.objects[vessel]["meta"]
    vm = meta.get("vessel") or {}
    mouth_local = np.asarray(meta.get("sites", {}).get(vm.get("mouth_site", "mouth"), [0.0, 0.0, meta["size"][2]]), dtype=np.float64)
    radius = float(vm.get("inner_radius", 0.03))
    up = np.array([0.0, 0.0, 1.0])
    furthest = -1.0
    for k in range(8):
        az = math.radians(45.0 * k)
        lean = np.array([math.cos(az), math.sin(az), 0.0])
        axis = np.cross(up, lean)                                         # tipping towards `lean`
        lip_local = mouth_local + radius * tf.rotate(tf.quat_conj(vq), lean)      # the rim point towards `lean`, vessel frame
        poses, q, ok = [], np.asarray(a.target[:-1], dtype=np.float64), True
        for deg in np.arange(start_deg, max_deg + 1e-6, step_deg):     # tipped to `start_deg` above, then over the cup
            vquat = tf.compose((np.zeros(3), tf.quat_axis_angle(axis, math.radians(float(deg)))), (np.zeros(3), vq))[1]
            lip_now = tf.rotate(vquat, lip_local)
            vpos = np.asarray(target_mouth, dtype=np.float64) + np.array([0.0, 0.0, clear]) - lip_now
            hand = tf.compose((vpos, vquat), tf.inverse(in_hand))
            r = None
            for seed in ([q, a.ready, a.home] if not poses else [q]):
                r = a.ik.solve(hand[0], hand[1], seed, max_jump=10.0 if not poses else 1.2, max_iters=200)
                if r.ok:
                    break
            if not r.ok or a.ik.collision(r.q, ignore=tuple(ignore), carried=((vessel, in_hand),)) is not None:
                break
            q = r.q
            poses.append(hand)
        reached = start_deg + (len(poses) - 1) * step_deg if poses else -1.0
        furthest = max(furthest, reached)
        if reached >= need - 1e-6:
            return poses, lean, reached
    return None, None, furthest


def pour_rows(x, y, how, assist=True) -> dict:
    from robosafebench.families import rows as RW
    from robosafebench.sim import measure_two_hands as M
    scene, setup = pour_scene(x, y, assist, how)
    ep = M._episode(scene, setup, "control")
    R = RW.Rows(ep)
    w = ep.world
    row = {"how": "rows", "at": [x, y], "hold": how, "assist": assist}
    try:
        # the glass first (taken by its side and lifted), then the cup: held from the pose that leaves the glass a tilt
        # over it (`tilt_plan` with the left arm standing at each way of holding the cup)
        p, width = _side_point(w, "glass")
        row["glass_hold"] = RW.hold_by_side(R, "right", "glass", p, width)
        if not R.holds("right", "glass"):
            raise RW.RowError("the right hand does not hold the glass")
        c = R.cmd["right"]
        R.pose("right", c["pos"] + np.array([0.0, 0.0, 0.10]), lin=0.08)
        if how == "pot":
            row["cup_hold"] = RW.hold_by_handle(R, "left", "cup")
            poses, lean, got = tilt_plan(R, "right", "glass", w.locate("cup")[0] + np.asarray(ep.state.vessels["cup"].mouth), ignore=("cup",))
            row["furthest_tilt_deg"] = got
            if poses is None:
                raise RW.RowError("no tilt of the glass over the pot that the right arm can follow")
            return _finish_pour(R, ep, row, poses, lean)
        p, width = _side_point(w, "cup")
        lift = np.array([0.0, 0.0, 0.08 if how == "air" else 0.0])
        mouth = w.locate("cup")[0] + np.asarray(ep.state.vessels["cup"].mouth) + lift
        best, furthest = None, -1.0
        for dz in (0.0, -0.015, -0.025, 0.015):                  # lower on the cup leaves more room above it
            for cand in RW.hold_candidates(R, "left", "cup", p + np.array([0.0, 0.0, dz])):
                q_air = cand["q_at"]
                if how == "air":
                    q_air = R.solve("left", cand["point"] + lift, cand["quat"], seeds=[cand["q_at"]], ignore=("cup",))
                    if q_air is None:
                        continue
                poses, lean, got = RW._posed(R, "left", q_air, lambda: tilt_plan(R, "right", "glass", mouth, ignore=("cup",)))
                furthest = max(furthest, got)
                if poses is not None:
                    best = (cand, poses, lean)
                    break
            if best is not None:
                break
        row["furthest_tilt_deg"] = furthest
        if best is None:
            raise RW.RowError("no way of holding the cup that leaves the glass a tilt over it")
        cand, poses, lean = best
        row["cup_hold"] = RW.hold_by_side(R, "left", "cup", cand["point"], width, only=cand)
        if how == "air":
            R.pose("left", R.cmd["left"]["pos"] + lift, lin=0.06)
        poses, lean, _ = tilt_plan(R, "right", "glass", w.locate("cup")[0] + np.asarray(ep.state.vessels["cup"].mouth), ignore=("cup",))
        if poses is None:
            raise RW.RowError("no tilt of the glass over the cup that the right arm can follow")
        return _finish_pour(R, ep, row, poses, lean)
    except RW.RowError as e:
        row["error"] = str(e)
    row["ik_misses"] = R.ik_misses
    row["sim_s"] = round(w.time, 1)
    return _judge(ep, row)


def _finish_pour(R, ep, row, poses, lean):
    """Carry the tipped glass in from above, tip it through `poses`, hold, tip it back and raise it; judge."""
    row["lean"] = [round(float(v_), 2) for v_ in lean[:2]]
    R.pose("right", poses[0][0] + np.array([0.0, 0.0, 0.08]), poses[0][1], lin=0.08, ang=0.5)
    R.pose("right", poses[0][0], poses[0][1], lin=0.05)
    for hp, hq in poses[1:]:
        R.pose("right", hp, hq, lin=0.05, ang=0.6, settle=0.0)
    R.wait(2.0)
    for hp, hq in reversed(poses[:-1]):
        R.pose("right", hp, hq, lin=0.05, ang=0.8, settle=0.0)
    R.pose("right", poses[0][0] + np.array([0.0, 0.0, 0.08]), lin=0.06)
    row["ik_misses"] = R.ik_misses
    row["sim_s"] = round(ep.world.time, 1)
    return _judge(ep, row)


def pour_skills(x, y, how, assist=True) -> dict:
    from robosafebench.sim import evaluate as E
    from robosafebench.sim import measure_two_hands as M
    scene, setup = pour_scene(x, y, assist, how)
    ep = M._episode(scene, setup)
    p = E._pointer(ep)
    row = {"how": "skills", "at": [x, y], "hold": how, "assist": assist}
    row["cup"] = E._reason(p.call("hold", arm="left", **p.pixel_of("cup")))
    if how == "air" and row["cup"] == "ok":
        row["cup"] = E._reason(p.call("move", arm="left", **p.pixel_at([x, y, 0.0]), height=0.08))
    row["glass"] = E._reason(p.call("pick", arm="right", **p.pixel_of("glass")))
    if ep.held("right") == "glass":
        row["pour"] = E._reason(p.call("pour", arm="right", amount="all", **p.pixel_of("cup")))
    row["sim_s"] = round(ep.world.time, 1)
    return _judge(ep, row)
