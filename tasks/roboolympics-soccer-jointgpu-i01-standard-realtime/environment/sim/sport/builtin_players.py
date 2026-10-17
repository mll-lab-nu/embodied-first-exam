"""soccer's built-in players (same action interface as a model's program; core/client.py plays them over HTTP).

  Reference  the Season-1 camera-only reference player (scripts/olympiad/soccer/*/solution/cam_player.py) as an
             act(view) player, for any format and seat. It uses only what every player gets: the head-camera tiles
             of the observation, the own robots' state (pose from self-localization, IMU roll/pitch, trunk height),
             the referee's information and the camera model of /spec. Each call:
               1. finds the orange ball in each own robot's head camera (a colour threshold), casts the pixel's ray
                  from the camera pose (trunk pose x IMU roll/pitch x cam_to_trunk) onto the plane z = ball radius
                  and averages the robots' estimates (team frame); the opponents' jerseys (red for team A, blue for
                  team B) the same way on the plane of the trunk (z = 0.78 m);
               2. roles: the robot nearer the ball is the striker, the other guards the line between the ball and its
                  own goal (outside the own penalty area while the striker is in it: illegal defence); kick-off and
                  shoot-out roles from the referee's information; in the team formats (one robot per seat: team,
                  team_match) the seat talks with its teammate only through the team channel (core 0.2.21:
                  message(view)): every 0.2 s its pose and its own latest ball sighting (team frame, with the game
                  time it was seen); it plays with the fresher of its own and its teammate's ball sighting, takes the
                  teammate's reported pose for the roles (the same rule: the robot nearer the ball strikes, the other
                  guards) and falls back to playing as the striker while it has no recent message;
               3. striker: gets behind the ball on the line ball -> aim, lines up 0.3 m behind the spot that puts the
                  ball in the swing kick's strike zone and walks straight in slowly, turns to the aim and kicks (the
                  swing with the foot on its side of the ball; power 1 near the goal, 0.6 farther, 0 for the kick-off's
                  first touch); farther than 7 m from the goal, with an opponent within 1.5 m of the ball and room
                  behind it, the quick push instead; a corner in the shoot-out; keeps clear of the opponents (pushing is a foul); the ball estimate is kept
                  up to 6 s while a robot is too close to see it (the head camera sees the floor from ~0.55 m ahead);
                  without a ball estimate it turns on the spot to look for the ball;
               4. returns ONE act per call (the core's client and in-process loop take one body per call): the robot
                  whose command changed, round robin between the two robots of a team seat.
  Chase      the simple baseline: the reference player with every robot a striker (no division of labour).
  StepReference  the reference with the in-walk kick (style step) instead of the swing in every format (in team_match
             the Reference itself plays the in-walk kick: the format's camera reference, user decision 2026-10-13).
  StepChase  StepReference with every robot a striker (the truth reference's plan; screening variant).
  RLOpponent the RL-trained opponent (rl_opponent.py, weights rl/v2/): a built-in seat that reads the true state
             (uses_truth: view["truth"] = SoccerMatch.builtin_truth(seat), never served over HTTP); runs only inside
             the sim service (it imports the simulator's planner), never as a task's oracle.
  Stand      starts and stands still (a robot that never acts; check policy).
  Random     seeded random walk / stand / kick commands (check policy).
No simulator import: this file runs in the player's container as the task's oracle (numpy + pillow only)."""
from __future__ import annotations

import base64
import io
import json
import math

import numpy as np

HALF_L, HALF_W, BALL_R, GOAL_W, CENTER_R = 5.0, 3.5, 0.11, 2.6, 1.0
ZONE_AHEAD, ZONE_RIGHT = 0.32, 0.06           # the swing kick's strike zone centre (/spec robot.strike_zone.swing)
PSO_AIM_Y = 0.9                               # shoot-out: a corner
STAGE_M = 0.30                                # line up this far behind the kick spot, then walk straight in
PUSH_AHEAD, PUSH_RIGHT, CONTEST_M = 0.975, 0.15, 1.5   # the push kick's spot; used with an opponent near the ball
BALL_MEMORY_S, BALL_MEMORY_NEAR_S = 2.0, 6.0  # how long a ball estimate is used; longer when the ball is too close
                                              # to the feet for the head camera (it sees the floor from ~0.55 m on)
