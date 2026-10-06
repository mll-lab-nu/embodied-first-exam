"""Scripted reference controller for LIBERO-MAX cases (authoring only; never copied anywhere the agent can reach).

Privileged, closed loop: every control step it re-reads the hand, the fingers and the objects (MuJoCo state), so when
the event moves an object or a receptacle it goes after the new pose. Goals, in this order:
- Open (a drawer): grasp its handle (the part of the drawer that sticks out furthest) and pull along the slide;
- On / In: grasp the object across its narrow side (bowls: at the rim, closing across the wall; mugs: the same at the
  cup's wall, away from the handle), lift, carry it until the OBJECT (not the hand) is over the target, lower it until
  it is just above the target, release, retreat; a target inside a closed drawer has the drawer opened first;
- TurnOn / TurnOff (a stove knob): grasp the knob at its axis and turn the wrist until LIBERO's range is reached;
- Close (a drawer: push its front panel beside the handle, on the robot's side unless an object stands there, and
  finish on the handle; a hinged door: push it shut along its arc).
Unsupported: objects wider than the open gripper that are not bowls or mugs (plates, moka pots), placing into a
microwave (it needs a sideways approach).
Then it waits for LIBERO's success check.
"""

from __future__ import annotations

import mujoco
import numpy as np

MAX_OPEN = 0.075  # the Panda gripper closes on objects up to about this width
K_POS, K_YAW = 10.0, 3.0


class Unsupported(Exception):
    pass


def _ids(s):
    m = s.sim.model._model
    return m, s.sim.data._data


def body_bbox(s, body: str) -> dict:
    """World-frame box of every colliding geom under `body` (a LIBERO object's root body), from MuJoCo's geom AABBs."""
    m, d = _ids(s)
    root = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, body)
    pts = []
    for g in range(m.ngeom):
        x = int(m.geom_bodyid[g])
        while x not in (0, root):
            x = int(m.body_parentid[x])
        if x != root or (m.geom_contype[g] == 0 and m.geom_conaffinity[g] == 0):
            continue
        c, h = m.geom_aabb[g][:3], m.geom_aabb[g][3:]
        R = d.geom_xmat[g].reshape(3, 3)
        for corner in np.array(np.meshgrid([-1, 1], [-1, 1], [-1, 1])).T.reshape(-1, 3):
            pts.append(d.geom_xpos[g] + R @ (c + h * corner))
    if not pts:
        raise Unsupported(f"no colliding geometry under {body}")
    pts = np.asarray(pts)
    Rb = d.xmat[root].reshape(3, 3)
    loc = (pts - d.xpos[root]) @ Rb
    lo, hi = loc.min(0), loc.max(0)
    centre = d.xpos[root] + Rb @ ((lo + hi) / 2)
    return {"centre": centre, "half": (hi - lo) / 2, "R": Rb, "top": pts[:, 2].max(), "bottom": pts[:, 2].min(),
            "min": pts.min(0), "max": pts.max(0)}


def obj_bbox(s, name: str) -> dict:
    ent, _ = s.wrapped.backend._entity(name)
    return body_bbox(s, ent.root_body)


def target_point(s, name: str) -> tuple[np.ndarray, float]:
    """(xy centre, height to release above) of a target: an object (its box) or a LIBERO region site. An open drawer's
    region: the middle of the part that is out of the cabinet (half the opening behind the drawer's front panel)."""
    if name in s.env.object_sites_dict and drawer_site(s, name):
        j = joint_of(s, name)
        c, u = handle_point(s, j)
        q = jinfo(s, j)["q"]
        front = c - u * 0.027
        p = np.asarray(s.sim.data.get_site_xpos(name), float)
        xy = (front - u * (abs(q) / 2))[:2]
        return np.r_[xy, p[2]], p[2]
    if name in s.env.object_sites_dict:
        p = np.asarray(s.sim.data.get_site_xpos(name), float)
        return p, p[2]
    b = obj_bbox(s, name)
    return b["centre"], b["top"]


def finger_angle(s) -> float:
    m, d = _ids(s)
    lf = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "gripper0_leftfinger")
    rf = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "gripper0_rightfinger")
    v = d.xpos[lf] - d.xpos[rf]
    return float(np.arctan2(v[1], v[0]))


def wrap180(a: float) -> float:
    """An angle difference modulo pi (the fingers are symmetric), in [-pi/2, pi/2)."""
    return (a + np.pi / 2) % np.pi - np.pi / 2


