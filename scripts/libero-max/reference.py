"""Scripted reference controller for LIBERO-MAX cases (authoring only; never copied anywhere the agent can reach).

Privileged, closed loop: every control step it re-reads the hand, the fingers and the objects (MuJoCo state), so when
the event moves an object or a receptacle it goes after the new pose. It handles goals made of LIBERO's On / In
predicates, one after the other: grasp the object across its narrow side (bowls: at the rim, closing across the
wall), lift, carry it until the OBJECT (not the hand) is over the target, lower it until it is just above the target,
release, retreat, then wait for LIBERO's success check. Other predicates (Open, Close, TurnOn, ...) raise Unsupported.
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
    return {"centre": centre, "half": (hi - lo) / 2, "R": Rb, "top": pts[:, 2].max(), "bottom": pts[:, 2].min()}


def obj_bbox(s, name: str) -> dict:
    ent, _ = s.wrapped.backend._entity(name)
    return body_bbox(s, ent.root_body)


def target_point(s, name: str) -> tuple[np.ndarray, float]:
    """(xy centre, height to release above) of a target: an object (its box) or a LIBERO region site."""
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


def grasp_plan(s, obj: str) -> tuple[np.ndarray, float]:
    """(grasp point, wanted finger angle) for the object as it is now."""
    b = obj_bbox(s, obj)
    hx, hy = b["half"][:2]
    ax, ay = b["R"][:, 0], b["R"][:, 1]
    if min(hx, hy) * 2 <= MAX_OPEN:  # close across the narrow horizontal side, at mid height (not into the table)
        axis = ax if hx <= hy else ay
        z = max(b["centre"][2], b["top"] - 0.03)
        return np.r_[b["centre"][:2], z], float(np.arctan2(axis[1], axis[0]))
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

    if not go("carry", lambda: over(0.08), 1.0, 0.015):
        return
    if not go("lower", lambda: over(0.0), 1.0, 0.01):
        return
    for _ in range(12):
        if budget():
            act(s, s.eef()["pos"], -1.0)
    up = s.eef()["pos"] + [0, 0, 0.10]
    go("retreat", lambda: up, -1.0, 0.03, max_t=40)
    log["phase"] = f"{obj}:placed"


def plan_goals(s) -> list:
    steps = []
    for g in s.goal():
        pred = str(g[0]).lower()
        if pred in ("on", "in") and len(g) == 3:
            steps.append((pred, g[1], g[2]))
        else:
            raise Unsupported(f"goal predicate {g}")
    if not steps:
        raise Unsupported("empty goal")
    return steps


def run(s) -> dict:
    log = {"goals": plan_goals(s)}
    for pred, obj, tgt in log["goals"]:
        if s.done:
            break
        pick_place(s, pred, obj, tgt, log)
    hold = np.array([0, 0, 0, 0, 0, 0, -1.0])
    for _ in range(40):  # the last goal may hold only once the object settles
        if s.done or len(s.actions) >= s.max_steps:
            break
        s.step(hold)
    return log