LV = dict(vmax=0.8, vlat=0.4, wmax=1.0, pos_tol=0.05, yaw_tol=0.08, shoot_m=7.0)
# the in-walk kick (style step; StepReference), as the scripted levels and the truth reference use it (soccer.STEP):
# line up on the kicking foot's line STEP_STAGE behind the ball (the ball still in the head camera's view, which
# starts ~0.55 m ahead), then send the kick walking in; the kick waits for the step that reaches the ball
STEP_LINE, STEP_STAGE, STEP_LAT_TOL, STEP_YAW_TOL, STEP_V = 0.16, 0.7, 0.06, 0.15, 0.5
TRUNK_TOP_Z = 0.85                            # overhead formats: the height at which a robot's shoulders are seen


def in_own_area(p, margin=0.0):
    """Inside the own penalty area (2 m deep, 4 m wide, the goal included) in the team frame."""
    return p[0] < -(HALF_L - 2.0 - margin) and abs(p[1]) < 2.0 + margin


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


# ------------------------------------------------------------------------------------------------ perception
def rot(roll, pitch, yaw):
    cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    return Rz @ Ry @ Rx


def find_ball(tile):
    """(u, v, n) of the orange ball's centre in a tile, or None (colour threshold, then the pixels near their median)."""
    r = tile[..., 0].astype(np.int32)
    g = tile[..., 1].astype(np.int32)
    b = tile[..., 2].astype(np.int32)
    m = (r > 90) & (g * 100 > 22 * r) & (g * 100 < 68 * r) & (b * 100 < 30 * r)
    ys, xs = np.nonzero(m)
    if len(xs) < 5:
        return None
    mx, my = np.median(xs), np.median(ys)
    half = max(6.0, 2.5 * math.sqrt(len(xs)))
    sel = (np.abs(xs - mx) <= half) & (np.abs(ys - my) <= half)
    if sel.sum() < 5:
        return None
    return float(xs[sel].mean()) + 0.5, float(ys[sel].mean()) + 0.5, int(sel.sum())


def find_robots(tile, colour):
    """Image positions (u, v, n) of the trunks of one team's jerseys (colour 'red' or 'blue'): columns of matching
    pixels grouped into blobs."""
    r = tile[..., 0].astype(np.int32)
    g = tile[..., 1].astype(np.int32)
    b = tile[..., 2].astype(np.int32)
    if colour == "red":
        m = (r > 80) & (g * 100 < 21 * r) & (b * 100 < 25 * r)
    else:
        m = (b > 80) & (r * 100 < 40 * b) & (g * 100 < 55 * b)
    cols = m.sum(axis=0)
    out, x = [], 0
    n = len(cols)
    while x < n:
        if cols[x] == 0:
            x += 1
            continue
        x0 = x
        while x < n and cols[x:x + 6].any():
            x += 1
        blob = m[:, x0:x]
        if blob.sum() >= 25:
            ys, xs = np.nonzero(blob)
            out.append((float(xs.mean() + x0) + 0.5, float(ys.mean()) + 0.5, int(blob.sum())))
    return out


def ball_from_pixel(u, v, st, K, C, z=BALL_R):
    p = st["pose"]
    R = rot(st["imu"]["roll"], st["imu"]["pitch"], p["yaw"])
    o = np.array([p["x"], p["y"], st["trunk_height"]]) + R @ C[:3, 3]
    d = R @ (C[:3, :3] @ np.array([(u - K[0][2]) / K[0][0], (v - K[1][2]) / K[1][1], 1.0]))
    if d[2] > -1e-3:
        return None
    t = (z - o[2]) / d[2]
    b = o + t * d
    if t <= 0 or t > 14 or abs(b[0]) > HALF_L + 0.5 or abs(b[1]) > HALF_W + 0.5:
        return None
    return b[:2]


