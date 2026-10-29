#!/usr/bin/env python3
"""Navmesh oracle for a HumanCLAW instance, closed-loop through the privileged tools (hc_tools.Env).

    python oracle.py <instance.json> <out.json>     (ORACLE_V=1: print every action)

Approach: Habitat's shortest path to the nearest goal viewpoint (turn toward the next waypoint, walk), then close in on
the nearest target box with short strides. Nav: stop within ~0.15 m. Interact (HumanCLAW's own recipe, prompts/v4):
touch the target, turn the back to it, step back up to two chunks, sit for 3-4 chunks at the target height, stop.
Tries a few variants (free resets) until one succeeds. Writes {"actions": [[id, value], ...], "success", ...}.
"""
import json, math, os, sys, time
sys.path.insert(0, "/opt/tools")   # hc_tools (the privileged tools)
import numpy as np
import hc_tools
VERBOSE = os.environ.get("ORACLE_V") == "1"

SEAT = {"bed": 0.55, "couch": 0.45, "sofa": 0.45, "toilet": 0.42}


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def heading_to(p, q):
    dx, dz = q[0] - p[0], q[2] - p[2]
    return math.degrees(math.atan2(-dx, -dz))


class Runner:
    def __init__(self, env):
        self.env = env

    def st(self):
        return self.env.state()

    def left(self):
        return self.st()["actions_left"]

    def act(self, a, v=0.0):
        r = self.env.step(a, v)
        if VERBOSE:
            print("  act", a, round(float(v), 3), "pos", [round(x, 2) for x in r["position"]], "hd", round(r["heading_deg"], 1),
                  "d", round(r["body_target_distance_m"], 3), "left", r["actions_left"], flush=True)
        return r

    def face(self, want_deg, tol=12.0):
        """Turn toward an absolute heading (one or two turns). Returns the residual."""
        for _ in range(2):
            s = self.st()
            d = wrap(want_deg - s["heading_deg"])
            if abs(d) <= tol or s["done"] or s["actions_left"] <= 3:
                return d
            self.act(2, float(np.clip(d, -120, 120)) if abs(d) >= 10 else math.copysign(10.0, d))
        return wrap(want_deg - self.st()["heading_deg"])


def nearest_box_point(p, aabbs):
    cands = [np.clip(p, lo, hi) for lo, hi in aabbs]
    return min(cands, key=lambda q: math.hypot(q[0] - p[0], q[2] - p[2]))


def approach_points(env, aabbs, p0, path, off=0.3, step=0.35):
    """Reachable floor points just outside each target box, one per side and box, nearest (geodesic) first."""
    out = []
    for lo, hi in aabbs:
        x0, x1, z0, z1 = lo[0] - off, hi[0] + off, lo[2] - off, hi[2] + off
        sides = {"x0": [(x0, z) for z in np.arange(z0, z1 + 1e-6, step)], "x1": [(x1, z) for z in np.arange(z0, z1 + 1e-6, step)],
                 "z0": [(x, z0) for x in np.arange(x0, x1 + 1e-6, step)], "z1": [(x, z1) for x in np.arange(x0, x1 + 1e-6, step)]}
        for side, pts in sides.items():
            best = None
            for x, z in pts:
                g = [float(x), float(p0[1]), float(z)]
                sp = path(g, 0.25)
                if not sp["found"] or not np.isfinite(sp["geodesic_m"]) or not sp["points"]:
                    continue
                e = sp["points"][-1]
                if math.hypot(e[0] - x, e[2] - z) > 0.15:
                    continue
                if best is None or sp["geodesic_m"] < best[0]:
                    best = (sp["geodesic_m"], g)
            if best:
                out.append(best)
    out.sort(key=lambda b: b[0])
    return out