def cup_frame(s, obj: str) -> tuple[np.ndarray, float, np.ndarray | None]:
    """(cup centre, wall radius, horizontal direction of the handle or None) of a mug: the mean of its geoms, again
    without the ones well beyond the wall ring (the handle)."""
    ent, _ = s.wrapped.backend._entity(obj)
    pts = np.array([c for c, _ in geoms_of(s, ent.root_body)])
    c = pts.mean(0)
    for _ in range(3):
        dist = np.linalg.norm((pts - c)[:, :2], axis=1)
        keep = dist <= 1.5 * np.median(dist)
        c = pts[keep].mean(0)
    dist = np.linalg.norm((pts - c)[:, :2], axis=1)
    keep = dist <= 1.5 * np.median(dist)
    r = float(np.percentile(dist[keep], 90))
    hdir = None
    if (~keep).any():
        h = pts[~keep].mean(0)[:2] - c[:2]
        hdir = h / (np.linalg.norm(h) + 1e-9)
    return c, r, hdir


def grasp_plan(s, obj: str) -> tuple[np.ndarray, float]:
    """(grasp point, wanted finger angle) for the object as it is now."""
    b = obj_bbox(s, obj)
    hx, hy = b["half"][:2]
    ax, ay = b["R"][:, 0], b["R"][:, 1]
    if min(hx, hy) * 2 <= MAX_OPEN:  # close across the narrow horizontal side, at mid height (not into the table)
        axis = ax if hx <= hy else ay
        z = max(b["centre"][2], b["top"] - 0.03)
        return np.r_[b["centre"][:2], z], float(np.arctan2(axis[1], axis[0]))
    if "mug" in obj:  # rim grasp on the cup's wall facing the hand, away from the handle
        c, r, hdir = cup_frame(s, obj)
        d = s.eef()["pos"][:2] - c[:2]
        d = d / (np.linalg.norm(d) + 1e-9)
        if hdir is not None and d @ hdir > 0.5:   # within 60 degrees of the handle: turn to 90 degrees from it
            side = np.array([-hdir[1], hdir[0]])
            d = side if side @ d >= 0 else -side
        return np.r_[c[:2] + r * d, b["top"] - 0.015], float(np.arctan2(d[1], d[0]))
    if "bowl" in obj:  # rim grasp on the side facing the hand, fingers across the wall (radial)
        e = s.eef()["pos"]
        d = e[:2] - b["centre"][:2]
        d = d / (np.linalg.norm(d) + 1e-9)
        r = min(hx, hy) - 0.012
        return np.r_[b["centre"][:2] + r * d, b["top"] - 0.015], float(np.arctan2(d[1], d[0]))
    raise Unsupported(f"{obj} is wider than the gripper ({2 * hx:.3f} x {2 * hy:.3f} m)")


def act(s, goal: np.ndarray, grip: float, yaw: float | None = None) -> float:
    e = s.eef()["pos"]
    err = goal - e
    a = np.zeros(7)
    a[:3] = np.clip(err * K_POS, -1, 1)
    if yaw is not None:
        a[5] = np.clip(wrap180(yaw - finger_angle(s)) * K_YAW, -1, 1)
    a[6] = grip
    if not s.done and len(s.actions) < s.max_steps:   # LIBERO ends the episode the moment its check holds
        s.step(a)
    return float(np.linalg.norm(err))