# ------------------------------------------------------------------------------------------------ planning
def go(me, tgt, face=None, slow=False, others=(), opps=()):
    p, yaw = np.array([me["pose"]["x"], me["pose"]["y"]]), me["pose"]["yaw"]
    tgt = np.array([np.clip(tgt[0], -HALF_L + 0.25, HALF_L - 0.25), np.clip(tgt[1], -HALF_W + 0.25, HALF_W - 0.25)])
    e = tgt - p
    dist = float(np.hypot(*e))
    if face is None:
        face = math.atan2(e[1], e[0]) if dist > 0.25 else yaw
    elif dist > 0.8:
        face = math.atan2(e[1], e[0])
    v = 1.6 * e
    for o in others:
        rel = p - o
        dd = float(np.hypot(*rel))
        if 1e-6 < dd < 0.75:
            v += 1.2 * (0.75 - dd) / 0.75 * rel / dd
    for o in opps:                                       # keep clear of opponents (pushing is a foul)
        rel = p - o
        dd = float(np.hypot(*rel))
        if 1e-6 < dd < 0.85:
            v += 1.4 * (0.85 - dd) / 0.85 * rel / dd
    vmax = 0.15 if slow else LV["vmax"]
    sp = float(np.hypot(*v))
    if sp > vmax:
        v *= vmax / sp
    for o in opps:                                       # never walk into an opponent at the robot (pushing is a
        rel = o - p                                      # removal penalty that grows with every team offence)
        dd = float(np.hypot(*rel))
        if 1e-6 < dd < 0.75:
            n = rel / dd
            toward = float(np.dot(v, n))
            if toward > 0:
                v = v - toward * n
    c, s = math.cos(yaw), math.sin(yaw)
    vx, vy = c * v[0] + s * v[1], -s * v[0] + c * v[1]
    err = wrap(face - yaw)
    if abs(err) > 0.9:
        vx *= 0.3
        vy *= 0.3
    vx = float(np.clip(vx, -0.5 * vmax, vmax))
    vy = float(np.clip(vy, -LV["vlat"], LV["vlat"]))
    wz = float(np.clip(1.8 * err, -LV["wmax"], LV["wmax"]))
    if abs(vx) < 0.04 and abs(vy) < 0.04 and abs(wz) < 0.06:
        return dict(type="stand")
    return dict(type="walk", v=[round(vx, 2), round(vy, 2), round(wz, 2)])


def kick_spot(ball, aim):
    u = aim - ball
    u /= max(np.hypot(*u), 1e-6)
    left = np.array([-u[1], u[0]])
    return ball - ZONE_AHEAD * u + ZONE_RIGHT * left, u, left


def choose_aim(ball, aim):
    """The goal if the kick spot behind the ball is on the pitch; else a target that keeps the ball going forward
    (a post, the penalty spot area, ahead of the ball); None if no kick spot is reachable (the ball at a board)."""
    for a in (aim, (HALF_L, 0.8), (HALF_L, -0.8), (HALF_L - 1.5, 0.0), (min(ball[0] + 2.0, HALF_L - 1.0), 0.0),
              (ball[0] + 1.5, 0.3 * ball[1]), (ball[0] + 1.5, ball[1]), (ball[0] + 1.0, ball[1] - 0.6 * np.sign(ball[1])),
              (ball[0] + 0.3, 0.0), (ball[0], 0.0)):
        a = np.array(a, float)
        P, u, _ = kick_spot(ball, a)
        if abs(P[0]) <= HALF_L - 0.25 and abs(P[1]) <= HALF_W - 0.25 and np.hypot(*(a - ball)) > 0.3:
            return a
    return None