def attempt(env, var):
    env.reset()
    R = Runner(env)
    tg = env.targets()
    inter = tg["interaction"]
    aabbs = [(np.array(b["min"]), np.array(b["max"])) for b in tg["aabbs"]]
    rad = var.get("rad", 0.35)
    def path(goal, r=None):
        try:
            sp = env.shortest_path(goal, agent_radius=r if r is not None else rad)
        except Exception:
            sp = {"found": False, "geodesic_m": float("inf"), "points": []}
        if not sp["found"] or not np.isfinite(sp["geodesic_m"]):
            sp = env.shortest_path(goal)
        return sp
    p0 = np.array(R.st()["position"])
    best = None
    if var.get("approach") is None:
        for vp in tg["goal_viewpoints"]:
            sp = path(vp)
            if sp["found"] and np.isfinite(sp["geodesic_m"]) and (best is None or sp["geodesic_m"] < best[0]):
                best = (sp["geodesic_m"], vp)
    else:
        cands = approach_points(env, aabbs, p0, path)
        k = int(var["approach"])
        if k < len(cands):
            best = cands[k]
        elif cands:
            return None                                   # no such approach point: skip this variant
    goal = best[1] if best else list(nearest_box_point(p0, aabbs))
    if VERBOSE:
        print("  start", [round(x, 2) for x in p0], "hd", round(R.st()["heading_deg"], 1), "goal", [round(x, 2) for x in goal],
              "geo", best and round(best[0], 2), "path", [[round(x, 2) for x in q] for q in path(goal)["points"]][:8], flush=True)
    near = var.get("near", 0.6)
    reserve = 12 if inter else 4
    # 1) the path
    stuck = 0
    for _ in range(90):
        s = R.st()
        if s["done"] or s["actions_left"] <= reserve or s["body_target_distance_m"] <= near:
            break
        p = np.array(s["position"])
        sp = path(goal)
        pts = [np.array(q) for q in sp["points"]]
        if not sp["found"] or not pts or sp["geodesic_m"] < 0.3:
            break
        nxt = next((q for q in pts[1:] if math.hypot(q[0] - p[0], q[2] - p[2]) > 0.3), pts[-1])
        if abs(R.face(heading_to(p, nxt), tol=15.0)) > 15.0:
            continue
        d = math.hypot(nxt[0] - p[0], nxt[2] - p[2])
        R.act(0, 0.6 if d > 1.0 else 0.4 if d > 0.5 else 0.2)
        q1 = np.array(R.st()["position"])
        if math.hypot(q1[0] - p[0], q1[2] - p[2]) < 0.08:
            stuck += 1
            R.act(5, 0.2)                                   # back off, then slide sideways
            R.act(6, 0.3 if stuck % 2 else -0.3)
        else:
            stuck = max(0, stuck - 1)
    # 2) close in on the nearest box
    goal_d = 0.0 if inter else var.get("nav_stop", 0.12)
    stuck = 0
    for _ in range(30):
        s = R.st()
        if s["done"] or s["actions_left"] <= reserve or s["body_target_distance_m"] <= goal_d + 1e-6:
            break
        p = np.array(s["position"])
        q = nearest_box_point(p, aabbs)
        if abs(R.face(heading_to(p, q), tol=15.0)) > 15.0:
            continue
        before = s["body_target_distance_m"]
        R.act(0, 0.4 if before > 0.8 else 0.2)
        if R.st()["body_target_distance_m"] >= before - 0.01:
            stuck += 1
            if stuck >= 2:   # blocked: try a side step toward the box
                R.act(6, 0.2 if (stuck % 2 == 0) else -0.2)
            if stuck >= 4:
                break
    if inter and not R.st()["done"]:
        p = np.array(R.st()["position"])
        lo, hi = min(aabbs, key=lambda b: math.hypot(*(((b[0] + b[1]) / 2 - p)[[0, 2]])))
        q = nearest_box_point(p, [(lo, hi)])
        away = wrap(heading_to(p, q) + 180.0 + var.get("away_off", 0.0))
        R.face(away, tol=12.0)
        for _ in range(var.get("back", 1)):
            if R.st()["actions_left"] <= 6:
                break
            R.act(5, var.get("back_m", 0.2))
        h = SEAT.get(tg["category"], 0.45) + var.get("dh", 0.0)
        for _ in range(var.get("sits", 3)):
            if R.st()["actions_left"] <= 2 or R.st()["done"]:
                break
            R.act(4, h)
            if R.st()["pelvis_touches_target"] and not var.get("all_sits"):
                break                                     # landed on it: stop now (the last motion must touch)
    if not R.st()["done"]:
        R.act(1, 0.0)
    s = R.st()
    return {"actions": [list(map(float, r)) for r in env.session.rows], "success": bool(s["success"]),
            "n": len(env.session.rows), "final_sha": env.state_sha(), "variant": var,
            "final_distance": s["body_target_distance_m"], "metrics": env.session.result.get("metrics")}


A = {"near": 0.2, "rad": 0.25}
VARIANTS = [{}, {**A, "approach": 0}, {**A, "approach": 1}, {"rad": 0.45}, {**A, "approach": 0, "back": 2},
            {**A, "approach": 2}, {"back": 2, "back_m": 0.35}, {**A, "approach": 3}, {**A, "approach": 1, "back": 0}]
NAV_VARIANTS = [{}, {**A, "approach": 0}, {**A, "approach": 1}, {"rad": 0.45}, {**A, "approach": 2},
                {**A, "approach": 3}]


def main():
    inst, out = sys.argv[1], sys.argv[2]
    t0 = time.time()
    env = hc_tools.Env(inst)
    tries = []
    vs = VARIANTS if env.targets()["interaction"] else NAV_VARIANTS
    if os.environ.get("ORACLE_MAX"):
        vs = vs[:int(os.environ["ORACLE_MAX"])]
    res, last = None, None
    for v in vs:
        r = attempt(env, v)
        if r is None:
            continue
        last = r
        tries.append({"variant": v, "success": r["success"], "n": r["n"], "d": r["final_distance"]})
        print(json.dumps(tries[-1]), flush=True)
        if r["success"]:
            res = r
            break
    if res is None:
        res = last
    res["tries"] = tries
    res["start_sha"] = None
    env.reset(); res["start_sha"] = env.state_sha()
    env.close()
    res["seconds"] = round(time.time() - t0, 1)
    try:
        import torch
        res["gpu"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    json.dump(res, open(out, "w"))
    print(json.dumps({k: v for k, v in res.items() if k not in ("actions", "metrics")}))


if __name__ == "__main__":
    main()
