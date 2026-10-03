"""Scripted 8-ball player from public information only: the top camera image, its documented pose and intrinsics, and
the table geometry and rules from the prompt / `game spec`. No simulator, no hidden state.

perceive(): ball centres from the overhead image (a distance transform of the non-cloth pixels finds each ball's disc;
the centre is refined by the centroid of its pixels and back-projected to the plane z = R) and each ball's kind from
its colours: the cue ball is white all over, the 8 black, a stripe has white caps above and below its coloured band
(white in the ring around the number disc), a solid is coloured there. The number follows from the kind and the
colour (the standard set: 1 / 9 yellow, 2 / 10 blue, 3 / 11 red, 4 / 12 purple, 5 / 13 orange, 6 / 14 green,
7 / 15 maroon), matched to the numbers the service lists as on the table.
decide(): break from just above the head string at the front ball; with ball in hand, a cue position for a straight
pot (above the head string after a scratch on the break, where only balls on or below the head string may be hit first
directly: WPA 6.11); then the
easiest direct pot of a ball it may hit (ghost-ball geometry, no blocked path, no cue-ball path into a pocket), called
as BALL:POCKET; with no pot, a firm full hit on the nearest such ball (a cushion is then reached), called safety.
"""
import io
import math

import numpy as np
from PIL import Image
from scipy import ndimage

W, L, R = 0.9906, 1.9812, 0.028575
HEAD_SPOT = (W / 2, L / 4)
HEAD_STRING_Y = L / 4             # "above the head string" is y < L/4, the line itself excluded
KITCHEN_SPOT = (W / 2, HEAD_STRING_Y - 0.05)
CLOTH = np.array([38, 110, 150], dtype=float)
CUSHION = np.array([28, 88, 122], dtype=float)
PALETTE = {"1": (250, 200, 20), "2": (30, 70, 210), "3": (215, 30, 30), "4": (110, 40, 160), "5": (255, 120, 20),
           "6": (20, 140, 40), "7": (120, 20, 30)}       # solid n and stripe n + 8 share a colour
POCKET_XY = {"lb": (0.0, 0.0), "rb": (W, 0.0), "lt": (0.0, L), "rt": (W, L), "lc": (0.0, L / 2), "rc": (W, L / 2)}
POCKET_R = {k: 0.07 for k in POCKET_XY}          # replaced by the pockets of `game spec` (set_table)
POCKET_C = {k: np.array(v) for k, v in POCKET_XY.items()}
POCKET_AIM = {}
for _k, (_x, _y) in POCKET_XY.items():
    if _k in ("lc", "rc"):
        POCKET_AIM[_k] = np.array([_x + (-0.012 if _k == "lc" else 0.012), _y])
    else:
        _d = np.array([1.0 if _x == 0 else -1.0, 1.0 if _y == 0 else -1.0]) / math.sqrt(2)
        POCKET_AIM[_k] = np.array([_x, _y]) + 0.02 * _d


def set_table(spec_table: dict) -> None:
    for k, p in spec_table["pockets"].items():
        POCKET_R[k] = float(p["radius"]); POCKET_C[k] = np.array(p["centre_xy"], dtype=float)


def placement_error(balls: dict, xy, kitchen: bool):
    x, y = float(xy[0]), float(xy[1])
    if not (R <= x <= W - R and R <= y <= L - R):
        return "off the table"
    if kitchen and y >= HEAD_STRING_Y:
        return "not above the head string"
    if any(math.hypot(x - q[0], y - q[1]) < 2 * R + 2e-3 for q in balls.values()):
        return "overlaps a ball"
    if any(math.hypot(x - c[0], y - c[1]) < POCKET_R[k] + R + 1e-3 for k, c in POCKET_C.items()):
        return "in a pocket opening"
    return None


def free_spot(balls: dict, x: float, y: float, step: float = 0.03):
    for k in range(80):
        for sgn in ((1,) if k == 0 else (-1, 1)):
            p = (x if k == 0 else W / 2, y + sgn * k * step)
            if placement_error(balls, p, False) is None:
                return p
    return (W / 2, 0.1)


def kitchen_spot(balls: dict):
    """A free cue position above the head string."""
    for dy in (0.0, -0.06, -0.12, -0.2):
        for k in range(30):
            for sgn in ((1,) if k == 0 else (-1, 1)):
                p = (KITCHEN_SPOT[0] + sgn * k * 0.03, KITCHEN_SPOT[1] + dy)
                if placement_error(balls, p, True) is None:
                    return p
    return (W / 2, 0.1)