def striker(me, ball, aim, power_far=0.6, first_touch=False, others=(), opps=(), fixed=False):
    p, yaw = np.array([me["pose"]["x"], me["pose"]["y"]]), me["pose"]["yaw"]
    if not fixed:
        aim = choose_aim(ball, aim)
        if aim is None:                                    # no kick spot: push the ball towards the middle
            c = -ball / max(np.hypot(*ball), 1e-6)
            return go(me, ball + 0.5 * c, face=math.atan2(c[1], c[0]), others=others)
    P, u, left = kick_spot(ball, aim)
    rel = p - ball
    face = math.atan2(u[1], u[0])
    behind, lat = float(np.dot(rel, u)), float(np.dot(rel, left))
    zr, foot = ZONE_RIGHT, "right"
    if lat < -0.03:                                      # on the ball's right: the left foot (the zone mirrored)
        zr, foot = -ZONE_RIGHT, "left"
        P = ball - ZONE_AHEAD * u + zr * left
    if behind > -0.2:                                    # not behind the ball: go round it
        side = 1.0 if lat >= 0 else -1.0
        rr = 0.9 if ball[0] < -HALF_L + 3.0 else 0.75     # wider near the own goal (no own goals on the way round)
        tgt = ball - rr * u + side * rr * left
        return go(me, tgt, face=face if np.hypot(*(p - tgt)) < 0.8 else None, others=others, opps=opps)
    if not fixed and not first_touch and behind < -0.6 and any(np.hypot(*(o - ball)) < CONTEST_M for o in opps) \
            and float(np.hypot(*(np.array([HALF_L, 0.0]) - ball))) > LV["shoot_m"]:
        # far from the goal, an opponent near the ball and room behind it: the quick push (no 2.5 s on one leg beside
        # an opponent); near the goal the swing (a kicked ball is harder to stop than a poke)
        Pp = ball - PUSH_AHEAD * u + PUSH_RIGHT * left
        ep = Pp - p
        if np.hypot(*ep) < 0.10 and abs(wrap(face - yaw)) < 0.12:
            return dict(type="kick", power=1.0, style="push")
        if np.hypot(*ep) < 0.5:
            return go(me, Pp, face=face, others=others)
    e = P - p
    contested = any(np.hypot(*(o - ball)) < 1.1 for o in opps)
    tol, ytol = (0.08, 0.12) if contested else (LV["pos_tol"], LV["yaw_tol"])
    if np.hypot(*e) < tol and abs(wrap(face - yaw)) < ytol:
        power = 1.0 if float(np.hypot(*(np.array([HALF_L, 0.0]) - ball))) < LV["shoot_m"] else power_far
        cmd = dict(type="kick", power=0.0 if first_touch else power)
        if foot != "right":
            cmd["foot"] = foot
        return cmd
    # an opponent at the ball lining up its kick, and the robot close behind the ball: press the ball (step onto it
    # from behind; a ball that moves calls the opponent's swing off), the scripted team's press
    if not fixed and not first_touch and behind < -0.2 and np.hypot(*rel) < 1.4 \
            and any(np.hypot(*(o - ball)) < 0.7 for o in opps):
        return go(me, ball - 0.2 * u, face=face, others=others)
    # otherwise an opponent right at the robot is always avoided (walking into it is pushing: a removal penalty that
    # grows with every team offence; go() never walks towards an opponent within 0.75 m)
    close = [o for o in opps if np.hypot(*(o - p)) < 0.75]
    if abs(lat - zr) > 0.10 or behind > -(ZONE_AHEAD - 0.05):   # off the line or too close: line up
        return go(me, ball - (ZONE_AHEAD + STAGE_M) * u + zr * left, face=face, others=others,
                  opps=[o for o in opps if np.hypot(*(o - ball)) > 0.6] + close)
    # then straight in, slowly; near the ball only the opponents right at the robot are avoided (the ball is between)
    return go(me, P, face=face, slow=np.hypot(*e) < 0.4, others=others,
              opps=([o for o in opps if np.hypot(*(o - ball)) > 0.6] if np.hypot(*e) > 0.4 else []) + close)


def step_striker(me, ball, aim, power_far=0.6, first_touch=False, others=(), opps=(), fixed=False):
    """The striker with the in-walk kick: behind the ball on the kicking foot's line, then kick walking in."""
    p, yaw = np.array([me["pose"]["x"], me["pose"]["y"]]), me["pose"]["yaw"]
    if not fixed:
        aim = choose_aim(ball, aim)
        if aim is None:
            c = -ball / max(np.hypot(*ball), 1e-6)
            return go(me, ball + 0.5 * c, face=math.atan2(c[1], c[0]), others=others)
    u = aim - ball
    u /= max(np.hypot(*u), 1e-6)
    left = np.array([-u[1], u[0]])
    rel = p - ball
    face = math.atan2(u[1], u[0])
    behind, lat = float(np.dot(rel, u)), float(np.dot(rel, left))
    foot, ry = ("right", STEP_LINE) if lat >= 0 else ("left", -STEP_LINE)
    err = wrap(face - yaw)
    if not fixed and not first_touch and behind < -0.2 and np.hypot(*rel) < 1.4 \
            and any(np.hypot(*(o - ball)) < 0.7 for o in opps):
        return go(me, ball - 0.2 * u, face=face, others=others)          # press an opponent at the ball
    if -STEP_STAGE - 0.25 < behind < -0.35 and abs(lat - ry) < STEP_LAT_TOL and abs(err) < STEP_YAW_TOL:
        power = 1.0 if float(np.hypot(*(np.array([HALF_L, 0.0]) - ball))) < LV["shoot_m"] else power_far
        c, s_ = math.cos(yaw), math.sin(yaw)
        vy = float(np.clip(1.5 * (ry - lat) * float(-s_ * left[0] + c * left[1]), -LV["vlat"], LV["vlat"]))
        cmd = dict(type="kick", style="step", power=0.0 if first_touch else power,
                   v=[STEP_V, round(vy, 3), round(float(np.clip(1.8 * err, -LV["wmax"], LV["wmax"])), 3)])
        if foot != "right":
            cmd["foot"] = foot
        return cmd
    if behind > -0.2:                                    # not behind the ball: go round it
        side = 1.0 if lat >= 0 else -1.0
        rr = 0.9 if ball[0] < -HALF_L + 3.0 else 0.75
        tgt = ball - rr * u + side * rr * left
        return go(me, tgt, face=face if np.hypot(*(p - tgt)) < 0.8 else None, others=others, opps=opps)
    Ps = ball - STEP_STAGE * u + ry * left
    close = [o for o in opps if np.hypot(*(o - p)) < 0.75]
    return go(me, Ps, face=face, slow=np.hypot(*(Ps - p)) < 0.3, others=others,
              opps=[o for o in opps if np.hypot(*(o - ball)) > 0.6] + close)