def pick_place(s, pred: str, obj: str, tgt: str, log: dict) -> None:
    def budget() -> bool:
        return not s.done and len(s.actions) < s.max_steps

    def go(name, goal_fn, grip, tol, yaw_fn=None, max_t=120):
        t0 = len(s.actions)
        while budget() and len(s.actions) - t0 < max_t:
            if act(s, goal_fn(), grip, yaw_fn() if yaw_fn else None) < tol:
                return True
        log["phase"] = f"{obj}:{name}"
        b = obj_bbox(s, obj)
        note(s, log, f"pick {obj}:{name} failed goal={np.round(goal_fn(), 3).tolist()} eef={np.round(s.eef()['pos'], 3).tolist()} "
                     f"obj c={np.round(b['centre'], 3).tolist()} half={np.round(b['half'], 3).tolist()} top={b['top']:.3f} "
                     f"fingers={finger_angle(s):.2f} contacts={hand_contacts(s)}")
        return False

    yaw_ok = lambda: abs(wrap180(grasp_plan(s, obj)[1] - finger_angle(s))) < np.radians(4)  # noqa: E731
    above = lambda: grasp_plan(s, obj)[0] + [0, 0, 0.10]  # noqa: E731
    if not go("above", above, -1.0, 0.012, lambda: grasp_plan(s, obj)[1]):
        return
    t0 = len(s.actions)
    while budget() and not yaw_ok() and len(s.actions) - t0 < 60:
        act(s, above(), -1.0, grasp_plan(s, obj)[1])
    if not go("down", lambda: grasp_plan(s, obj)[0], -1.0, 0.008, lambda: grasp_plan(s, obj)[1]):
        return
    g = grasp_plan(s, obj)[0]
    for _ in range(15):
        if budget():
            act(s, g, 1.0)
    tz = target_point(s, tgt)[1]
    lift_z = max(s.eef()["pos"][2] + 0.12, tz + 0.25)
    if not go("lift", lambda: np.r_[s.eef()["pos"][:2], lift_z], 1.0, 0.02):
        return
    held = obj_bbox(s, obj)["bottom"] > tz + 0.05 or obj_bbox(s, obj)["bottom"] > g[2] + 0.03
    if not held:
        log["phase"] = f"{obj}:not held after lift"
        return

    def over(dz):
        tp, top = target_point(s, tgt)
        b = obj_bbox(s, obj)
        e = s.eef()["pos"]
        off = e - b["centre"]
        drop = (top + (0.03 if pred == "in" else 0.015)) - b["bottom"]  # object's bottom just above the target
        return np.r_[tp[:2] + off[:2], e[2] + drop + dz]

    into_drawer = tgt in s.env.object_sites_dict and drawer_site(s, tgt)
    if not go("carry", lambda: over(0.08), 1.0, 0.03 if into_drawer else 0.015):
        return
    if not go("lower", lambda: over(0.0), 1.0, 0.025 if into_drawer else 0.01, max_t=60 if into_drawer else 120):
        return
    for _ in range(12):
        if budget():
            act(s, s.eef()["pos"], -1.0)
    up = s.eef()["pos"] + [0, 0, 0.10]
    go("retreat", lambda: up, -1.0, 0.03, max_t=40)
    log["phase"] = f"{obj}:placed"
    note(s, log, log["phase"])


# ------------------------------------------------------------------------------------------------ articulated goals
OPEN_Q, IS_OPEN_Q, PLACE_OPEN_Q, CLOSE_Q = -0.157, -0.14, -0.153, 0.001   # drawers: LIBERO's open is q < -0.14, closed q > 0.0 (range [-0.16, 0.01])
TURN_ON_Q, TURN_OFF_Q = 0.7, -0.004  # stove knob: on q >= 0.5, off q < 0.0
DOOR_CLOSED_Q = -0.002               # microwave door: closed q > -0.005


def joint_of(s, name: str) -> str:
    if name in s.env.object_sites_dict and getattr(s.env.object_sites_dict[name], "joints", None):
        return list(s.env.object_sites_dict[name].joints)[0]
    try:
        js = s.env.get_object(name).joints
    except Exception:  # noqa: BLE001 -- not an object of this scene
        js = None
    if not js:
        raise Unsupported(f"{name} has no joint")
    return list(js)[0]


def jinfo(s, j: str) -> dict:
    m, d = _ids(s)
    jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, j)
    if jid < 0:
        raise Unsupported(f"no joint {j}")
    return {"id": jid, "q": float(d.qpos[m.jnt_qposadr[jid]]), "axis": d.xaxis[jid].copy(), "anchor": d.xanchor[jid].copy(),
            "type": int(m.jnt_type[jid]), "body": mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, m.jnt_bodyid[jid])}


def geoms_of(s, body: str) -> list:
    """World centres and AABB half sizes of the colliding geoms under `body`."""
    m, d = _ids(s)
    root = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, body)
    out = []
    for g in range(m.ngeom):
        x = int(m.geom_bodyid[g])
        while x not in (0, root):
            x = int(m.body_parentid[x])
        if x == root and (m.geom_contype[g] or m.geom_conaffinity[g]):
            R = d.geom_xmat[g].reshape(3, 3)
            out.append((d.geom_xpos[g].copy(), np.abs(R) @ m.geom_aabb[g][3:]))
    return out


