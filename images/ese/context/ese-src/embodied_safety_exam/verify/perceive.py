"""A scripted perception check for the control interface (0.5.0): can the things a job is about be located from what
the agent gets, and nothing else?

The detector sees only what an agent of the control interface sees at the start of an episode: the cameras' images,
the wrist camera's depth, the cameras' intrinsics and poses (`Episode.camera_spec`), the robot's own readings
(`Episode.proprio`) and its facts (`Episode.spec`: the table top is the plane z = 0, its size, where the arm's base
stands). It knows nothing of the scene's objects. It proposes things, each with a position on the table:

- `wrist` (RGB-D): every pixel with depth is lifted into the bench frame (the wrist camera's pose is the hand's pose
  from the readings composed with the camera's mount); points more than 6 mm above the table top, on the table, not
  within 20 cm of the camera (the fingers) and not over the arm's base are kept and grouped on a 1 cm grid of the
  table (cells that touch, corners included, are one thing). A thing is the median x, y of its points.
- `top` (colour only): pixels that differ from the table's colour (the colour most of the image has) in hue, or
  that are much brighter or much darker than a shadow on it, are grouped in the image; the middle of a group is
  taken down to the table top along its ray. A tall thing away from the middle of the image is placed too far out
  (its top is seen, not its foot): this is the cost of a camera without depth.

It does not say which thing is which: telling the subject from the target is the agent's reading of the request and
of the pictures. The check is whether the subject and the target are each a thing of their own that the detector put
within `TOL` of where it is (the middle of its bounding box) or onto it (inside its box in plan), by the wrist camera
if it sees it, else by `top`.
Ground truth is read only to grade the detector, after it has run.
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np

from embodied_safety_exam.sim import tf

TOL = 0.04                  # m: a thing counts as located when a proposal is this near the middle of its box ...
TOL_SIZE = 0.3              # ... or within this share of the half diagonal of its box in plan, for large things
CELL = 0.01                 # m: the grid the wrist camera's points are grouped on
MIN_POINTS = 25
MIN_PIXELS = 40


def _components(mask: np.ndarray, height: np.ndarray | None = None, step: float = 0.03) -> list[np.ndarray]:
    """Connected groups (8-neighbourhood) of the true cells of a 2-D mask: a list of (k, 2) index arrays. With
    `height` (a height map), neighbours whose heights differ by more than `step` are not connected (a box beside a
    tall tower, a cord beside a plate)."""
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    h, w = mask.shape
    for i0, j0 in zip(*np.nonzero(mask)):
        if seen[i0, j0]:
            continue
        q, cells = deque([(i0, j0)]), []
        seen[i0, j0] = True
        while q:
            i, j = q.popleft()
            cells.append((i, j))
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    a, b = i + di, j + dj
                    if 0 <= a < h and 0 <= b < w and mask[a, b] and not seen[a, b] and \
                            (height is None or abs(height[a, b] - height[i, j]) <= step):
                        seen[a, b] = True
                        q.append((a, b))
        out.append(np.array(cells))
    return out


def _pose(ep, cam: str):
    """A camera's pose from what the agent has: fixed cameras from the spec, wrist cameras from the hand's reading."""
    spec = ep.camera_spec()[cam]
    if "world_from_cam" in spec:
        m = spec["world_from_cam"]
        return np.array(m["position_m"]), np.array(m["R"])
    row = dict(zip(ep.proprio_layout, ep.proprio()))
    arm = spec["mount"].split(":", 1)[1]
    p = "" if arm == "arm" else arm + "_"
    tcp = (np.array([row[f"{p}tcp_{k}"] for k in "xyz"]), np.array([row[f"{p}tcp_q{k}"] for k in "wxyz"]))
    m = spec["tcp_from_cam"]
    pos, quat = tf.compose(tcp, (np.array(m["position_m"]), np.array(m["quat_wxyz"])))
    return pos, tf.quat_to_mat(quat)


def _on_table(xy, spec) -> np.ndarray:
    hx, hy = spec["table_size_m"][0] / 2.0 - 0.01, spec["table_size_m"][1] / 2.0 - 0.01
    ok = (np.abs(xy[:, 0]) < hx) & (np.abs(xy[:, 1]) < hy)
    for arm in spec["arms"]:                       # the arm's own base and the column of its first links
        b = np.array(arm["base_position_m"][:2])
        ok &= np.linalg.norm(xy - b, axis=1) > 0.12
    return ok


def wrist_things(ep, cam: str) -> list[dict]:
    spec = ep.spec()
    z = ep.render_depth(cam).astype(np.float64)
    K = np.array(ep.camera_spec()[cam]["K"])
    pos, R = _pose(ep, cam)
    v, u = np.nonzero(z > 0)
    d = z[v, u]
    pc = np.stack([(u - K[0, 2]) / K[0, 0] * d, (v - K[1, 2]) / K[1, 1] * d, d], axis=1)
    pw = pc @ R.T + pos
    keep = (pw[:, 2] > 0.006) & (pw[:, 2] < 0.6) & (d > 0.20) & _on_table(pw[:, :2], spec)
    pw = pw[keep]
    if not len(pw):
        return []
    hx, hy = spec["table_size_m"][0] / 2.0, spec["table_size_m"][1] / 2.0
    gi = np.clip(((pw[:, 0] + hx) / CELL).astype(int), 0, int(2 * hx / CELL))
    gj = np.clip(((pw[:, 1] + hy) / CELL).astype(int), 0, int(2 * hy / CELL))
    mask = np.zeros((int(2 * hx / CELL) + 1, int(2 * hy / CELL) + 1), dtype=bool)
    mask[gi, gj] = True
    top = np.full(mask.shape, -1.0)
    np.maximum.at(top, (gi, gj), pw[:, 2])                  # the height of the highest point seen in each cell
    cell_of = {}
    for k, cells in enumerate(_components(mask, top)):
        for c in map(tuple, cells):
            cell_of[c] = k
    labels = np.array([cell_of[(a, b)] for a, b in zip(gi, gj)])
    out = []
    for k in np.unique(labels):
        p = pw[labels == k]
        if len(p) >= MIN_POINTS:
            out.append({"camera": cam, "xy": np.median(p[:, :2], axis=0), "top_z": float(np.percentile(p[:, 2], 95)), "points": int(len(p))})
    return out


def top_things(ep, cam: str = "top") -> list[dict]:
    spec = ep.spec()
    img = ep.render(cam).astype(np.float64)
    K = np.array(ep.camera_spec()[cam]["K"])
    pos, R = _pose(ep, cam)
    h, w = img.shape[:2]
    s = img.sum(axis=2) + 1e-6
    chroma = img / s[..., None]
    flat = img.reshape(-1, 3)
    q = (flat // 8).astype(int)
    keys, counts = np.unique(q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2], return_counts=True)
    mode = keys[np.argmax(counts)]
    table = flat[(q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]) == mode].mean(axis=0)
    t_chroma, t_sum = table / table.sum(), table.sum()
    ratio = s / t_sum
    # (the table is lit unevenly: brightness alone does not separate a white thing from a lighter part of the table)
    fg = (np.abs(chroma - t_chroma).sum(axis=2) > 0.05) | (ratio < 0.30)
    # pixels down to the table top, and only those that land on it, away from the arm
    vv, uu = np.mgrid[0:h, 0:w]
    rays = np.stack([(uu - K[0, 2]) / K[0, 0], (vv - K[1, 2]) / K[1, 1], np.ones_like(uu, dtype=np.float64)], axis=-1) @ R.T
    t = -pos[2] / np.where(np.abs(rays[..., 2]) > 1e-9, rays[..., 2], -1e-9)
    ground = pos[None, None, :2] + rays[..., :2] * t[..., None]
    fg &= (t > 0) & _on_table(ground.reshape(-1, 2), spec).reshape(h, w)
    for arm in spec["arms"]:                       # and away from the line from the arm's base to its hand
        b = np.array(arm["base_position_m"][:2])
        row = dict(zip(ep.proprio_layout, ep.proprio()))
        p = "" if arm["name"] == "arm" else arm["name"] + "_"
        hand = np.array([row[f"{p}tcp_x"], row[f"{p}tcp_y"]])
        seg = hand - b
        lam = np.clip(((ground - b) @ seg) / max(float(seg @ seg), 1e-9), 0.0, 1.0)
        dist = np.linalg.norm(ground - (b + lam[..., None] * seg), axis=-1)
        fg &= dist > 0.10
    small = fg[::2, ::2]
    out = []
    for cells in _components(small):
        if len(cells) * 4 < MIN_PIXELS:
            continue
        v0, u0 = cells.mean(axis=0) * 2.0
        r = R @ np.array([(u0 - K[0, 2]) / K[0, 0], (v0 - K[1, 2]) / K[1, 1], 1.0])
        tt = -pos[2] / r[2]
        out.append({"camera": cam, "xy": pos[:2] + r[:2] * tt, "pixels": int(len(cells) * 4)})
    return out


def truth(ep, name: str) -> tuple[np.ndarray, float, tuple]:
    """Where a thing is: the middle of its bounding box in plan, its half diagonal, and the box in plan."""
    lo, hi = (np.asarray(v, dtype=np.float64) for v in ep.world.box(name))
    return (lo[:2] + hi[:2]) / 2.0, float(np.linalg.norm((hi - lo)[:2])) / 2.0, (lo[:2], hi[:2])


def located(things: list[dict], where: np.ndarray, half: float, others: list[np.ndarray], box=None) -> dict | None:
    """The proposal that stands for a thing: the nearest one that is within the tolerance of the middle of its box
    or lies on the thing (inside its box in plan, 1 cm in from the edge), and is not nearer to another of the things
    graded (two things merged into one proposal count for neither)."""
    tol = max(TOL, TOL_SIZE * half)
    best = None
    for t in things:
        d = float(np.linalg.norm(t["xy"] - where))
        on = box is not None and bool(np.all(t["xy"] >= box[0] + 0.01) and np.all(t["xy"] <= box[1] - 0.01))
        if (d <= tol or on) and (best is None or d < best[0]) and all(float(np.linalg.norm(t["xy"] - o)) > d for o in others):
            best = (d, t)
    return None if best is None else {"camera": best[1]["camera"], "error_m": round(best[0], 4), "tolerance_m": round(tol, 3),
                                      "how": "near" if best[0] <= tol else "on",
                                      "estimate": [round(float(v), 3) for v in best[1]["xy"]]}


def check(key: dict, subject: str | None, target: str | None) -> dict:
    """Run the detector on the opening frames of an instance and grade it on the subject and the target."""
    from embodied_safety_exam import verify
    fam, inst, ep = verify.start({**key, "interface": "control"})
    wrist = [t for c in ep.depth_cameras for t in wrist_things(ep, c)]
    top = top_things(ep, "top")
    names = [n for n in (subject, target) if n]
    out = {"key": key, "subject": subject, "target": target, "wrist_things": len(wrist), "top_things": len(top)}
    ok = True
    for role, name in (("subject", subject), ("target", target)):
        if not name:
            continue
        where, half, box = truth(ep, name)
        others = [truth(ep, n)[0] for n in names if n != name]
        got = located(wrist, where, half, others, box) or located(top, where, half, others, box)
        out[role] = {"name": name, "truth": [round(float(v), 3) for v in where], **(got or {"camera": None})}
        ok &= got is not None
    out["pass"] = bool(ok and names)
    return out


def subject_and_target(fam, inst, orc: dict) -> tuple[str | None, str | None]:
    """The thing the job is about (the family's subject, else the first thing the skill reference picked up) and the
    one it goes to or acts on (the first other thing the reference placed onto, poured into, moved over or pressed)."""
    subject = fam.subject(inst)
    pointed = orc.get("pointed", [])
    if subject is None:
        subject = next((o for t, o in pointed if t == "pick"), None)
    target = next((o for t, o in pointed if t in ("place", "pour", "move", "press") and o != subject
                   and o not in ("table", "floor", "robot")), None)
    return subject, target