class TopCamera:
    def __init__(self, info: dict):
        self.pos = np.array(info["position_world"], dtype=float)
        self.Rwc = np.array(info["R_world_to_camera"], dtype=float)
        self.fx, self.fy, self.cx, self.cy = info["fx"], info["fy"], info["cx"], info["cy"]

    def project(self, p):
        c = self.Rwc @ (np.asarray(p, dtype=float) - self.pos)
        return np.array([self.fx * c[0] / c[2] + self.cx, self.fy * c[1] / c[2] + self.cy]), c[2]

    def ray_to_plane(self, u, v, z):
        d = self.Rwc.T @ np.array([(u - self.cx) / self.fx, (v - self.cy) / self.fy, 1.0])
        t = (z - self.pos[2]) / d[2]
        return (self.pos + t * d)[:2]


def perceive(png: bytes, cam_info: dict, on_table=None):
    """{'cue': (x, y) or None, 'balls': {number: (x, y)}, 'kind': {number: 'solid'|'stripe'|'eight'}}.
    on_table: the numbers the service reports as on the table (used to match colours to numbers)."""
    cam = TopCamera(cam_info)
    img = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=float)
    H, Wd = img.shape[:2]
    _, depth = cam.project([W / 2, L / 2, R])
    r_px = cam.fx * R / math.sqrt(depth * depth - R * R)
    vv, uu = np.mgrid[0:H, 0:Wd]
    c0, c1 = cam.project([0, 0, 0.0])[0], cam.project([W, L, 0.0])[0]
    umin, umax = sorted([c0[0], c1[0]]); vmin, vmax = sorted([c0[1], c1[1]])
    m = r_px                                     # a ball in the jaws overlaps the cushion nose line
    surf = (uu >= umin - m) & (uu <= umax + m) & (vv >= vmin - m) & (vv <= vmax + m)
    hole = np.zeros_like(surf)
    for k, c in POCKET_C.items():
        (pu, pv), _ = cam.project([c[0], c[1], 0.0])
        rp = cam.fx * POCKET_R[k] / depth
        hole |= (uu - pu) ** 2 + (vv - pv) ** 2 < rp * rp
    diff = np.abs(img - CLOTH).max(axis=2)
    diff_c = np.abs(img - CUSHION).max(axis=2)
    mask = surf & (diff > 45) & (diff_c > 30) & ~(hole & (img.max(axis=2) < 40))   # cloth, cushions, pockets
    mask = ndimage.binary_fill_holes(mask)       # black numbers inside a ball near a pocket
    dt = ndimage.distance_transform_edt(mask)
    peaks = (dt >= 0.7 * r_px) & (dt == ndimage.maximum_filter(dt, size=int(r_px)))
    lab, n = ndimage.label(peaks)
    cands = ndimage.center_of_mass(peaks, lab, range(1, n + 1)) if n else []
    cands = sorted(((dt[int(round(a)), int(round(b))], a, b) for a, b in cands), reverse=True)
    centres = []
    for _, a, b in cands:                        # non-maximum suppression: one per ball
        if all((a - c[0]) ** 2 + (b - c[1]) ** 2 > (1.3 * r_px) ** 2 for c in centres):
            centres.append([a, b])
    for _ in range(3):                           # refine: centroid of the pixels nearer to this centre than to others
        new = []
        for i, (a, b) in enumerate(centres):
            v0, v1, u0, u1 = int(a - r_px - 2), int(a + r_px + 3), int(b - r_px - 2), int(b + r_px + 3)
            gv, gu = np.mgrid[max(v0, 0):min(v1, H), max(u0, 0):min(u1, Wd)]
            sel = mask[gv, gu] & ((gv - a) ** 2 + (gu - b) ** 2 <= r_px ** 2)
            for j, (c, d) in enumerate(centres):
                if j != i:
                    sel &= (gv - a) ** 2 + (gu - b) ** 2 < (gv - c) ** 2 + (gu - d) ** 2
            new.append([float(gv[sel].mean()), float(gu[sel].mean())] if sel.sum() > 20 else [a, b])
        centres = new
    found = []
    for a, b in centres:
        gv, gu = np.mgrid[int(a - r_px):int(a + r_px) + 1, int(b - r_px):int(b + r_px) + 1]
        rr = np.hypot(gv - a, gu - b)
        sel = (rr > 0.55 * r_px) & (rr < 0.88 * r_px)
        ring = img[gv[sel], gu[sel]]
        white = (ring.min(axis=1) > 205) & (ring.max(axis=1) - ring.min(axis=1) < 40)
        dark = ring.max(axis=1) < 60
        disc = img[gv[rr < 0.88 * r_px], gu[rr < 0.88 * r_px]]
        coloured = (disc.max(axis=1) - disc.min(axis=1)) > 70
        col = np.median(ring[(ring.max(axis=1) - ring.min(axis=1)) > 60], axis=0) if (
            ((ring.max(axis=1) - ring.min(axis=1)) > 60).sum() > 5) else np.median(ring, axis=0)
        if white.mean() > 0.85 and coloured.mean() < 0.04:
            kind = "cue"
        elif dark.mean() > 0.5:
            kind = "eight"
        elif white.mean() > 0.25:
            kind = "stripe"
        else:
            kind = "solid"
        xy = cam.ray_to_plane(b + 0.5, a + 0.5, R)
        found.append((kind, (float(xy[0]), float(xy[1])), float(white.mean()), col))
    cues = [f for f in found if f[0] == "cue"]
    cue = max(cues, key=lambda f: f[2])[1] if cues else None
    allowed = set(on_table) if on_table else {str(i) for i in range(1, 16)}
    cands = []                                   # (colour distance, index, number)
    obj = [f for f in found if not (f[0] == "cue" and f[1] == cue)]
    for i, (k, xy, _, col) in enumerate(obj):
        k = "stripe" if k == "cue" else k        # a second all-white ball can only be a stripe seen from its cap
        if k == "eight":
            cands.append((0.0, i, "8"))
            continue
        for n, rgb in PALETTE.items():
            num = n if k == "solid" else str(int(n) + 8)
            cands.append((float(np.linalg.norm(np.asarray(col, float) - np.asarray(rgb, float))) + (0 if num in allowed else 1e4),
                          i, num))
    balls, kind, used, done = {}, {}, set(), set()
    for d, i, num in sorted(cands):              # greedy matching of seen balls to numbers, closest colours first
        if i in done or num in used:
            continue
        done.add(i); used.add(num)
        balls[num] = obj[i][1]
        kind[num] = "eight" if num == "8" else ("solid" if int(num) < 8 else "stripe")
    return {"cue": cue, "balls": balls, "kind": kind}


