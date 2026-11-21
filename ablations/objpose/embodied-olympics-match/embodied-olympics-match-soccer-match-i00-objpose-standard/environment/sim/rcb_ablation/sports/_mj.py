"""MuJoCo readers for the state tables: a body's pose and velocity, a free joint's state, joint positions and
velocities. Only reads (mj_objectVelocity reads the data's last forward pass; nothing is stepped)."""
from __future__ import annotations

import numpy as np

POSE = {"pos": "m", "quat": "wxyz", "lin_vel": "m/s", "ang_vel": "rad/s"}
JOINTS = {"joint_pos": "rad or m", "joint_vel": "rad/s or m/s",
          "joint_range": "{joint: [lower, upper]} rad or m (null: not limited)"}
FIELDS = ("pos", "quat", "size", "bbox", "lin_vel", "ang_vel", "joint_pos", "joint_vel", "joint_range",
          "height_above_ground")                     # the only fields a state table has
KINDS = ("robot", "robot_link", "object", "articulation", "scene_feature")
GOAL = {"pos": "m (the centre of its box)", "size": "[3] m (full extents)",
        "bbox": "[[x, y, z] min, [x, y, z] max] m (axis-aligned, in the frame)"}
BOX = {"size": "[3] m (full extents along the entity's own axes)",
       "bbox": "[[x, y, z] min, [x, y, z] max] m (axis-aligned, in the frame)"}
_SIGNS = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], float)


def r(x, n=5):
    return [round(float(v), n) for v in np.asarray(x, float).ravel()]


def body_id(model, name):
    import mujoco as mj
    i = mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, name)
    if i < 0:
        raise KeyError(f"no body {name!r}")
    return i


def body(model, data, name_or_id) -> dict:
    """World pose and velocity of a body (its frame's origin)."""
    import mujoco as mj
    i = name_or_id if isinstance(name_or_id, (int, np.integer)) else body_id(model, name_or_id)
    v = np.zeros(6)
    mj.mj_objectVelocity(model, data, mj.mjtObj.mjOBJ_BODY, int(i), v, 0)      # [angular, linear], world frame
    return {"pos": r(data.xpos[i]), "quat": r(data.xquat[i], 6), "lin_vel": r(v[3:]), "ang_vel": r(v[:3])}


def site(model, data, name) -> dict:
    import mujoco as mj
    i = mj.mj_name2id(model, mj.mjtObj.mjOBJ_SITE, name)
    if i < 0:
        raise KeyError(f"no site {name!r}")
    v = np.zeros(6)
    mj.mj_objectVelocity(model, data, mj.mjtObj.mjOBJ_SITE, i, v, 0)
    q = np.zeros(4)
    mj.mju_mat2Quat(q, data.site_xmat[i])
    return {"pos": r(data.site_xpos[i]), "quat": r(q, 6), "lin_vel": r(v[3:]), "ang_vel": r(v[:3])}


def free_joint(model, data, joint) -> dict:
    """A free joint's state from qpos / qvel (position, wxyz, linear velocity, angular velocity: MuJoCo's convention
    for a free joint, the angular velocity in the body's local frame is converted to the world frame)."""
    import mujoco as mj
    j = joint if isinstance(joint, (int, np.integer)) else mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, joint)
    if j < 0:
        raise KeyError(f"no joint {joint!r}")
    a, b = model.jnt_qposadr[j], model.jnt_dofadr[j]
    quat = np.asarray(data.qpos[a + 3:a + 7], float)
    w_local = np.asarray(data.qvel[b + 3:b + 6], float)
    R = np.zeros(9)
    mj.mju_quat2Mat(R, quat)
    return {"pos": r(data.qpos[a:a + 3]), "quat": r(quat, 6), "lin_vel": r(data.qvel[b:b + 3]),
            "ang_vel": r(R.reshape(3, 3) @ w_local)}


def joints(model, data, names) -> dict:
    import mujoco as mj
    pos, vel, rng = {}, {}, {}
    for n in names:
        j = mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, n)
        if j < 0:
            continue
        pos[n] = round(float(data.qpos[model.jnt_qposadr[j]]), 6)
        vel[n] = round(float(data.qvel[model.jnt_dofadr[j]]), 6)
        rng[n] = r(model.jnt_range[j], 6) if bool(model.jnt_limited[j]) else None
    return {"joint_pos": pos, "joint_vel": vel, "joint_range": rng}


def strip(d: dict, prefix_len=None, sep=None) -> dict:
    """joint_pos / joint_vel / joint_range keyed by the joint's name without its robot's prefix."""
    def key(k):
        return k.split(sep, 1)[1] if sep else k[prefix_len:]
    for f in ("joint_pos", "joint_vel", "joint_range"):
        if f in d:
            d[f] = {key(k): v for k, v in d[f].items()}
    return d


def yaw_quat(yaw) -> list:
    """wxyz of a rotation by yaw about z."""
    return r([np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)], 6)


def joint_names(model, pattern=None):
    import re
    import mujoco as mj
    out = []
    for j in range(model.njnt):
        n = mj.mj_id2name(model, mj.mjtObj.mjOBJ_JOINT, j) or ""
        if model.jnt_type[j] in (2, 3) and (pattern is None or re.search(pattern, n)):     # slide, hinge
            out.append(n)
    return out


def body_geoms(model, b: int, subtree: bool = False) -> list:
    """The geoms of body b and of the bodies below it: every one (subtree) or those fixed to it (no joint between)."""
    out, todo = [], [int(b)]
    while todo:
        c = todo.pop()
        out += list(range(int(model.body_geomadr[c]), int(model.body_geomadr[c]) + int(model.body_geomnum[c])))
        todo += [k for k in range(c + 1, model.nbody)
                 if int(model.body_parentid[k]) == c and (subtree or not model.body_jntnum[k])]
    return out