def handle_point(s, j: str) -> tuple[np.ndarray, np.ndarray]:
    """(handle centre, opening direction) of a drawer: the drawer geom that sticks out furthest along the opening
    direction (q decreases to open, so the drawer moves along -axis)."""
    ji = jinfo(s, j)
    u = -ji["axis"] / np.linalg.norm(ji["axis"])
    c, h = max(geoms_of(s, ji["body"]), key=lambda gh: float(gh[0] @ u))
    return c, u


def hand_contacts(s) -> list:
    m, d = _ids(s)
    out = set()
    for c in d.contact[:d.ncon]:
        a, b = (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or f"g{g}" for g in (c.geom1, c.geom2))
        for x, y in ((a, b), (b, a)):
            if ("gripper" in x or "robot" in x) and not ("gripper" in y or "robot" in y):
                out.add(f"{x}>{y}")
    return sorted(out)


def note(s, log: dict, msg: str) -> None:
    log.setdefault("trace", []).append(f"{len(s.actions)}:{msg}")


def _drive(s, target_fn, grip, done_fn, max_t, yaw_fn=None) -> bool:
    t0 = len(s.actions)
    while not s.done and len(s.actions) < s.max_steps and len(s.actions) - t0 < max_t:
        if done_fn():
            return True
        act(s, target_fn(), grip, yaw_fn() if yaw_fn else None)
    return done_fn()


def _reach(s, goal, grip, tol, max_t=120, yaw=None) -> bool:
    return _drive(s, lambda: goal, grip, lambda: np.linalg.norm(goal - s.eef()["pos"]) < tol, max_t,
                  (lambda: yaw) if yaw is not None else None)


def open_drawer(s, site: str, log: dict) -> None:
    j = joint_of(s, site)
    c, u = handle_point(s, j)
    yaw = float(np.arctan2(-u[0], u[1]))   # fingers close across the opening direction (straddle the vertical bar)
    _reach(s, c + u * 0.02 + [0, 0, 0.10], -1.0, 0.02, yaw=yaw)
    note(s, log, "open: above")
    _drive(s, lambda: c + u * 0.02 + [0, 0, 0.10], -1.0, lambda: abs(wrap180(yaw - finger_angle(s))) < np.radians(6), 40, lambda: yaw)
    _reach(s, c, -1.0, 0.025, max_t=40, yaw=yaw)
    note(s, log, f"open: at handle eef={np.round(s.eef()['pos'] - c, 3).tolist()}")
    for _ in range(8):
        act(s, c, 1.0)
    _drive(s, lambda: handle_point(s, j)[0] + u * 0.08, 1.0, lambda: jinfo(s, j)["q"] < OPEN_Q, 120)
    note(s, log, f"open: pulled q={jinfo(s, j)['q']:.3f}")
    for _ in range(6):
        act(s, s.eef()["pos"], -1.0)
    back = s.eef()["pos"] + u * 0.04 + [0, 0, 0.10]
    _reach(s, back, -1.0, 0.04, max_t=30)
    log["phase"] = f"{site}:opened q={jinfo(s, j)['q']:.3f}"
    note(s, log, log["phase"])


def _clearance(s, pts: list, handle: np.ndarray, u: np.ndarray, w: np.ndarray) -> float:
    """Smallest horizontal distance from `pts` to the box of any movable object at hand height, ignoring what is in the
    drawer (behind its handle, within its width)."""
    best = 1.0
    for name in s.env.objects_dict:
        try:
            b = obj_bbox(s, name)
        except Exception:  # noqa: BLE001 -- no geometry: nothing to hit
            continue
        rel = b["centre"] - handle
        if (rel @ u < 0 and abs(rel @ w) < 0.12) or b["top"] < min(p[2] for p in pts) - 0.03:
            continue
        lo, hi = b["min"][:2], b["max"][:2]
        for p in pts:
            best = min(best, float(np.linalg.norm(np.maximum(0, np.maximum(lo - p[:2], p[:2] - hi)))))
    return best