def _seg_dist(p, a, b) -> float:
    ab = b - a
    t = float(np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-12), 0.0, 1.0))
    return float(np.linalg.norm(p - (a + t * ab)))


def scratch_risk(ghost, d, u) -> bool:
    """Does the cue ball, after contact, head for a pocket (tangent line and the bend towards rolling)?"""
    t = d - np.dot(d, u) * u
    dirs = [d] if np.linalg.norm(t) < 0.03 else [t / np.linalg.norm(t), (t / np.linalg.norm(t) + 0.5 * d)]
    for e in dirs:
        e = e / np.linalg.norm(e)
        for c in POCKET_AIM.values():
            w = c - ghost
            along = float(np.dot(w, e))
            if 0.0 < along < 1.3 and abs(float(e[0] * w[1] - e[1] * w[0])) < 0.07:
                return True
    return False


def pot_options(cue, balls: dict, targets, margin: float = 0.006, avoid_scratch: bool = True) -> list:
    """Direct ghost-ball pots of any target ball, easiest first; blocked paths removed."""
    cue = np.asarray(cue, dtype=float)
    obs = {k: np.asarray(v, dtype=float) for k, v in balls.items()}
    opts = []
    for bid in targets:
        if bid not in obs:
            continue
        ob = obs[bid]
        for pk, tgt in POCKET_AIM.items():
            d2v = tgt - ob; d2 = float(np.linalg.norm(d2v)); u = d2v / d2
            ghost = ob - 2 * R * u
            d1v = ghost - cue; d1 = float(np.linalg.norm(d1v))
            if d1 < 1e-6:
                continue
            cosc = float(np.dot(d1v / d1, u))
            if cosc < math.cos(math.radians(70)):
                continue
            if pk in ("lc", "rc") and (abs(u[0]) < math.cos(math.radians(45)) or (u[0] > 0) != (pk == "rc")):
                continue
            if not (R < ghost[0] < W - R and R < ghost[1] < L - R):
                continue
            if any(_seg_dist(q, cue, ghost) < 2 * R + margin or _seg_dist(q, ob, tgt) < 2 * R + margin
                   for oid, q in obs.items() if oid != bid):
                continue
            diff = (d1 + 1.6 * d2) / max(cosc, 0.2) ** 1.5
            if avoid_scratch and scratch_risk(ghost, d1v / d1, u):
                diff += 10.0
            V = float(np.clip(0.9 + 0.55 * d1 + 0.9 * d2 / max(cosc, 0.35), 1.0, 4.5))
            opts.append({"ball": bid, "pocket": pk, "phi": math.degrees(math.atan2(d1v[1], d1v[0])) % 360.0, "V": V,
                         "cut_deg": math.degrees(math.acos(min(1.0, cosc))), "difficulty": diff})
    opts.sort(key=lambda o: o["difficulty"])
    return opts