def _corners(model, data, g: int):
    """The 8 corners of geom g's own bounding box (model.geom_aabb), world frame, in the current state."""
    c, h = model.geom_aabb[g][:3], model.geom_aabb[g][3:]
    return (c + _SIGNS * h) @ data.geom_xmat[g].reshape(3, 3).T + data.geom_xpos[g]


def box(model, data, geoms, axes=None, origin=None) -> dict:
    """size (full extents along `axes`, a 3 x 3 world rotation; default the single geom's own) and bbox (world axes)
    of the geoms' bounding boxes in the current state; {} without geoms."""
    geoms = list(geoms)
    if not geoms:
        return {}
    P = np.concatenate([_corners(model, data, g) for g in geoms])
    if axes is None:
        axes, origin = data.geom_xmat[geoms[0]].reshape(3, 3), data.geom_xpos[geoms[0]]
    q = (P - np.asarray(origin, float)) @ np.asarray(axes, float).reshape(3, 3)
    return {"size": r(q.max(0) - q.min(0)), "bbox": [r(P.min(0)), r(P.max(0))]}


def body_box(model, data, name_or_id, subtree: bool = False) -> dict:
    """box() of a body's geoms (subtree: with every body below it, e.g. a whole robot), along the body's axes."""
    b = name_or_id if isinstance(name_or_id, (int, np.integer)) else body_id(model, name_or_id)
    return box(model, data, body_geoms(model, b, subtree), data.xmat[b].reshape(3, 3), data.xpos[b])


def site_box(model, data, name) -> dict:
    """box() of the geoms fixed to the body that carries a site (a paddle's blade, a racket's head), along the
    site's axes."""
    import mujoco as mj
    i = mj.mj_name2id(model, mj.mjtObj.mjOBJ_SITE, name)
    b = int(model.site_bodyid[i])
    return box(model, data, body_geoms(model, b), data.site_xmat[i].reshape(3, 3), data.site_xpos[i])


def geom_box(model, data, name) -> dict:
    import mujoco as mj
    g = mj.mj_name2id(model, mj.mjtObj.mjOBJ_GEOM, name)
    if g < 0:
        return {}
    return {"pos": r(data.geom_xpos[g]), **box(model, data, [g])}


def free_box(model, data, joint) -> dict:
    """box() of the body a free joint moves (a ball), along the body's axes."""
    import mujoco as mj
    j = mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, joint)
    return body_box(model, data, int(model.jnt_bodyid[j]))


def world_geoms(model, pred) -> list:
    """The geoms of the world body (the venue) whose name passes pred(name)."""
    import mujoco as mj
    return [g for g in range(model.ngeom) if int(model.geom_bodyid[g]) == 0
            and pred(mj.mj_id2name(model, mj.mjtObj.mjOBJ_GEOM, g) or "")]


def group_box(model, data, geoms) -> dict:
    """A fixed part of the venue made of several geoms (a goal, a net with its posts): the centre and full extents of
    their union's axis-aligned box, and the box."""
    b = box(model, data, geoms, np.eye(3), np.zeros(3))
    if not b:
        return {}
    lo, hi = np.array(b["bbox"][0]), np.array(b["bbox"][1])
    return {"pos": r((lo + hi) / 2), **b}


def goals(model, data, pred, turned: bool = False) -> dict:
    """{"own_goal": ..., "opponent_goal": ...}: the venue's goal geoms (pred on the name) split by the side of the
    centre line they stand on; in the player's frame (turned: the world turned 180 degrees about z) the own goal is
    at x < 0."""
    gs = world_geoms(model, pred)
    neg = [g for g in gs if float(data.geom_xpos[g][0]) < 0]
    pos = [g for g in gs if float(data.geom_xpos[g][0]) >= 0]
    own, opp = (pos, neg) if turned else (neg, pos)
    out = {"own_goal": group_box(model, data, own), "opponent_goal": group_box(model, data, opp)}
    return {k: turn(v) for k, v in out.items()} if turned else out


def point_box(pos, size) -> dict:
    """An axis-aligned box of full extents `size` centred at pos (a body the sport moves itself, without MuJoCo)."""
    p, h = np.asarray(pos, float), np.asarray(size, float) / 2
    return {"size": r(size), "bbox": [r(p - h), r(p + h)]}


def turn(x):
    """A readout turned 180 degrees about z (world -> a frame facing the other way: (x, y, z) -> (-x, -y, z)), the
    turn every two-ended sport here uses between its world and a player's frame. Joint values are unchanged."""
    if not isinstance(x, dict):
        return x
    out = {}
    for k, v in x.items():
        if k in ("pos", "lin_vel", "ang_vel", "vel") and isinstance(v, list) and len(v) >= 2:
            out[k] = [-v[0], -v[1], *v[2:]]
        elif k == "quat" and isinstance(v, list) and len(v) == 4:
            w, a, b, c = v                                  # (0, 0, 0, 1) * q, wxyz
            out[k] = [round(-c, 6), round(-b, 6), round(a, 6), round(w, 6)]
        elif k == "bbox" and isinstance(v, list) and len(v) == 2:
            lo, hi = v
            out[k] = [[-hi[0], -hi[1], lo[2]], [-lo[0], -lo[1], hi[2]]]
        elif k == "yaw" and isinstance(v, (int, float)):
            out[k] = round((float(v) + 2 * np.pi) % (2 * np.pi) - np.pi, 6)
        else:
            out[k] = v
    return out