def overhead_ground(cam, u, v, z):
    """The point (team frame) at height z seen at pixel (u, v) of an overhead camera (game spec camera.overhead)."""
    pos, look, up = (np.array(cam[k], float) for k in ("pos", "lookat", "up"))
    fwd = (look - pos) / np.linalg.norm(look - pos)
    right = np.cross(fwd, up)
    right /= np.linalg.norm(right)
    upv = np.cross(right, fwd)
    f = float(cam["focal_px"])
    ray = fwd + right * (u - cam["width"] / 2) / f - upv * (v - cam["height"] / 2) / f
    t = (z - pos[2]) / ray[2]
    return (pos + t * ray)[:2]


def find_blobs(tile, colour, min_px=40, radius=30.0):
    """(u, v, n) of the blobs of a team colour seen from above (greedy clustering of the matching pixels)."""
    r = tile[..., 0].astype(np.int32)
    g = tile[..., 1].astype(np.int32)
    b = tile[..., 2].astype(np.int32)
    if colour == "red":
        m = (r > 80) & (g * 100 < 21 * r) & (b * 100 < 25 * r)
    else:
        m = (b > 80) & (r * 100 < 40 * b) & (g * 100 < 55 * b)
    ys, xs = np.nonzero(m[::2, ::2])
    cl = []                                              # [sum_x, sum_y, n]
    for x, y in zip(xs * 2.0, ys * 2.0):
        for c in cl:
            if abs(c[0] / c[2] - x) < radius and abs(c[1] / c[2] - y) < radius:
                c[0] += x
                c[1] += y
                c[2] += 1
                break
        else:
            cl.append([x, y, 1])
    return [(c[0] / c[2] + 1.0, c[1] / c[2] + 1.0, 4 * c[2]) for c in cl if 4 * c[2] >= min_px]


def search(me):
    return dict(type="walk", v=[0.0, 0.0, 0.6])


def image_of(obs):
    from PIL import Image
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(obs["image_png_b64"]))).convert("RGB"))