def close_drawer(s, site: str, log: dict) -> None:
    """Push the drawer shut with the closed fingers on its front panel beside the handle, on the robot's side unless an
    object stands there; if the push stalls (something in the way), back off and push from the other side."""
    j = joint_of(s, site)
    if jinfo(s, j)["q"] > CLOSE_Q:
        return
    c, u = handle_point(s, j)
    w0 = np.array([-u[1], u[0], 0.0])                    # across the drawer, horizontal
    shut = c - u * abs(jinfo(s, j)["q"])                 # the handle once the drawer is closed
    room = {sg: _clearance(s, [shut + sg * w0 * 0.06 + u * k for k in (0.0, 0.05, 0.10)], c, u, w0) for sg in (1, -1)}
    toward_robot = 1 if w0 @ (s.robot_base()["pos"] - c) >= 0 else -1
    sides = [toward_robot, -toward_robot]       # the wrist trails toward the robot: on the far side it meets the drawer above
    if room[toward_robot] < 0.03 < room[-toward_robot]:
        sides.reverse()
    note(s, log, f"close: room={ {k: round(v, 3) for k, v in room.items()} } sides={sides}")
    for sg in sides:
        w = sg * w0
        side = lambda: handle_point(s, j)[0] + w * 0.06 - u * 0.025   # noqa: E731,B023 -- the front panel beside the handle
        start = side() + u * 0.07
        _reach(s, s.eef()["pos"] + u * 0.06 + [0, 0, 0.12], 1.0, 0.03, max_t=40)
        _reach(s, start + [0, 0, 0.12], 1.0, 0.02)
        _reach(s, start, 1.0, 0.012)
        hist = [jinfo(s, j)["q"]]

        def done_or_stalled():
            hist.append(jinfo(s, j)["q"])
            return hist[-1] > CLOSE_Q or (len(hist) > 30 and hist[-1] - hist[-30] < 0.003)
        _drive(s, lambda: side() - u * 0.08, 1.0, done_or_stalled, 160)   # noqa: B023
        note(s, log, f"close: pushed q={jinfo(s, j)['q']:.3f} eef-side={np.round(s.eef()['pos'] - side(), 3).tolist()} "
                     f"contacts={hand_contacts(s)}")
        if jinfo(s, j)["q"] > CLOSE_Q:
            break
        if jinfo(s, j)["q"] > -0.03:
            # nearly flush: the hand meets the drawer above, so finish on the handle, which stands 2.7 cm proud
            hp = lambda: handle_point(s, j)[0]   # noqa: E731
            _reach(s, s.eef()["pos"] + u * 0.04, 1.0, 0.012, max_t=30)
            _reach(s, hp() + u * 0.035, 1.0, 0.01, max_t=60)
            hist[:] = [jinfo(s, j)["q"]]
            _drive(s, lambda: hp() - u * 0.05, 1.0, done_or_stalled, 80)
            note(s, log, f"close: on handle q={jinfo(s, j)['q']:.3f} contacts={hand_contacts(s)}")
            if jinfo(s, j)["q"] > CLOSE_Q:
                break
    _reach(s, s.eef()["pos"] + u * 0.05 + [0, 0, 0.08], 1.0, 0.03, max_t=40)
    log["phase"] = f"{site}:closed q={jinfo(s, j)['q']:.3f}"
    note(s, log, log["phase"])


def close_door(s, obj: str, log: dict) -> None:
    """A hinged door about a vertical axis, closed as q rises to 0: push it shut, the fingers behind its free part."""
    j = joint_of(s, obj)
    ji = jinfo(s, j)
    if ji["q"] > DOOR_CLOSED_Q:
        return
    A = ji["anchor"]
    gs = geoms_of(s, ji["body"])
    zc = float(np.mean([c[2] for c, _ in gs]))

    def frame():
        g = geoms_of(s, jinfo(s, j)["body"])
        far = max(g, key=lambda gh: float(np.linalg.norm((gh[0] - A)[:2])))[0]
        r = (far - A)[:2]
        R = float(np.linalg.norm(r))
        rh = r / R
        t = np.array([-rh[1], rh[0]])          # +z rotation (q rising)
        return rh, t, R

    def push_point(lead: float):
        rh, t, R = frame()
        ang = np.arctan2(rh[1], rh[0]) + lead
        p = A[:2] + 0.7 * R * np.array([np.cos(ang), np.sin(ang)]) - 0.06 * np.array([-np.sin(ang), np.cos(ang)])
        return np.r_[p, zc - 0.03]

    p0 = push_point(0.0)
    door_yaw = lambda: float(np.arctan2(frame()[0][1], frame()[0][0]))   # noqa: E731 -- finger axis along the door
    note(s, log, f"door q={ji['q']:.3f} A={np.round(A, 3).tolist()} p0={np.round(p0, 3).tolist()} frame={[np.round(x, 3).tolist() for x in frame()[:2]]}")
    _reach(s, p0 + [0, 0, 0.15], 1.0, 0.02, yaw=door_yaw())
    note(s, log, f"above q={jinfo(s, j)['q']:.3f}")
    _reach(s, p0, 1.0, 0.012, yaw=door_yaw())
    note(s, log, f"down q={jinfo(s, j)['q']:.3f} eef={np.round(s.eef()['pos'], 3).tolist()}")
    _drive(s, lambda: push_point(0.6), 1.0, lambda: jinfo(s, j)["q"] > DOOR_CLOSED_Q, 220, door_yaw)
    _reach(s, s.eef()["pos"] + [0, 0, 0.10], 1.0, 0.03, max_t=40)
    log["phase"] = f"{obj}:closed q={jinfo(s, j)['q']:.3f}"
    note(s, log, log["phase"])


