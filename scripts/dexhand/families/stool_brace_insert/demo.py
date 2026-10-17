"""Authoring controller (not shipped): closed-loop scripted Sharpa Wave episode, recorded as open-loop motor rows.

Phase 1 pinches the loose brace near one end, pivots it upright about its far dowel on the table, lifts it, carries it
over the empty lower-frame bore and lowers it (re-centring the dowel tip on the bore axis from the simulator state),
then opens the pinch. Phase 2 grips a crossrail of the opposite side frame with thumb + three fingers, lifts it,
carries it over the four upper dowels, aligns the frame pose to the lower frame (wrist corrections from the frame
state), lowers it onto the dowels, releases and withdraws. Only actuator targets are sent.
"""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation as Rot

from ctl import INDEX, MIDDLE, RING, THUMB, Ctl, rotate_about, rotation_between
from runtime import Session

RELEASE = "slide"  # brace release style: "slide" (open, slide +x, lift) or "lift" (open, lift straight up)


def near_geoms(session, owner, point, radius):
    m, d = session.model, session.data
    return [g for g in range(m.ngeom) if session.owner.get(int(m.geom_bodyid[g])) == owner and m.geom_contype[g]
            and np.linalg.norm(d.geom_xpos[g] - point) < radius]


def brace_phase(s, c, log):
    m, d = s.model, s.data
    origin = np.asarray(s.config["stage_origin"])
    bid = m.body("brace").id
    table = m.geom("table").id
    R0 = d.xmat[bid].reshape(3, 3)
    grip = d.xpos[bid] + R0 @ np.array([0, 0, -0.105])
    q0 = s.hold_action().copy()
    q0[0:3] = [grip[0] - 0.15, grip[1], grip[2] + 0.06]
    q0[0:3] -= origin
    var = [0, 1, 2] + THUMB + INDEX
    avoid = [m.geom("brace_pine").id]
    opened, k1 = c.pinch(q0, grip, [0, 1, 0], 0.015, 0.012, fingers=("index",), obstacles=[table], avoid=avoid,
                         variable=var)
    closed, k2 = c.pinch(opened, grip, [0, 1, 0], 0.015, -0.010, fingers=("index",), obstacles=[table], avoid=avoid,
                         variable=var)
    log("brace pinch ik", k1, k2)
    above = opened.copy()
    above[2] += 0.12
    c.execute(above, 60, "approach brace")
    c.execute(opened, 50, "descend to brace end")
    c.execute(closed, 40, "pinch brace end")
    c.execute(closed, 25, "stabilize pinch")
    W0 = origin + closed[0:3]
    r = grip - W0
    far = d.site("brace_tip_p").xpos.copy() + np.array([0, 0, 0.012])
    L = np.linalg.norm(grip - far)
    n = 12
    for k in range(1, n + 1):
        phi = np.pi / 2 * k / n
        G = far + L * np.array([-np.cos(phi), 0, np.sin(phi)])
        t = closed.copy()
        t[4] = phi
        t[0:3] = G - Rot.from_euler("y", phi).as_matrix() @ r - origin
        c.execute(t, 15, "pivot brace upright")
    c.execute(t, 30, "settle upright")
    lift = t.copy()
    lift[2] += 0.10
    c.execute(lift, 60, "lift brace")
    entry = d.site("lower_frame_leg_m_b0_entry").xpos.copy()

    def tip():
        return d.site("brace_tip_p").xpos.copy()

    goal = entry + np.array([0, 0, 0.025])
    t = lift.copy()
    t[0:3] += goal - tip()
    c.execute(t, 120, "carry brace over bore")
    for _ in range(4):
        # Make the hanging brace vertical: rotate the hand about the pinch point (closed loop on the brace axis).
        axis = d.xmat[bid].reshape(3, 3)[:, 2]
        pivot = d.xpos[bid] + d.xmat[bid].reshape(3, 3) @ np.array([0, 0, -0.105])
        t = rotate_about(t, origin, rotation_between(axis, [0, 0, -1]), pivot)
        c.execute(t, 30, "straighten brace")
        log("  axis", d.xmat[bid].reshape(3, 3)[:, 2].round(4).tolist())
    for _ in range(8):
        c.execute(t, 25, "align dowel over bore")
        e = goal - tip()
        log("  tip error", e.round(4).tolist(), "axis", d.xmat[bid].reshape(3, 3)[:, 2].round(3).tolist())
        t[0:3] += e
        if np.linalg.norm(e[0:2]) < 0.0008:
            break
    c.execute(t, 30, "align dowel over bore")
    for _ in range(8):
        e = entry - tip()
        t[0:2] += e[0:2]
        t[2] -= 0.006
        c.execute(t, 20, "insert lower dowel")
        log("  ends", s.status()["ends"]["brace_p"])
    c.execute(t, 30, "seat brace shoulder")
    th = d.geom_xpos[c.tip["thumb"]].copy()
    ix = d.geom_xpos[c.tip["index"]].copy()
    ax = th - ix
    ax[2] = 0
    rel, k3 = c.pinch(t, (th + ix) / 2, ax, 0.015, 0.016, fingers=("index",), avoid=avoid, variable=THUMB + INDEX,
                      weight_reg=0.003)
    log("  release ik", k3)
    c.execute(rel, 50, "open pinch")
    log("  hand contacts after opening", s.status()["hand_contact_parts"])
    if RELEASE == "slide":
        away = rel.copy()
        away[0] += 0.05
        c.execute(away, 40, "slide fingers off brace")
    else:
        away = rel.copy()
    up = away.copy()
    up[2] += 0.12
    c.execute(up, 80 if RELEASE != "slide" else 60, "withdraw from brace")
    c.execute(up, 30, "brace stands seated")
    return up


