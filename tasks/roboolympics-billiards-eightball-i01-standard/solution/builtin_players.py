"""billiards' built-in players (the same action interface as a model's program; core/client.py plays them over HTTP).

  Reference  the camera-only planning player (billiards-3; the task's oracle, solution/): the top camera image (the
             `top` tile of the observation PNG), its documented pose and intrinsics (the observation's `cameras`), the
             table geometry of /spec and the rules. No simulator, no hidden state. decide_plan(): an analytic model of
             the table predicts each candidate stroke (pot strokes with stun, follow and draw at three speeds, the aim
             corrected for throw; safeties at several cuts and speeds), and it plays the pot with the best chance and
             leave, a safety that leaves the opponent the hardest best pot, a run-out placement with ball in hand, and
             defends when the opponent is on the 8.
  Greedy     the simple greedy player (billiards-2's reference, Season 1's eight_player.py): decide(): the easiest
             direct pot, else a firm hit on the nearest ball called safety. A simple baseline of step 4.
  NoSafety, BlindOpp  the reference with one capability weakened (step 4, capability sensitivity): never plays safe;
             blind to the opponent's balls once the groups are set.
  Random     random valid shots (the generic tests: no draw, whitelist, determinism, mirror symmetry; a baseline).
  Fixed      the same stroke every time (a baseline).
  TRUTH_PLAYERS  screening only (sports/billiards/screen/hooks.py, refcheck.reference_match): the reference, the greedy player
             and the capability-sensitivity variants on the true positions (view["truth"], which only the screening
             tools put there; a task's service never does), for the large samples of step 4.
  (refcheck.reference_match: tools/check stage 5's [reference] hook, in its own module: the reference imports no
             framework.)

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
import base64
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


def perceive(png, cam_info: dict, on_table=None):
    """{'cue': (x, y) or None, 'balls': {number: (x, y)}, 'kind': {number: 'solid'|'stripe'|'eight'}}.
    on_table: the numbers the service reports as on the table (used to match colours to numbers)."""
    cam = TopCamera(cam_info)
    im = png if isinstance(png, Image.Image) else Image.open(io.BytesIO(png))       # PNG bytes or an image
    img = np.asarray(im.convert("RGB"), dtype=float)
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
                         "cut_deg": math.degrees(math.acos(min(1.0, cosc))), "difficulty": diff, "d1": d1, "d2": d2})
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


# ----------------------------------------------------------------------------- the planning reference player
# An analytic model of the table (the physics_model of /spec: sliding friction 0.2, rolling resistance 0.01, ball-ball
# restitution 0.95, cushion restitution 0.85) predicts where a stroke leaves the balls: the cue strike (speed and spin
# from the tip offset), sliding until the ball rolls, rolling to rest, frictionless ball-ball contacts (the cue ball
# keeps its spin: follow and draw bend its path after contact; throw), cushion rebounds and the pockets; struck balls
# move on and may strike others. Good to a few centimetres for soft strokes, decimetres for firm ones (checked against
# the engine); enough to choose between strokes.
MU_S, MU_R, E_BB, G = 0.2, 0.01, 0.95, 9.81
# The rebound off a cushion: a fit to test shots on this table (a ball sent at a long rail at 0-75 degrees from the
# normal, 0.3-4 m/s, rolling, stunned, with draw or follow): the outgoing velocity and spin, in the rail's frame
# (n: normal, t: along the rail) and divided by the incoming speed s, as a quadratic in the incoming ones / s and s.
CUSHION_FIT = [[-0.01518, 0.75147, -0.0357, 0.04281, -0.0361, 0.01353, 0.13545, -0.03193, 0.02595, -0.03745, 0.02595, -0.02628, -0.02871, 0.02705, 0.01204, -0.00057, 0.00126], [-0.14074, 0.33339, -1.33103, 0.39697, -0.33475, 0.12545, 1.25595, -0.29602, 0.24059, -0.34725, 0.24059, -0.24365, -0.26619, 0.25079, 0.11164, -0.00533, 0.01166], [-1.51467, 2.46681, -2.53006, 3.00779, -2.09747, -0.95342, 2.52475, -2.25746, 0.91212, 0.00794, 0.91212, 0.14598, -0.56124, 2.2176, -0.05609, 0.00076, -0.00124], [-1.02097, 1.66276, -1.7054, 1.35336, -0.4138, -0.64266, 1.70181, -1.52165, 0.61481, 0.00535, 0.61481, 0.0984, -0.37831, 1.49478, -0.03781, 0.00051, -0.00084]]
MOUTH_CORNER, MOUTH_SIDE = 0.091, 0.0755   # where the cushion noses end at the pockets (metres, see _in_mouth)
SIGMA_DEG = 0.12                   # the aim error the planner assumes: execution scatter and perception
STROKES = ((1.0, 0.0), (0.7, 0.0), (1.4, 0.0), (1.0, -0.35), (1.0, 0.35), (1.4, -0.35), (0.7, 0.35))
PLAN = {"pots": 3, "places": 4, "safety_balls": 3, "safety_cuts": (-0.9, -0.6, -0.3, 0.0, 0.3, 0.6, 0.9),
        "safety_speeds": (0.6, 1.0, 1.6), "safety_robust": 6, "gamma": 0.7, "pot_min": 0.55, "pot_min_defend": 0.8}
PERTURB = ((0.3, 0.95), (-0.3, 1.05))   # the neighbours of a stroke judge_robust looks at (degrees, speed factor)
POCKET_TOL = {"lb": 0.028, "rb": 0.028, "lt": 0.028, "rt": 0.028, "lc": 0.022, "rc": 0.022}


class _Ball:
    __slots__ = ("x", "y", "vx", "vy", "ux", "uy")

    def __init__(self, x, y, vx=0.0, vy=0.0, ux=0.0, uy=0.0):
        self.x, self.y, self.vx, self.vy, self.ux, self.uy = x, y, vx, vy, ux, uy


def _pocket_at(x, y, margin=0.0):
    for k, c in POCKET_C.items():
        if (x - c[0]) ** 2 + (y - c[1]) ** 2 < (POCKET_R[k] + margin) ** 2:
            return k
    return None


def _in_mouth(x, y) -> bool:
    """Past a cushion line inside a pocket's mouth: the long rails' noses run from MOUTH_CORNER to L/2 - MOUTH_SIDE and
    from L/2 + MOUTH_SIDE to L - MOUTH_CORNER, the short rails' from MOUTH_CORNER to W - MOUTH_CORNER (the table of
    /spec: corner openings about 11.7 cm, side openings about 13.5 cm, measured between the jaws)."""
    if x < R or x > W - R:
        if y < MOUTH_CORNER or y > L - MOUTH_CORNER or abs(y - L / 2) < MOUTH_SIDE:
            return True
    if y < R or y > L - R:
        if x < MOUTH_CORNER or x > W - MOUTH_CORNER:
            return True
    return False


def _rebound(vn, un, vt, ut):
    """CUSHION_FIT: (vn, un, vt, ut) towards the rail (vn > 0) -> (vn', un', vt', ut') with n now away from it."""
    sg = -1.0 if vt < 0 else 1.0
    vt, ut = sg * vt, sg * ut
    sp = math.hypot(vn, vt)
    if sp < 1e-9:
        return 0.0, 0.0, 0.0, 0.0
    z = (vn / sp, un / sp, vt / sp, ut / sp)
    f = [1.0, *z] + [z[i] * z[j] for i in range(4) for j in range(i, 4)] + [sp, sp * z[0]]
    o = [sp * sum(c * x for c, x in zip(row, f)) for row in CUSHION_FIT]
    return max(o[0], 0.0), o[1], sg * o[2], sg * o[3]


def _cushion(b, nx: float, ny: float) -> None:
    """Rebound of ball b off a cushion whose unit normal (nx, ny) points from the cushion towards the ball."""
    tx, ty = -ny, nx
    vn, vt = -(b.vx * nx + b.vy * ny), b.vx * tx + b.vy * ty
    un, ut = -(b.ux * nx + b.uy * ny), b.ux * tx + b.uy * ty
    vn2, un2, vt2, ut2 = _rebound(vn, un, vt, ut)
    b.vx, b.vy = vn2 * nx + vt2 * tx, vn2 * ny + vt2 * ty
    b.ux, b.uy = un2 * nx + ut2 * tx, un2 * ny + ut2 * ty


# The pocket jaws (the table of /spec, 7-ft: the cushion noses end MOUTH_CORNER / MOUTH_SIDE from the corners and
# the side pockets; from there an angled jaw face runs into each pocket, with a rounded nose where it meets the rail):
# per pocket, its two jaw faces (segment end points) and its two noses (centre, radius).
JAWS = {
    "lb": ([((0.0222, -0.0508), (0.0776, -0.0048)), ((-0.0508, 0.0222), (-0.0048, 0.0776))],
           [((0.091, -0.0209), 0.0209), ((-0.0209, 0.091), 0.0209)]),
    "lt": ([((0.0222, 2.032), (0.0776, 1.986)), ((-0.0508, 1.959), (-0.0048, 1.9036))],
           [((-0.0209, 1.8902), 0.0209), ((0.091, 2.0021), 0.0209)]),
    "rt": ([((0.9684, 2.032), (0.913, 1.986)), ((1.0414, 1.959), (0.9954, 1.9036))],
           [((0.8996, 2.0021), 0.0209), ((1.0115, 1.8902), 0.0209)]),
    "rb": ([((1.0414, 0.0222), (0.9954, 0.0776)), ((0.9684, -0.0508), (0.913, -0.0048))],
           [((1.0115, 0.091), 0.0209), ((0.8996, -0.0209), 0.0209)]),
    "lc": ([((-0.0508, 1.0528), (-0.007, 1.0582)), ((-0.0508, 0.9284), (-0.007, 0.923))],
           [((-0.008, 0.9151), 0.008), ((-0.008, 1.0661), 0.008)]),
    "rc": ([((1.0414, 1.0528), (0.9976, 1.0582)), ((1.0414, 0.9284), (0.9976, 0.923))],
           [((0.9986, 1.0661), 0.008), ((0.9986, 0.9151), 0.008)]),
}


def _jaws(b) -> int:
    """Contacts of ball b with the jaws of the pocket it is near (pushed back out and rebounded): the count."""
    n = 0
    for k, c in POCKET_C.items():
        if (b.x - c[0]) ** 2 + (b.y - c[1]) ** 2 > 0.18 ** 2:
            continue
        faces, noses = JAWS[k]
        for (ax, ay), (bx, by) in faces:
            ex, ey = bx - ax, by - ay
            t = max(0.0, min(1.0, ((b.x - ax) * ex + (b.y - ay) * ey) / (ex * ex + ey * ey)))
            px, py = ax + t * ex, ay + t * ey
            d = math.hypot(b.x - px, b.y - py)
            if 1e-9 < d < R:
                nx, ny = (b.x - px) / d, (b.y - py) / d
                if b.vx * nx + b.vy * ny < 0:
                    b.x, b.y = px + R * nx, py + R * ny
                    _cushion(b, nx, ny)
                    n += 1
        for (cx, cy), r in noses:
            d = math.hypot(b.x - cx, b.y - cy)
            if 1e-9 < d < R + r:
                nx, ny = (b.x - cx) / d, (b.y - cy) / d
                if b.vx * nx + b.vy * ny < 0:
                    b.x, b.y = cx + (R + r) * nx, cy + (R + r) * ny
                    _cushion(b, nx, ny)
                    n += 1
    return n


def _advance(b, others, step=0.008, tmax=30.0):
    """Move ball b until it stops, drops or touches one of `others` ({id: (x, y)}): (event, info, cushions)."""
    cush, t = 0, 0.0
    while t < tmax:
        sx, sy = b.vx - b.ux, b.vy - b.uy
        slip, sp = math.hypot(sx, sy), math.hypot(b.vx, b.vy)
        if slip > 1e-6:
            ax, ay = -MU_S * G * sx / slip, -MU_S * G * sy / slip
            t_end = slip / (3.5 * MU_S * G)
            dt, sliding = min(step / max(sp, 0.05), t_end), True
        else:
            if sp < 1e-4:
                return "stop", None, cush
            ax, ay = -MU_R * G * b.vx / sp, -MU_R * G * b.vy / sp
            t_end = sp / (MU_R * G)
            dt, sliding = min(step / max(sp, 0.02), t_end), False
        nx, ny = b.x + b.vx * dt + 0.5 * ax * dt * dt, b.y + b.vy * dt + 0.5 * ay * dt * dt
        hit, best = None, 2.0
        ddx, ddy = nx - b.x, ny - b.y
        a = ddx * ddx + ddy * ddy
        for oid, (ox, oy) in others.items():
            dx0, dy0 = b.x - ox, b.y - oy
            c = dx0 * dx0 + dy0 * dy0 - 4 * R * R
            if a < 1e-14 or c > a + 4 * R * math.sqrt(a) + 1e-9:
                continue
            bb = 2 * (dx0 * ddx + dy0 * ddy)
            disc = bb * bb - 4 * a * c
            if disc >= 0:
                f = (-bb - math.sqrt(disc)) / (2 * a)
                if 0.0 <= f <= 1.0 and f < best:
                    best, hit = f, oid
        if hit is not None:
            tt = best * dt
            b.x += best * ddx; b.y += best * ddy
            b.vx += ax * tt; b.vy += ay * tt
            if sliding:
                b.ux -= 2.5 * ax * tt; b.uy -= 2.5 * ay * tt
            else:
                b.ux, b.uy = b.vx, b.vy
            ox, oy = others[hit]
            d = math.hypot(ox - b.x, oy - b.y)
            return "hit", (hit, (ox - b.x) / d, (oy - b.y) / d), cush
        b.x, b.y = nx, ny
        b.vx += ax * dt; b.vy += ay * dt
        if sliding:
            b.ux -= 2.5 * ax * dt; b.uy -= 2.5 * ay * dt
            if dt >= t_end - 1e-12:
                b.ux, b.uy = b.vx, b.vy
        else:
            b.ux, b.uy = b.vx, b.vy
            if dt >= t_end - 1e-12:
                b.vx = b.vy = b.ux = b.uy = 0.0
        t += dt
        pk = _pocket_at(b.x, b.y)
        if pk:
            return "pocket", pk, cush
        if not _in_mouth(b.x, b.y):
            if b.x < R or b.x > W - R:
                lo = b.x < R
                b.x = 2 * R - b.x if lo else 2 * (W - R) - b.x
                _cushion(b, 1.0 if lo else -1.0, 0.0)
                cush += 1
            if b.y < R or b.y > L - R:
                lo = b.y < R
                b.y = 2 * R - b.y if lo else 2 * (L - R) - b.y
                _cushion(b, 0.0, 1.0 if lo else -1.0)
                cush += 1
        cush += _jaws(b)
    return "stop", None, cush


def _collide(st, ob):
    """st (moving) strikes ob (at rest): normal impulse with restitution E_BB and the throw of Alciatore's friction
    model (mu falling with the slip speed): the struck ball is pushed along the striker's sideways slip; the slip has
    a sideways part (the cut) and an upright part (the striker's roll or draw). Returns the struck ball's start
    direction in degrees."""
    nx, ny = ob.x - st.x, ob.y - st.y
    d = math.hypot(nx, ny)
    nx, ny = nx / d, ny / d
    vn = st.vx * nx + st.vy * ny
    k = 0.5 * (1 + E_BB) * vn
    tx, ty = st.vx - vn * nx, st.vy - vn * ny
    vz = -(st.ux * nx + st.uy * ny)
    v_rel = math.sqrt(tx * tx + ty * ty + vz * vz)
    f = min((0.00995 + 0.108 * math.exp(-1.088 * v_rel)) * k / v_rel, 1.0 / 7.0) if v_rel > 1e-9 else 0.0
    ob.vx, ob.vy = k * nx + f * tx, k * ny + f * ty
    ob.ux = ob.uy = 0.0
    st.vx -= k * nx + f * tx; st.vy -= k * ny + f * ty
    return math.degrees(math.atan2(ob.vy, ob.vx))


def predict(cue, balls: dict, phi_deg: float, V: float, b: float = 0.0, max_hits: int = 6) -> dict:
    """The analytic model's outcome of a stroke: first_hit, pocketed {id: pocket}, positions, cushion_after_first,
    ob_dir (the first ball's start direction). The moving balls are followed one at a time against the balls at rest
    (a struck ball first, then the ball that struck it), up to max_hits contacts; after that the rest stop where
    they are."""
    v0 = 2.0 * V / (1.3 + 2.5 * b * b)            # the cue strike: centre hit 1.54 V; spin-equivalent 2.5 b v0
    u0 = 2.5 * b * v0
    c, s = math.cos(math.radians(phi_deg)), math.sin(math.radians(phi_deg))
    rest = {k: (float(v[0]), float(v[1])) for k, v in balls.items()}
    out = {"first_hit": None, "pocketed": {}, "cushion_after_first": False}
    stack = [("cue", _Ball(float(cue[0]), float(cue[1]), v0 * c, v0 * s, u0 * c, u0 * s))]
    hits = 0
    while stack:
        bid, bl = stack.pop()
        if hits >= max_hits:
            rest[bid] = (bl.x, bl.y)
            continue
        ev, info, cu = _advance(bl, rest)
        if out["first_hit"] is not None and cu:
            out["cushion_after_first"] = True
        if ev == "pocket":
            out["pocketed"][bid] = info
            if out["first_hit"] is not None:
                out["cushion_after_first"] = True
        elif ev == "stop":
            rest[bid] = (bl.x, bl.y)
        else:
            hid = info[0]
            hits += 1
            if bid == "cue" and out["first_hit"] is None:
                out["first_hit"] = hid
            hx, hy = rest.pop(hid)
            hb = _Ball(hx, hy)
            d = _collide(bl, hb)
            if bid == "cue" and hid == out["first_hit"] and "ob_dir" not in out:
                out["ob_dir"] = d
            stack.append((bid, bl))                  # the striker continues after the struck ball has moved
            stack.append((hid, hb))
    out["positions"] = rest
    return out


def pot_prob(o: dict, sigma_deg: float = SIGMA_DEG) -> float:
    """The chance of a direct pot from geometry: an aim error e turns the object ball by about e d1 / (2R cos(cut));
    it must arrive within POCKET_TOL of the pocket's aim point after d2 (plus a floor for throw and speed)."""
    cosc = max(math.cos(math.radians(o["cut_deg"])), 0.2)
    s_ob = math.radians(sigma_deg) * o["d1"] / (2 * R * cosc) + 0.004
    return float(math.erf(POCKET_TOL[o["pocket"]] / max(o["d2"], 0.05) / (math.sqrt(2.0) * s_ob)))


def best_pot_prob(cue, balls: dict, targets) -> float:
    if cue is None or not targets:
        return 0.0
    return max((pot_prob(o) for o in pot_options(cue, balls, targets)[:6]), default=0.0)


def group_balls(table: dict, group: str) -> list:
    """The balls of a group text of the observation ('open', 'solids', 'stripes (on the 8)', ...) that I may hit."""
    return targets_for(table, group)


class Planner:
    """decide_plan(): position play, safeties and defence on the analytic model. The switches weaken one capability
    each (the capability-sensitivity check), in two strengths where it makes sense: safety=False never plays safe,
    pot_min=0.2 plays safe only when its best pot is very hard (default 0.55); blind_opp=True leaves the opponent's
    balls out of its picture once the groups are set, read_opp=False sees them but ignores what a safety leaves the
    opponent; position=False ignores where the cue ball stops, gamma=0.25 weighs it less (default 0.7)."""

    def __init__(self, table: dict, state: dict, safety: bool = True, blind_opp: bool = False, position: bool = True,
                 pot_min: float | None = None, read_opp: bool = True, gamma: float | None = None):
        self.state, self.use_safety, self.position = state, safety, position
        self.pot_min = PLAN["pot_min"] if pot_min is None else pot_min
        self.read_opp = read_opp
        self.gamma = PLAN["gamma"] if gamma is None else gamma
        self.mine = state.get("your_group", "open")
        self.theirs = state.get("opponent_group", "open")
        balls = dict(table["balls"])
        if blind_opp and not self.mine.startswith("open"):
            own = "solid" if self.mine.startswith("solids") else "stripe"
            balls = {b: p for b, p in balls.items() if table["kind"].get(b) in (own, "eight")}
        self.table = dict(table, balls=balls, kind={b: table["kind"][b] for b in balls})
        self.balls = balls

    def next_targets(self, ball: str, newpos: dict):
        if ball == "8":
            return None
        kind = self.table["kind"]
        own = kind[ball] if self.mine.startswith("open") else ("solid" if self.mine.startswith("solids") else "stripe")
        left = [b for b in newpos if kind.get(b) == own]
        return left if left else (["8"] if "8" in newpos else [])

    def opp_targets(self, newpos: dict) -> list:
        t = {b: p for b, p in newpos.items() if b != "cue"}
        return targets_for(dict(self.table, balls=t, kind={b: self.table["kind"][b] for b in t}), self.theirs)

    def throw_aim(self, cue, o, V, b) -> float:
        """The ghost-ball aim corrected for throw: two Newton steps on the object ball's start direction (the model's
        ob_dir) towards the pocket's aim point; the object ball turns by about d1 / (2R cos(cut)) per unit of aim."""
        ob = np.asarray(self.balls[o["ball"]], dtype=float)
        tgt = POCKET_AIM[o["pocket"]] - ob
        want = math.degrees(math.atan2(tgt[1], tgt[0]))
        gain = o["d1"] / (2 * R * max(math.cos(math.radians(o["cut_deg"])), 0.3))
        phi = o["phi"]
        for _ in range(2):
            out = predict(cue, self.balls, phi, V, b)
            if out["first_hit"] != o["ball"] or "ob_dir" not in out:
                return o["phi"]
            err = (out["ob_dir"] - want + 180.0) % 360.0 - 180.0
            if abs(err) < 0.05:
                break
            phi += err / gain
        return phi % 360.0

    def judge_robust(self, cue, o, V, b, p0) -> float:
        """judge_pot over the stroke and two neighbours (aim +-PERTURB_DEG, speed -+5%): the model's error grows with
        the speed, so a leave that only one of them reaches is not trusted; a scratch in any of them costs."""
        vals = []
        for da, dv in ((0.0, 1.0),) + PERTURB:
            vals.append(self.judge_pot(o, predict(cue, self.balls, o["phi"] + da, V * dv, b), p0))
            if vals[0] <= 0.1 * p0:
                return vals[0]
        if min(vals) < 0:
            return min(vals) if vals[0] < 0 else 0.5 * p0 + 0.5 * min(vals)
        return sum(vals) / len(vals)

    def judge_pot(self, o, out, p0) -> float:
        pk = out["pocketed"]
        if "cue" in pk:
            return -1.0
        if out["first_hit"] != o["ball"]:
            return 0.05 * p0
        if "8" in pk and o["ball"] != "8":
            return -1.0
        if pk.get(o["ball"]) != o["pocket"]:
            return 0.1 * p0
        newpos = {k: v for k, v in out["positions"].items() if k != "cue"}
        nxt = self.next_targets(o["ball"], newpos)
        if nxt is None:
            return 10.0 * p0
        return p0 * (1.0 + self.gamma * best_pot_prob(out["positions"].get("cue"), newpos, nxt))

    def pots(self, cue, targets, opts=None):
        opts = opts if opts is not None else pot_options(cue, self.balls, targets)
        opts = sorted(opts, key=lambda o: -pot_prob(o))[:PLAN["pots"]]
        strokes = STROKES if self.position else STROKES[:1]
        best = None
        for o in opts:
            p0 = pot_prob(o)
            for vm, b in strokes:
                if best is not None and p0 * (1.0 + self.gamma) <= best[0]:
                    break
                V = float(np.clip(o["V"] * vm, 0.5, 5.5))
                oc = dict(o, phi=self.throw_aim(cue, o, V, b))
                u = self.judge_robust(cue, oc, V, b, p0) if self.position else p0
                if best is None or u > best[0]:
                    best = (u, p0, {"aim_deg": oc["phi"], "speed": V, "spin_y": b, "call": f"{o['ball']}:{o['pocket']}",
                                    "plan": f"pot {o['ball']} in {o['pocket']}"})
        return best

    def placements(self, targets, kitchen: bool) -> list:
        cands = []
        for bid in targets:
            ob = np.asarray(self.balls[bid], dtype=float)
            for pk, tgt in POCKET_AIM.items():
                u = (tgt - ob) / np.linalg.norm(tgt - ob)
                best = None
                for ang in (0.0, 20.0, -20.0):
                    c, s_ = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                    w = np.array([c * u[0] - s_ * u[1], s_ * u[0] + c * u[1]])
                    for back in (0.2, 0.35, 0.12):
                        xy = ob - 2 * R * u - back * w
                        if placement_error(self.balls, xy, kitchen):
                            continue
                        opts = [o for o in pot_options(xy, self.balls, [bid]) if o["pocket"] == pk]
                        if opts and (best is None or pot_prob(opts[0]) > best[0] + 1e-9):
                            best = (pot_prob(opts[0]), (float(xy[0]), float(xy[1])), opts[0])
                if best is not None:
                    cands.append(best)
        cands.sort(key=lambda c: -c[0])
        return cands

    def safety_value(self, cue, t, phi, V):
        """The value of a safety stroke in the model: 1 - the other player's best pot chance from the table it leaves;
        None if the model says it is a foul (first ball not t, no cushion after it and nothing down, a scratch, the 8)."""
        out = predict(cue, self.balls, phi, V, 0.0)
        pk = out["pocketed"]
        if out["first_hit"] != t or "cue" in pk or "8" in pk or not (pk or out["cushion_after_first"]):
            return None
        newpos = {k: v for k, v in out["positions"].items() if k != "cue"}
        if not self.read_opp:
            return 1.0
        return 1.0 - best_pot_prob(out["positions"].get("cue"), newpos, self.opp_targets(newpos))

    def safety(self, cue, targets):
        """The safety that leaves the other player the hardest best pot: full and cut hits on the nearest target balls
        with a clear path, soft to firm; the best few judged again with the aim off by +-PERTURB_DEG (the worst of the
        three counts, a foul in any of them costs)."""
        cue = np.asarray(cue, dtype=float)
        obs = {k: np.asarray(v, dtype=float) for k, v in self.balls.items()}
        order = sorted((t for t in targets if t in obs), key=lambda t: float(np.linalg.norm(obs[t] - cue)))
        clear = [t for t in order if all(_seg_dist(q, cue, obs[t]) >= 2 * R + 0.002 for oid, q in obs.items() if oid != t)]
        cands = []
        for t in clear[:PLAN["safety_balls"]]:
            d = obs[t] - cue
            perp = np.array([-d[1], d[0]]) / np.linalg.norm(d)
            for c in PLAN["safety_cuts"]:
                aim = obs[t] + c * 2 * R * perp - cue
                phi = math.degrees(math.atan2(aim[1], aim[0])) % 360.0
                for V in PLAN["safety_speeds"]:
                    v = self.safety_value(cue, t, phi, V)
                    if v is not None:
                        cands.append((v, t, phi, V))
        best = None
        for v, t, phi, V in sorted(cands, key=lambda c: -c[0])[:PLAN["safety_robust"]]:
            vals = [v] + [self.safety_value(cue, t, phi + da, V * dv) for da, dv in PERTURB]
            val = min(-0.5 if x is None else x for x in vals)
            if best is None or val > best[0]:
                best = (val, {"aim_deg": phi, "speed": V, "spin_y": 0.0, "call": "safety", "plan": f"safety on {t}"})
        return best

    def decide(self) -> dict:
        st, balls = self.state, self.balls
        if st.get("break_shot"):
            return decide(self.table, st)
        targets = targets_for(self.table, self.mine)
        bih = st.get("ball_in_hand")
        kitchen = "head string" in str(bih or "")
        if kitchen:
            targets = [t for t in targets if balls[t][1] >= HEAD_STRING_Y]
            if not targets:
                return decide(self.table, st)        # down the table and back (the simple player's shot)
        dec = {"type": "shoot", "spin_x": 0.0, "spin_y": 0.0}
        cue = self.table["cue"]
        defend = "on the 8" in self.theirs and "on the 8" not in self.mine
        pot_min = max(PLAN["pot_min_defend"], self.pot_min) if defend else self.pot_min
        pot = None
        if bih:
            place = None
            for q, xy, o in self.placements(targets, kitchen)[:PLAN["places"]]:
                r = self.pots(xy, targets, opts=[o])
                if r is not None and (pot is None or r[0] > pot[0]):
                    pot, place = r, xy
            if place is None:
                place = cue if cue is not None and placement_error(balls, cue, kitchen) is None else (
                    kitchen_spot(balls) if kitchen else free_spot(balls, *HEAD_SPOT))
            cue = place
            dec.update(cue_x=float(place[0]), cue_y=float(place[1]))
        else:
            if cue is None:
                cue = free_spot(balls, *HEAD_SPOT)
            pot = self.pots(cue, targets)
        if pot is not None and pot[0] > 0 and (pot[1] >= pot_min or not self.use_safety):
            return dict(dec, **pot[2])
        sf = self.safety(cue, targets) if self.use_safety else None
        if sf is not None and (pot is None or pot[0] <= 0 or sf[0] > pot[1]):
            return dict(dec, **sf[1])
        if pot is not None:
            return dict(dec, **pot[2])
        s0 = safety(cue, balls, targets)
        if self.use_safety:
            return dict(dec, aim_deg=s0["phi"], speed=s0["V"], call="safety", plan=s0["plan"])
        b = min((t for t in targets if t in balls), key=lambda t: float(np.linalg.norm(np.asarray(balls[t]) - cue)),
                default=None)               # no safety: still call the nearest ball into its nearest pocket
        pk = min(POCKET_AIM, key=lambda k: float(np.linalg.norm(POCKET_AIM[k] - np.asarray(balls[b])))) if b else None
        return dict(dec, aim_deg=s0["phi"], speed=s0["V"], call=f"{b}:{pk}" if b else "safety", plan=s0["plan"])


def decide_plan(table: dict, state: dict, **kw) -> dict:
    """The planning reference's next shot (the HTTP body of `act`) plus a `plan` text."""
    return Planner(table, state, **kw).decide()


def top_image(obs: dict):
    """The `top` tile of the observation PNG."""
    img = Image.open(io.BytesIO(base64.b64decode(obs["image_png_b64"]))).convert("RGB")
    t = next(t for t in obs["tiles"] if t["camera"] == "top")
    return img.crop((t["x"], t["y"], t["x"] + t["width"], t["y"] + t["height"]))


def _r6(x):
    return round(float(x), 6)


class Greedy:
    """The simple greedy player (billiards-2's reference, Season 1's oracle): decide() on the balls perceived in the top
    camera image. A shot the service refused (over HTTP the client then asks again for the same shot number) is
    simplified: first without the cue placement, then called safety."""
    KW: dict = {}

    def __init__(self, spec, seat, seed=0):
        set_table(spec["table"])
        self.last, self.retry, self.plan = None, 0, ""

    def choose(self, table, st):
        return decide(table, st)

    TRUTH = False                                 # screening only: the true positions instead of the image

    def table(self, view) -> dict:
        """The balls this player sees: perceived in the top camera image; a truth variant (TRUTH, screening only:
        tools/screen and refcheck.reference_match put the true positions in view["truth"]) reads them instead."""
        st, obs = view["state"], view["observation"]
        if self.TRUTH:
            return truth_table(view["truth"])
        cam = next(c for c in obs["cameras"] if c["name"] == "top")
        return perceive(top_image(obs), cam, st.get("balls_on_table"))

    def act(self, view):
        st = view["state"]
        table = self.table(view)
        dec = self.choose(table, st)
        self.plan = dec.pop("plan")
        n = st.get("shot_number")
        self.retry = self.retry + 1 if n == self.last else 0
        self.last = n
        if self.retry >= 1:
            dec.pop("cue_x", None)
            dec.pop("cue_y", None)
        if self.retry >= 2 and "call" in dec:
            dec["call"] = "safety"
        return {k: (_r6(v) if isinstance(v, float) else v) for k, v in dec.items()}

    def review(self, reply):
        return "reference player: " + (self.plan or "shot recorded"), "reference player: easiest legal pot next"


class Reference(Greedy):
    """The reference player (billiards-3): decide_plan() on the balls perceived in the top camera image: position play,
    safeties, ball in hand and defence against the 8 on the analytic table model; same refusal handling as Greedy."""

    def choose(self, table, st):
        return decide_plan(table, st, **self.KW)

    def review(self, reply):
        return "reference player: " + (self.plan or "shot recorded"), "reference player: planned pot or safety next"


class NoSafety(Reference):
    """Capability check: the reference that never plays safe (b2, shot choice)."""
    KW = {"safety": False}


class BlindOpp(Reference):
    """Capability check: the reference blind to the opponent's balls once the groups are set (b2, reading the opponent)."""
    KW = {"blind_opp": True}


def truth_table(pos: dict) -> dict:
    """The table as perceive() returns it, from true positions (screening only): {"cue", "balls", "kind"}."""
    balls = {k: (float(v[0]), float(v[1])) for k, v in pos.items() if k != "cue"}
    kind = {b: "eight" if b == "8" else ("solid" if int(b) < 8 else "stripe") for b in balls}
    cue = pos.get("cue")
    return {"cue": None if cue is None else (float(cue[0]), float(cue[1])), "balls": balls, "kind": kind}


def _truth(cls, kw=None, name=None):
    """A screening variant of a player: true positions (view["truth"]) instead of the image, the planner's options kw."""
    attrs = {"TRUTH": True, "__doc__": f"Screening only: {cls.__name__} on the true positions" + (f", {kw}" if kw else "")}
    if kw is not None:
        attrs["KW"] = kw
    return type(name or ("Truth" + cls.__name__), (cls,), attrs)


# The screening variants (sports/billiards/screen/hooks.py, refcheck.reference_match): the reference, the greedy baseline and
# the capability-sensitivity players on the true positions; each capability weakened in two strengths (step 4).
TRUTH_PLAYERS = {
    "reference_truth": _truth(Reference),
    "greedy_truth": _truth(Greedy),
    "nosafety": _truth(Reference, {"safety": False}, "TruthNoSafety"),            # b2 shot choice: never safe
    "nosafety_weak": _truth(Reference, {"pot_min": 0.2}, "TruthNoSafetyWeak"),     # safe only when the pot is very hard
    "blindopp": _truth(Reference, {"blind_opp": True}, "TruthBlindOpp"),          # b2 reading the opponent: blind
    "blindopp_weak": _truth(Reference, {"read_opp": False}, "TruthBlindOppWeak"),  # sees them, ignores the leave
    "nopos": _truth(Reference, {"position": False}, "TruthNoPos"),                # a2/b2 position: plain strokes
    "nopos_weak": _truth(Reference, {"gamma": 0.25}, "TruthNoPosWeak"),           # position weighted a quarter
}

class Random:
    """Random valid shots, by seed only (not by seat): any direction, a firm speed, no spin, the cue ball where the
    rules put it, called safety after the break."""

    def __init__(self, spec, seat, seed=0):
        self.g = np.random.default_rng(int(seed) * 7919 + 23)

    def act(self, view):
        body = {"type": "shoot", "aim_deg": _r6(self.g.uniform(0.0, 360.0)), "speed": _r6(self.g.uniform(1.0, 6.0)),
                "spin_x": 0.0, "spin_y": 0.0}
        if not view["state"].get("break_shot"):
            body["call"] = "safety"
        return body


class Fixed:
    """A simple baseline: the same stroke every time (straight up the table, firm, no spin), called safety after the
    break; the cue ball where the rules put it."""

    def __init__(self, spec, seat, seed=0):
        pass

    def act(self, view):
        body = {"type": "shoot", "aim_deg": 90.0, "speed": 3.0, "spin_x": 0.0, "spin_y": 0.0}
        if not view["state"].get("break_shot"):
            body["call"] = "safety"
        return body