def place_for_pot(balls: dict, targets, kitchen: bool = False):
    """Ball in hand: a cue position for a straight pot of a target ball, (xy, option) or None."""
    best = None
    for bid in targets:
        ob = np.asarray(balls[bid], dtype=float)
        for pk, tgt in POCKET_AIM.items():
            u = (tgt - ob) / np.linalg.norm(tgt - ob)
            for back in (0.25, 0.4, 0.15, 0.6):
                xy = ob - (2 * R + back) * u
                if placement_error(balls, xy, kitchen):
                    continue
                opts = [o for o in pot_options(xy, balls, [bid]) if o["pocket"] == pk]
                if opts and (best is None or opts[0]["difficulty"] < best[1]["difficulty"]):
                    best = ((float(xy[0]), float(xy[1])), opts[0])
                break
    return best


def safety(cue, balls: dict, targets) -> dict:
    """No pot: a firm, full hit on the nearest target ball with a clear path (so that a cushion is reached)."""
    cue = np.asarray(cue, dtype=float)
    obs = {k: np.asarray(v, dtype=float) for k, v in balls.items()}
    order = sorted((t for t in targets if t in obs), key=lambda t: float(np.linalg.norm(obs[t] - cue)))
    pick = next((t for t in order if all(_seg_dist(q, cue, obs[t]) >= 2 * R + 0.002
                                         for oid, q in obs.items() if oid != t)), order[0] if order else None)
    if pick is None:
        return {"phi": 90.0, "V": 2.0, "plan": "no target seen"}
    d = obs[pick] - cue
    return {"phi": math.degrees(math.atan2(d[1], d[0])) % 360.0, "V": 2.2, "plan": f"safety on {pick}"}


def targets_for(table: dict, group: str) -> list:
    """The balls I may hit first: group = 'open', 'solids', 'stripes' or '... (on the 8)'."""
    kind = table["kind"]
    if "on the 8" in group:
        return [b for b, k in kind.items() if k == "eight"]
    if group.startswith("solids"):
        return [b for b, k in kind.items() if k == "solid"]
    if group.startswith("stripes"):
        return [b for b, k in kind.items() if k == "stripe"]
    return [b for b, k in kind.items() if k in ("solid", "stripe")]


def decide(table: dict, state: dict) -> dict:
    """The next shot (the HTTP body of `act`) plus a `plan` text."""
    balls = table["balls"]
    targets = targets_for(table, state.get("your_group", "open"))
    dec = {"type": "shoot", "spin_x": 0.0, "spin_y": 0.0}
    cue = table["cue"]
    if state.get("break_shot"):
        apex = min(balls.values(), key=lambda p: p[1]) if balls else (W / 2, 3 * L / 4)
        cue = KITCHEN_SPOT if placement_error(balls, KITCHEN_SPOT, True) is None else kitchen_spot(balls)
        d = np.asarray(apex) - np.asarray(cue)
        dec.update(cue_x=float(cue[0]), cue_y=float(cue[1]), aim_deg=math.degrees(math.atan2(d[1], d[0])) % 360.0,
                   speed=6.0)
        return dict(dec, plan="break")
    bih = state.get("ball_in_hand")
    kitchen = "head string" in str(bih or "")
    if kitchen:          # WPA 6.11: from above the head string only balls on or below it may be hit first directly
        reachable = [t for t in targets if balls[t][1] >= HEAD_STRING_Y]
        if not reachable:                    # all my balls are above the head string: down the table and back
            cue = kitchen_spot(balls)
            dec.update(cue_x=float(cue[0]), cue_y=float(cue[1]), aim_deg=90.0, speed=2.6, call="safety")
            return dict(dec, plan="cross the head string first, then come back")
        targets = reachable
    if bih:
        pl = place_for_pot(balls, targets, kitchen=kitchen)
        if pl is not None:
            cue = pl[0]
        elif cue is None or placement_error(balls, cue, kitchen):
            cue = kitchen_spot(balls) if kitchen else free_spot(balls, *HEAD_SPOT)
        dec.update(cue_x=float(cue[0]), cue_y=float(cue[1]))
    if cue is None:
        cue = free_spot(balls, *HEAD_SPOT)
    opts = pot_options(cue, balls, targets)
    if opts:
        o = opts[0]
        dec.update(aim_deg=o["phi"], speed=o["V"], spin_y=-0.2 if o["cut_deg"] < 12 else 0.0,
                   call=f"{o['ball']}:{o['pocket']}")
        return dict(dec, plan=f"pot {o['ball']} in {o['pocket']}")
    sf = safety(cue, balls, targets)
    dec.update(aim_deg=sf["phi"], speed=sf["V"], call="safety")
    return dict(dec, plan=sf["plan"])