# ------------------------------------------------------------------------------------------------ the players
class Reference:
    def __init__(self, spec, seat, seed=0):
        cam = spec["camera"]
        self.K = cam.get("intrinsics")                  # head camera (the onboard formats)
        self.C = np.array(cam["cam_to_trunk"], float) if "cam_to_trunk" in cam else None
        self.overhead = cam.get("overhead")             # the overhead formats: fixed cameras, the team's frame
        self.robots = [str(r) for r in spec["your_robots"]]
        self.team_fmt = len(self.robots) == 1           # one robot per seat: the team formats (team, team_match)
        self.all_strike = False                         # Chase: every robot a striker
        # the kick: the swing, except in team_match, where the reference plays the in-walk kick (user decision
        # 2026-10-13; the match format keeps the swing until the next soccer revision); StepReference: always the step
        self.kick = step_striker if spec.get("format") == "team_match" else striker
        self.ball = None                                # (xy, t_sim): the ball estimate played with
        self.own = None                                 # (xy, t_sim): this seat's own latest sighting (team formats)
        self.mate = None                                # the teammate's latest message (team channel), with t_recv
        self.heard = set()                              # (from, k) of the messages read: each used once
        self.last_say = -9.0
        self.i_strike = False                           # team formats: this seat's robot claims the striker role
        self.unit_t = 0.0
        self.last_cmd = {}
        self.striker_robot = None
        self.opp_colour = "red" if spec["team"] == "A" else "blue"
        self.opps = []                                  # [(xy, t_sim)] opponent trunk estimates
        self.unit = None
        self.rr = 0
        if self.overhead:                               # overhead reference: every robot chases, the in-walk kick
            self.all_strike = True                      # (the truth reference's play, soccer.Coach("reference"))
            self.kick = step_striker

    def perceive_overhead(self, obs, now):
        tiles = {t["camera"]: t for t in obs.get("tiles") or []}
        if not obs.get("image_png_b64") or not tiles:
            return False
        img = image_of(obs)
        est, opp = [], []
        for cam in self.overhead:
            t = tiles.get(cam["name"])
            if t is None:
                continue
            tile = np.ascontiguousarray(img[t["y"]:t["y"] + t["height"], t["x"]:t["x"] + t["width"]])
            det = find_ball(tile)
            if det:
                b = overhead_ground(cam, det[0], det[1], BALL_R)
                if abs(b[0]) <= HALF_L + 0.5 and abs(b[1]) <= HALF_W + 0.5:
                    est.append(b)
            for (u, v, n) in find_blobs(tile, self.opp_colour):
                opp.append(overhead_ground(cam, u, v, TRUNK_TOP_Z))
        t_frame = now["t_sim"]
        if est:
            self.ball = self.own = (np.mean(est, axis=0), t_frame)
        merged = []
        for o in opp:
            if all(np.hypot(*(o - q)) > 0.5 for q in merged):
                merged.append(o)
        self.opps = [(o, t_frame) for o in merged]
        return bool(est)

    def perceive(self, obs, now):
        if self.overhead:
            return self.perceive_overhead(obs, now)
        tiles = {t["camera"]: t for t in obs.get("tiles") or []}
        if not obs.get("image_png_b64") or not tiles:
            return False
        img = image_of(obs)
        t_frame = now["t_sim"]
        est, opp = [], []
        for r in self.robots:
            st, t = now["robots"][r], tiles.get(f"robot{r}")
            if t is None or st["fallen"] or st["penalized"]:
                continue
            tile = np.ascontiguousarray(img[t["y"]:t["y"] + t["height"], t["x"]:t["x"] + t["width"]])
            for (u, v, n) in find_robots(tile, self.opp_colour):
                o = ball_from_pixel(u, v, st, self.K, self.C, z=0.78)
                if o is not None:
                    opp.append(o)
            det = find_ball(tile)
            if det:
                b = ball_from_pixel(det[0], det[1], st, self.K, self.C)
                if b is not None:
                    est.append(b)
        if est:
            self.ball = (np.mean(est, axis=0), t_frame)
            self.own = self.ball
        merged = []
        for o in opp:
            if all(np.hypot(*(o - q)) > 0.5 for q in merged):
                merged.append(o)
        self.opps = [(o, t_frame) for o in merged] + [(o, t) for (o, t) in self.opps if t_frame - t < 1.0 and
                                                     all(np.hypot(*(o - q)) > 0.7 for q in merged)]
        for m in now.get("team_messages") or []:
            try:
                key = (m["from"], int(m["k"]))
                if key in self.heard:                   # a message delivered again is used once
                    continue
                self.heard.add(key)
                j = json.loads(m["text"])
                if isinstance(j, dict) and isinstance(j.get("p"), list) and (self.mate is None or
                                                                            j.get("t", 0) >= self.mate.get("t", 0)):
                    self.mate = dict(j, t_recv=t_frame)
            except (ValueError, TypeError, KeyError):
                pass
        mb = (self.mate or {}).get("b")
        if mb is not None and self.mate.get("bt", -1) >= self.unit_t and \
                (self.ball is None or self.mate["bt"] > self.ball[1] + 0.05):
            self.ball = (np.array(mb[:2], float), float(self.mate["bt"]))   # the teammate saw it more recently
        return bool(est)

    def mate_pos(self, now):
        """{robot number: xy} of the teammate from its message of the last second (standing, on the pitch)."""
        m = self.mate
        if not self.team_fmt or m is None or now["t_sim"] - m.get("t", -9) > 1.0 or m.get("f"):
            return {}
        return {str(m.get("r")): np.array(m["p"][:2], float)}

    def message(self, view):
        """Team formats: every 0.2 game s the robot's pose and its own latest ball sighting (core 0.2.21)."""
        now = view["state"]
        t = float(now.get("t_sim", 0.0))
        if not self.team_fmt or t - self.last_say < 0.2 - 1e-9 or now.get("world", "running") != "running":
            return None
        r = self.robots[0]
        st = now["robots"][r]
        self.last_say = t
        own = self.own if self.own is not None and self.own[1] >= self.unit_t else None
        return json.dumps({"r": r, "p": [round(st["pose"]["x"], 3), round(st["pose"]["y"], 3), round(st["pose"]["yaw"], 3)],
                           "f": int(bool(st["fallen"] or st["penalized"])),
                           "b": None if own is None else [round(float(own[0][0]), 3), round(float(own[0][1]), 3)],
                           "bt": None if own is None else round(own[1], 2), "s": int(self.i_strike), "t": round(t, 2)},
                          separators=(",", ":"))

    def decide(self, now):
        ref = now["referee"]
        rs = now["robots"]
        out = {}
        mine = {r: np.array([rs[r]["pose"]["x"], rs[r]["pose"]["y"]]) for r in self.robots}
        team = {**self.mate_pos(now), **mine}           # + the teammate's reported pose (team formats)
        ball = None
        if self.ball is not None:
            age = now["t_sim"] - self.ball[1]
            near = min(float(np.hypot(*(q - self.ball[0]))) for q in mine.values()) < 0.7
            if age <= BALL_MEMORY_S or (near and age <= BALL_MEMORY_NEAR_S):
                ball = self.ball[0]
        opps = [o for (o, t) in self.opps if now["t_sim"] - t < 1.0]
        so = ref.get("shootout") or {}
        cur = so.get("current")
        ko = ref.get("kickoff")
        for r in self.robots:
            st = rs[r]
            if st["fallen"] or st["penalized"] or st["command"]["type"] == "kick":
                continue
            oth = [o for rr, o in team.items() if rr != r]
            if ref["state"] == "pso_kick" and cur:
                if cur["we_shoot"] and cur["striker"] == "us" + r:
                    if ball is None:
                        out[r] = search(st)
                        continue
                    side = PSO_AIM_Y if (cur["n"] % 2) else -PSO_AIM_Y
                    out[r] = self.kick(st, ball, np.array([HALF_L, side]), power_far=1.0, fixed=True)
                elif not cur["we_shoot"] and cur["keeper"] == "us" + r:
                    y = 0.0 if ball is None else float(np.clip(ball[1], -GOAL_W / 2 + 0.3, GOAL_W / 2 - 0.3))
                    out[r] = go(st, np.array([-HALF_L + 0.25, y]), face=0.0)
                else:
                    out[r] = dict(type="stand")
                continue
            if ball is None:
                # no ball estimate: the robot nearer the own goal guards it (outside the penalty area) and looks
                # around from there; the other searches
                deep = min(team, key=lambda x: (float(np.hypot(*(team[x] - np.array([-HALF_L, 0.0])))), x))
                if r == deep and len(team) > 1 and np.hypot(*(mine[r] - np.array([-(HALF_L - 2.6), 0.0]))) > 0.4:
                    out[r] = go(st, np.array([-(HALF_L - 2.6), 0.0]), others=oth, opps=opps)
                else:
                    out[r] = search(st)
                continue
            role = self.role(r, team, ball, ko)
            if role == "wait":
                out[r] = dict(type="stand")
            elif role == "striker":
                # the kick-off team scores only after a touch outside the centre circle: a soft first touch there
                first = bool(ko and ko.get("ours") and np.hypot(*ball) < CENTER_R + 0.2)
                out[r] = self.kick(st, ball, np.array([HALF_L, 0.0]), first_touch=first, others=oth, opps=opps)
            else:
                own = np.array([-HALF_L, 0.0])
                tgt = own + 0.42 * (ball - own)
                tgt[0] = min(tgt[0], -0.6)
                if any(in_own_area(o, 0.3) for o in oth[:1]) and in_own_area(tgt, 0.3):
                    tgt[0] = -(HALF_L - 2.0 - 0.45)      # illegal defence: one robot in the own penalty area
                out[r] = go(st, tgt, face=math.atan2(ball[1] - mine[r][1], ball[0] - mine[r][0]), others=oth, opps=opps)
        return out

    def role(self, r, mine, ball, ko):
        if ko and not ko.get("ball_in_play"):
            self.i_strike = bool(ko.get("ours")) and r == "1"
            return "striker" if self.i_strike else "wait"
        if self.all_strike or len(mine) < 2:            # Chase; a team-format seat without a recent message
            self.i_strike = True
            return "striker"
        d_me = {rr: float(np.hypot(*(mine[rr] - ball))) for rr in mine}
        if self.team_fmt:
            # one robot per seat: the incumbent is whoever CLAIMS the striker role (its own last decision, the
            # teammate's flag "s" in its latest message); both seats apply the same rule to the same shared data, so
            # they agree (a per-seat memory alone could leave both robots supporting, each waiting for the other)
            me = self.robots[0]
            claims = [x for x, c in ((me, self.i_strike), (str((self.mate or {}).get("r")), (self.mate or {}).get("s")))
                      if c and x in d_me]
            best = min(d_me, key=lambda x: (d_me[x], x))
            s = claims[0] if len(claims) == 1 and d_me[best] + 0.4 >= d_me[claims[0]] else best
            self.i_strike = s == me
            return "striker" if r == s else "support"
        s = self.striker_robot if self.striker_robot in d_me else None
        best = min(d_me, key=lambda x: (d_me[x], x))
        if s is None or d_me[best] + 0.4 < d_me[s]:
            s = best
        self.striker_robot = s
        return "striker" if r == s else "support"

    def act(self, view):
        now = view["state"]
        if now.get("stoppages") != self.unit:         # a new unit (after a stoppage): forget the old ball estimate
            self.unit = now.get("stoppages")
            self.ball = self.own = None
            self.unit_t = float(now.get("t_sim", 0.0))
        self.perceive(view.get("observation") or {}, now)
        want = self.decide(now)
        todo = [r for r, cmd in want.items() if cmd["type"] == "kick" or cmd != self.last_cmd.get(r)
                or now["robots"][r]["command"].get("type") != cmd["type"]]
        if not todo:
            return None
        order = self.robots[self.rr:] + self.robots[:self.rr]
        r = next(x for x in order if x in todo)
        self.rr = (self.robots.index(r) + 1) % len(self.robots)
        self.last_cmd[r] = want[r]
        return {**want[r], "entity": r}

    def review(self, reply):
        self.ball = self.own = None
        stop = (reply or {}).get("stoppage") or {}
        return f"stoppage: {stop.get('kind')}", "camera reference player: same plan"