def turn_knob(s, obj: str, on: bool, log: dict) -> None:
    j = joint_of(s, obj)
    ji = jinfo(s, j)
    b = body_bbox(s, ji["body"])
    hx, hy = b["half"][:2]
    axis = b["R"][:, 0] if hx <= hy else b["R"][:, 1]
    yaw = float(np.arctan2(axis[1], axis[0]))
    g = np.r_[ji["anchor"][:2], b["top"] - 0.015]
    _reach(s, g + [0, 0, 0.10], -1.0, 0.012, yaw=yaw)
    _drive(s, lambda: g + [0, 0, 0.10], -1.0, lambda: abs(wrap180(yaw - finger_angle(s))) < np.radians(4), 60, lambda: yaw)
    _reach(s, g, -1.0, 0.006, yaw=yaw)
    for _ in range(12):
        act(s, g, 1.0)
    sign = 1.0 if on else -1.0
    done = (lambda: jinfo(s, j)["q"] >= TURN_ON_Q) if on else (lambda: jinfo(s, j)["q"] < TURN_OFF_Q)
    _drive(s, lambda: g, 1.0, done, 120, lambda: finger_angle(s) + sign * 0.35)
    for _ in range(10):
        act(s, s.eef()["pos"], -1.0)
    _reach(s, s.eef()["pos"] + [0, 0, 0.10], -1.0, 0.03, max_t=40)
    log["phase"] = f"{obj}:turned q={jinfo(s, j)['q']:.3f}"
    note(s, log, log["phase"])


def drawer_site(s, name: str) -> bool:
    if name not in s.env.object_sites_dict or not getattr(s.env.object_sites_dict[name], "joints", None):
        return False
    return jinfo(s, joint_of(s, name))["type"] == mujoco.mjtJoint.mjJNT_SLIDE


def plan_goals(s) -> list:
    """(kind, args) in execution order: opens, then placements (a target in a closed drawer opened first), then knob
    turns, then closes."""
    opens, places, turns, closes = [], [], [], []
    for g in s.goal():
        pred = str(g[0]).lower()
        if pred in ("on", "in") and len(g) == 3:
            if "microwave" in g[2]:
                raise Unsupported(f"placing into {g[2]} needs a sideways approach")
            if drawer_site(s, g[2]) and jinfo(s, joint_of(s, g[2]))["q"] > PLACE_OPEN_Q and ("open", g[2]) not in opens:
                opens.append(("open", g[2]))
            places.append((pred, g[1], g[2]))
        elif pred == "open" and len(g) == 2 and drawer_site(s, g[1]):
            opens.append(("open", g[1]))
        elif pred in ("turnon", "turnoff") and len(g) == 2:
            turns.append((pred, g[1]))
        elif pred == "close" and len(g) == 2:
            closes.append(("close", g[1]))
        else:
            raise Unsupported(f"goal predicate {g}")
    steps = opens + places + turns + closes
    if not steps:
        raise Unsupported("empty goal")
    return steps


def run(s) -> dict:
    log = {"goals": plan_goals(s)}
    for step in log["goals"]:
        if s.done:
            break
        kind = step[0]
        if kind in ("on", "in"):
            pick_place(s, kind, step[1], step[2], log)
        elif kind == "open":
            open_drawer(s, step[1], log)
        elif kind in ("turnon", "turnoff"):
            turn_knob(s, step[1], kind == "turnon", log)
        elif kind == "close":
            if drawer_site(s, step[1]):
                close_drawer(s, step[1], log)
            else:
                close_door(s, step[1], log)
    hold = np.array([0, 0, 0, 0, 0, 0, -1.0])
    for _ in range(40):  # the last goal may hold only once the object settles
        if s.done or len(s.actions) >= s.max_steps:
            break
        s.step(hold)
    return log