def ws_pose(t, origin):
    return np.asarray(origin) + t[0:3], Rot.from_euler("XYZ", t[3:6]).as_matrix()


def apply_body_error(t, origin, p_body, R_body, p_goal, R_goal, gain=1.0):
    """Shift the wrist targets by the rigid motion that takes the body pose to the goal pose (held object)."""
    R_err = R_goal @ R_body.T
    if gain != 1.0:
        R_err = Rot.from_rotvec(Rot.from_matrix(R_err).as_rotvec() * gain).as_matrix()
    p_err = p_body + gain * (p_goal - p_body) - R_err @ p_body
    W, R = ws_pose(t, origin)
    out = t.copy()
    out[0:3] = R_err @ W + p_err - origin
    out[3:6] = Rot.from_matrix(R_err @ R).as_euler("XYZ")
    return out


def kabsch(src, dst):
    cs, cd = src.mean(0), dst.mean(0)
    H = (src - cs).T @ (dst - cd)
    U, _S, Vt = np.linalg.svd(H)
    D = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))])
    R = Vt.T @ D @ U.T
    return R, cd - R @ cs


def frame_phase(s, c, log, up):
    m, d = s.model, s.data
    origin = np.asarray(s.config["stage_origin"])
    table = m.geom("table").id
    fb = m.body("upper_frame").id
    Rf = d.xmat[fb].reshape(3, 3)
    cr = d.xpos[fb] + Rf @ np.array([s.config["rail_stations"][0], 0, 0])
    avoid = near_geoms(s, "upper_frame", cr, 0.06)
    q0 = up.copy()
    q0[3:6] = 0
    q0[6:] = s.initial_targets[6:]
    q0[0:3] = np.array([cr[0] - 0.12, cr[1] - 0.01, cr[2] + 0.08]) - origin
    sp = {"index": (0, 0.022, 0), "middle": (0, 0.0, 0), "ring": (0, -0.022, 0)}
    var = [0, 1, 2] + THUMB + INDEX + MIDDLE + RING
    fo, k1 = c.pinch(q0, cr, [-1, 0, 0], 0.015, 0.012, fingers=("index", "middle", "ring"), spread=sp,
                     obstacles=[table], avoid=avoid, variable=var)
    fc, k2 = c.pinch(fo, cr, [-1, 0, 0], 0.015, -0.010, fingers=("index", "middle", "ring"), spread=sp,
                     obstacles=[table], avoid=avoid, variable=var)
    log("frame grip ik", k1, k2)
    hi = fo.copy()
    hi[2] = max(up[2], fo[2] + 0.15)
    mid = up.copy()
    mid[2] = hi[2]
    c.execute(mid, 40, "raise hand")
    c.execute(hi, 150, "travel to side frame")
    c.execute(fo, 70, "descend to crossrail")
    c.execute(fc, 50, "grip crossrail")
    c.execute(fc, 30, "stabilize grip")
    R_level = Rf.copy()  # carry the frame in its initial upside-down orientation

    def frame_pose():
        return d.xpos[fb].copy(), d.xmat[fb].reshape(3, 3).copy()

    def tilt_deg():
        return float(np.degrees(np.arccos(np.clip(-d.xmat[fb][8], -1, 1))))

    t = fc.copy()
    lift_goal = d.xpos[fb].copy() + np.array([0, 0, 0.35])
    for k in range(10):
        p, R = frame_pose()
        goal = p.copy()
        goal[2] = min(lift_goal[2], p[2] + 0.05)
        t = apply_body_error(t, origin, p, R, goal, R_level)
        c.execute(t, 35, "lift side frame level")
        log("  frame", d.xpos[fb].round(4).tolist(), "tilt", round(tilt_deg(), 2))
    # Target pose: bore entries over the four upper dowel tips (rigid fit), hovering then descending.
    lower_R = d.xmat[m.body("lower_frame").id].reshape(3, 3)
    R_nom = lower_R @ Rot.from_euler("x", np.pi).as_matrix()
    p_nom = d.xpos[m.body("lower_frame").id] + lower_R @ np.array([0, 0, 0.29])
    bores = [m.site(f"upper_frame_leg_{leg}_b{k}_entry").id for leg in ("m", "p") for k in range(2)]
    local = np.array([m.site_pos[sid] for sid in bores])
    tips = {}
    for name in ("brace", "rail_1", "rail_2", "rail_3"):
        a, b = d.site(f"{name}_tip_m").xpos.copy(), d.site(f"{name}_tip_p").xpos.copy()
        tips[name] = a if a[2] > b[2] else b

    def goal_pose(h):
        nominal = p_nom + (R_nom @ local.T).T
        dst = []
        for q in nominal:
            name = min(tips, key=lambda n: np.linalg.norm(tips[n][:2] - q[:2]))
            dst.append(tips[name] + np.array([0, 0, h]))
        R_g, p_g = kabsch(local, np.array(dst))
        return p_g, R_g

    p_g, R_g = goal_pose(0.035)
    log("  goal", p_g.round(4).tolist(), "nominal", p_nom.round(4).tolist())
    for k in range(10):
        p, R = frame_pose()
        step = p_g - p
        n = np.linalg.norm(step[:2])
        if n > 0.06:
            step[:2] *= 0.06 / n
        goal = p + step
        goal[2] = max(goal[2], p_g[2])
        t = apply_body_error(t, origin, p, R, goal, R_g if n < 0.1 else R_level)
        c.execute(t, 40, "carry side frame over dowels")
        log("  frame", d.xpos[fb].round(4).tolist(), "tilt", round(tilt_deg(), 2), "dist", round(float(n), 4))
    for k in range(4):
        p, R = frame_pose()
        t = apply_body_error(t, origin, p, R, p_g, R)  # position only; the carried frame is already level
        c.execute(t, 30, "align bores over dowels")
        log("  align err", (p_g - d.xpos[fb]).round(4).tolist(), "tilt", round(tilt_deg(), 3))
    for h in np.arange(0.030, -0.0201, -0.005):
        p, R = frame_pose()
        goal_p, _ = goal_pose(h)
        if h > 0.004:
            t = apply_body_error(t, origin, p, R, goal_p, R)
        else:
            t[2] -= 0.005
        c.execute(t, 30, "lower frame onto dowels")
        st = s.status()
        log("  h", round(float(h), 3), "frame", d.xpos[fb].round(4).tolist(), "seated", st["seated_interfaces"],
            "stage", st["stage"], st["reason"])
    c.execute(t, 30, "seat side frame")
    tips = {f: d.geom_xpos[c.tip[f]].copy() for f in ("thumb", "index", "middle", "ring")}
    fingers_c = (tips["index"] + tips["middle"] + tips["ring"]) / 3
    ax = tips["thumb"] - fingers_c
    ax[2] = 0
    sp2 = {f: tips[f] - fingers_c for f in ("index", "middle", "ring")}
    for f in sp2:
        sp2[f][2] = 0
    center = (tips["thumb"] + fingers_c) / 2
    rel, k3 = c.pinch(t, center, ax, 0.015, 0.016, fingers=("index", "middle", "ring"), spread=sp2,
                      avoid=near_geoms(s, "upper_frame", center, 0.06), variable=THUMB + INDEX + MIDDLE + RING,
                      weight_reg=0.003)
    log("  frame release ik", k3)
    c.execute(rel, 50, "open grip on frame")
    log("  hand contacts after opening", s.status()["hand_contact_parts"])
    up2 = rel.copy()
    up2[2] += 0.15
    c.execute(up2, 70, "withdraw hand")
    c.execute(up2, 80, "released hold")
    st = s.status()
    log("final", st["stage"], st["reason"], st["seated_interfaces"], st["released_hold_steps"], st["success"])
    return t


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--resume", help="pickle written by --checkpoint after the brace phase")
    parser.add_argument("--checkpoint")
    parser.add_argument("--stop", default="all", choices=["brace", "frame", "all"])
    parser.add_argument("--release", default="slide", choices=["slide", "lift"])
    args = parser.parse_args()
    global RELEASE
    RELEASE = args.release
    s = Session(hand="sharpa")
    c = Ctl(s)
    log = lambda *a, **k: print(*a, flush=True)
    if args.resume:
        blob = pickle.loads(Path(args.resume).read_bytes())
        s.replay(blob["actions"])
        c.target = blob["target"].copy()
        c.phases = list(blob["phases"])
        up = blob["up"]
        log("resumed", len(s.actions), s.status()["stage"], s.status()["reason"])
    else:
        up = brace_phase(s, c, log)
        if args.checkpoint:
            Path(args.checkpoint).write_bytes(pickle.dumps(
                {"actions": np.asarray(s.actions), "target": c.target, "phases": c.phases, "up": up}))
    if args.stop != "brace":
        frame_phase(s, c, log, up)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, actions=np.asarray(s.actions), phases=np.asarray(c.phases))
    st = s.status()
    log(json.dumps({k: st[k] for k in ("stage", "reason", "success", "steps", "seated_interfaces")}))


if __name__ == "__main__":
    main()