class Chase(Reference):
    """The simple baseline "everyone chases the ball" (screening, docs/screening/soccer.md): the camera reference
    player with every robot a striker (no division of labour), in every format."""

    def __init__(self, spec, seat, seed=0):
        super().__init__(spec, seat, seed)
        self.all_strike = True


class StepReference(Reference):
    """The camera reference with the in-walk kick (style step) instead of the swing: the kick the scripted levels and
    the truth reference play since soccer-2v2-9 (screening variant; not the sport's [players] reference)."""

    def __init__(self, spec, seat, seed=0):
        super().__init__(spec, seat, seed)
        self.kick = step_striker


class StepChase(StepReference):
    """StepReference with every robot a striker (the truth reference's plan: all go for the ball, in-walk kick)."""

    def __init__(self, spec, seat, seed=0):
        super().__init__(spec, seat, seed)
        self.all_strike = True


class OverheadReference(Reference):
    """The reference player of the overhead formats (match_overhead, duel_overhead): the same class; with the game
    spec's camera.overhead it finds the ball and the opponents in the two overhead tiles (colour thresholds, the
    pixel's ray onto the plane of the ball's centre / the opponents' shoulders), every robot goes for the ball and
    kicks with the in-walk kick (the truth reference's play, soccer.Coach("reference"))."""


class OverheadChase(Reference):
    """The simple baseline of the overhead formats: every robot goes for the ball with the swing kick."""

    def __init__(self, spec, seat, seed=0):
        super().__init__(spec, seat, seed)
        self.all_strike = True
        self.kick = striker


class RLOpponent:
    """The RL opponent (rl_opponent.BuiltinRL) on a team seat; needs the simulator (imported on first use)."""
    uses_truth = True
    version = "v2"

    def __init__(self, spec, seat, seed=0):
        import rl_opponent
        self.robots = [str(r) for r in spec["your_robots"]]
        self.b = rl_opponent.BuiltinRL(str(seat)[0], self.robots, version=self.version)

    def act(self, view):
        return self.b.act(view["truth"])

    def review(self, reply):
        return "stoppage", "RL opponent: same policy"


class Stand:
    """Starts, then stands still: every robot keeps its stand command (check policy)."""

    def __init__(self, spec, seat, seed=0):
        self.robots = [str(r) for r in spec["your_robots"]]

    def act(self, view):
        return None


class Random:
    """Seeded random commands, one robot per call (check policy)."""

    def __init__(self, spec, seat, seed=0):
        self.robots = [str(r) for r in spec["your_robots"]]
        self.g = np.random.default_rng(int(seed) * 7919 + 17)        # by seed, not by seat: mirror runs match

    def act(self, view):
        r = self.robots[int(self.g.integers(len(self.robots)))]
        x = self.g.random()
        if x < 0.1:
            return {"type": "kick", "power": round(float(self.g.random()), 3), "entity": r}
        if x < 0.2:
            return {"type": "stand", "entity": r}
        return {"type": "walk", "v": [round(float(v), 3) for v in self.g.uniform(-1, 1, 3)], "entity": r}
