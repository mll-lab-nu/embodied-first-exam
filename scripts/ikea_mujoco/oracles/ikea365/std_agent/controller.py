#!/usr/bin/env python3
"""Closed-loop reference of IKEA MuJoCo ikea365 (the final physics: prisms, EPA-patched MuJoCo, arm joint-speed clamp).

The original demo is the phase guide; its rows are used where they work, and the robot's actions are corrected where
the prism physics needs it (never the task, the physics, rcb_ikea or the grader):
  A  demo rows (as the clamp executes them) up to the screw return: remove, park, cross, return (gates 1-4).
  B  the right hand still holds the returned screw on its thread entry: it threads it K turns (right joint 7 at W rad/s,
     the TCP lowered by the pitch per turn by Jacobian IK), so the screw stands upright engaged instead of tipping over
     on release (under prisms it fell to ~9 deg tilt and the screwdriver could not engage it).
  C  demo rows again, the right arm offset by what B did (joint 7: K full turns, kept; joints 1-6: blended out after the
     hand has opened), until the demo's screwdriver spin.
  D  the screwdriver spin, closed loop: left joint 7 at W rad/s while the TCP descends until the screwdriver bears on
     the screw head with F_LO..F_HI N, until the mechanism accepts reinstall_same_screw (seated, welds on), then a short
     hold and a lift.
  E  demo rows from the end of the demo's spin to the end (turn the stand, place the bowl), the left arm blended back
     onto them (joint 7 by whole turns), the right arm offset as in C.
Every recorded row is the target the clamp applied (data.ctrl after Session.applied), so the rows are within the
joint-speed limits and replay 1:1 in both modes.

usage: controller.py --demo <original demo npz> --out <reference npz> [--k 7 --w 2.5 ...]   (inside the IKEA image)"""
from __future__ import annotations
import argparse, json, math, os, sys, time
import numpy as np
import mujoco

ap = argparse.ArgumentParser()
ap.add_argument("--demo", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--rcb-ikea", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
ap.add_argument("--t-thread", type=float, default=103.0, help="B starts here (s of the demo)")
ap.add_argument("--k", type=float, default=7.0, help="B: turns threaded by the right hand")
ap.add_argument("--w", type=float, default=2.5, help="B/D: joint 7 spin (rad/s)")
ap.add_argument("--blend", type=float, default=1.0, help="C/E: offset blend time (s)")
ap.add_argument("--f-lo", type=float, default=5.0); ap.add_argument("--f-hi", type=float, default=15.0)
ap.add_argument("--dz", type=float, default=2e-6, help="D: descent per control step while the screwdriver force is low (m)")
ap.add_argument("--d-max", type=float, default=60.0, help="D: give up after this long (s)")
ap.add_argument("--lift", type=float, default=0.004, help="D: lift after seating (m)")
ap.add_argument("--save-c", default=None, help="pickle the state after C here (development)")
ap.add_argument("--resume-c", default=None, help="start at D from a --save-c pickle (development)")
a = ap.parse_args()
import pickle
sys.path.insert(0, os.path.abspath(a.rcb_ikea))
import rcb_ikea as R

s = R.Session("ikea365"); m, d = s.model, s.data; M = s.S.mech
dt = s.control_dt
demo = R.load_trajectory(a.demo, s.nu, s.timestep)
L, Rr = list(range(0, 7)), list(range(8, 15))          # arm columns; 7, 15 the hands
sid = m.body("same_screw").id; sdid = m.body("screwdriver").id
tcp = {"left": m.site("left_tcp").id, "right": m.site("right_tcp").id}
dof = {arm: [int(m.jnt_dofadr[m.joint(f"{arm}_joint{k}").id]) for k in range(1, 8)] for arm in ("left", "right")}
rows: list = []
t0 = time.time()


def step(row):
    s.step(np.asarray(row, dtype=np.float64))
    rows.append(d.ctrl.copy())                          # what the clamp applied: the recorded reference row


def ik_move(arm, dx):
    """Joint 1-6 deltas that move the arm's TCP by dx (3, world) with its orientation kept (first order)."""
    jp = np.zeros((3, m.nv)); jr = np.zeros((3, m.nv)); mujoco.mj_jacSite(m, d, jp, jr, tcp[arm])
    J = np.vstack([jp, jr])[:, dof[arm][:6]]
    return np.linalg.lstsq(J, np.r_[dx, 0, 0, 0], rcond=None)[0]


def ik_dz(arm, dz):
    return ik_move(arm, np.array([0, 0, dz]))


def tip_offset():
    """The screwdriver tip's offset from the screw axis line (world, horizontal part) and its height above the head top."""
    ps = d.xpos[sdid]; pw = d.xpos[sid]; Rw = d.xmat[sid].reshape(3, 3)
    head = pw + Rw @ np.array([0, 0, 0.01875]); ax = Rw[:, 2]
    v = ps - head; lat = v - np.dot(v, ax) * ax
    return lat, float(np.dot(v, ax))


def fbody(b1, b2):
    n = d.ncon
    if not n:
        return 0.0
    gb = m.geom_bodyid; c = d.contact
    x, y = gb[c.geom1[:n]], gb[c.geom2[:n]]
    sel = ((x == b1) & (y == b2)) | ((x == b2) & (y == b1))
    adr = c.efc_address[:n][sel]
    return float(np.abs(d.efc_force[adr[adr >= 0]]).sum())


def touches():
    """Robot-part contact pairs with their normal force (N)."""
    out = {}
    for k in range(d.ncon):
        c = d.contact[k]; b1, b2 = m.body(m.geom_bodyid[c.geom1]).name, m.body(m.geom_bodyid[c.geom2]).name
        if b1.startswith(("left_", "right_")) != b2.startswith(("left_", "right_")):
            f = np.zeros(6); mujoco.mj_contactForce(m, d, k, f)
            key = "/".join(sorted((b1, b2))); out[key] = round(out.get(key, 0) + abs(float(f[0])), 2)
    return out


def gate(tag):
    p, q, sp = M.rel("same_screw"); Rw = d.xmat[sid].reshape(3, 3)
    print(json.dumps({"phase": tag, "t": round(float(d.time), 3), "rows": len(rows), "accepted": M.accepted(),
                      "gap_mm": round(1000 * (p[2] - M.screw_rel[2]), 3), "tilt_deg": round(math.degrees(math.acos(min(1, abs(Rw[2, 2])))), 3),
                      "turns": round(M.op.get("turns", 0.0), 3), "wall_s": round(time.time() - t0, 1),
                      "a_mm": [round(1000 * float(x), 2) for x in d.xpos[m.body("member_a").id]],
                      "b_mm": [round(1000 * float(x), 2) for x in d.xpos[m.body("member_b").id]]}), flush=True)


iB = int(round(a.t_thread / dt))
for r in ([] if a.resume_c else demo[:iB]):
    step(r)
if not a.resume_c:
    gate("A")
# ---- the demo's screwdriver spin: the left joint 7 runs fast between these rows
j7 = demo[:, 6]; dj = np.diff(j7)
fast = np.abs(dj[iB:int(170 / dt)]) > 0.003                  # the spin: the longest run of fast joint-7 rows
best, run, start = (0, 0, 0), 0, 0
for k, v in enumerate(fast):
    if v:
        run = run + 1 if run else 1; start = k if run == 1 else start
        if run > best[0]:
            best = (run, start, k)
    else:
        run = 0
iS, iE = iB + best[1], iB + best[2] + 1
iRel = iB + int(np.flatnonzero(demo[iB:, 15] > 100)[0])  # the right hand opens (the demo's release of the screw)
print(json.dumps({"spin_rows": [iS, iE], "spin_t": [round(iS * dt, 3), round(iE * dt, 3)], "right_release_t": round(iRel * dt, 3)}), flush=True)


def offset_right(i, t_since_rel):
    """C/E: the right arm's offset at demo row i: joint 7 whole turns kept, joints 1-6 blended out after the release."""
    o = off_r.copy()
    if i >= iRel:
        f = max(0.0, 1.0 - max(0.0, t_since_rel - 0.3) / a.blend)
        o[:6] *= f
    return o


if not a.resume_c:
    # ---- B: thread with the right hand
    cmd = d.ctrl.copy()
    n = int(round(a.k * 2 * math.pi / (a.w * dt)))
    for k in range(n):
        cmd[8:14] += ik_dz("right", -0.0005 * a.w * dt / (2 * math.pi)); cmd[14] += a.w * dt
        step(cmd)
    for _ in range(int(round(0.3 / dt))):
        step(cmd)
    gate("B")
    off_r = cmd[Rr] - demo[iB - 1][Rr]                     # the right arm's offset from the demo
    off_r7 = off_r[6]
    # ---- C
    for i in range(iB, iS):
        r = demo[i].copy(); r[Rr] += offset_right(i, (i - iRel) * dt)
        step(r)
    gate("C")
    if a.save_c:
        pickle.dump(dict(state=s.get_state(), rows=rows, off_r=off_r, iS=iS, iE=iE, iRel=iRel, iB=iB), open(a.save_c, "wb"))
if a.resume_c:
    P = pickle.load(open(a.resume_c, "rb")); s.set_state(P["state"]); rows = list(P["rows"])
    off_r, iS, iE, iRel, iB = P["off_r"], P["iS"], P["iE"], P["iRel"], P["iB"]
    gate("C (resumed)")
# ---- D: closed-loop spin: centre the screwdriver over the screw axis, then descend and spin
cmd = d.ctrl.copy(); seated_at = None; t_d = 0.0
lat, h = tip_offset()
print(json.dumps({"D_start_tip_lateral_mm": [round(1000 * x, 3) for x in lat], "tip_above_head_mm": round(1000 * h, 3)}), flush=True)
if h < 0.003:                                           # first lift clear of the head, so it can be centred
    nl = int(round(0.3 / dt))
    for _ in range(nl):
        cmd[0:6] += ik_dz("left", (0.003 - h) / nl); step(cmd)
for _ in range(3):                                      # centre (closed loop on the true tip offset)
    lat, h = tip_offset(); nl = int(round(0.3 / dt))
    for _ in range(nl):
        cmd[0:6] += ik_move("left", -lat / nl); step(cmd)
    for _ in range(int(round(0.2 / dt))):
        step(cmd)
lat, h = tip_offset()
print(json.dumps({"D_centred_tip_lateral_mm": [round(1000 * x, 3) for x in lat], "tip_above_head_mm": round(1000 * h, 3)}), flush=True)
while t_d < a.d_max:
    f = fbody(sdid, sid)
    if f < a.f_lo:
        cmd[0:6] += ik_dz("left", -a.dz)
    elif f > a.f_hi:
        cmd[0:6] += ik_dz("left", +a.dz)
    if int(t_d / dt) % 40 == 0:                         # keep centred while turning
        lat, h = tip_offset(); cmd[0:6] += ik_move("left", -0.2 * lat)
    cmd[6] += a.w * dt
    step(cmd); t_d += dt
    if "reinstall_same_screw" in M.accepted():
        seated_at = t_d; break
    if int(t_d / dt) % int(round(2.0 / dt)) == 0:
        gate(f"D {t_d:.0f}s F {f:.1f}")
gate("D seated" if seated_at is not None else "D FAILED")
if seated_at is None:
    sys.exit(2)
for _ in range(int(round(0.3 / dt))):
    step(cmd)
nl = int(round(0.5 / dt))
for _ in range(nl):
    cmd[0:6] += ik_dz("left", a.lift / nl); step(cmd)
gate("D lifted")
# ---- E: back onto the demo from the end of its spin
off_l = cmd[L] - demo[iE][L]
off_l7 = 2 * math.pi * round(off_l[6] / (2 * math.pi))
start = len(rows)
for i in range(iE, len(demo)):
    te = (len(rows) - start) * dt
    f = max(0.0, 1.0 - te / a.blend)
    r = demo[i].copy()
    ol = off_l * f; ol[6] = off_l7 + (off_l[6] - off_l7) * f
    r[L] += ol; r[Rr] += offset_right(i, (i - iRel) * dt)
    step(r)
    if (i - iE) % int(round(2.0 / dt)) == 0:
        pa = d.xpos[m.body("member_a").id]; up = d.xmat[m.body("member_a").id].reshape(3, 3)[2, 2]
        print(json.dumps({"E_demo_t": round(i * dt, 2), "next": M.ops[M.next] if not M.complete else "done",
                          "member_a_z": round(float(pa[2]), 4), "up_z": round(float(up), 3), "op": {k: (round(v, 5) if isinstance(v, float) else None) for k, v in M.op.items() if k in ("drift", "deg", "start_z")},
                          "hands": [round(float(d.ctrl[7]), 1), round(float(d.ctrl[15]), 1)], "touch": touches(), "rtcp": [round(float(x), 4) for x in d.site_xpos[tcp["right"]]], "ltcp": [round(float(x), 4) for x in d.site_xpos[tcp["left"]]],
                          "a": [round(float(x), 4) for x in d.xpos[m.body("member_a").id]], "b": [round(float(x), 4) for x in d.xpos[m.body("member_b").id]],
                          "dq_r": [round(float(x), 4) for x in (d.ctrl[8:15] - demo[i][8:15])],
                          "sd": [round(float(x), 3) for x in d.xpos[sdid]]}), flush=True)
gate("E")
fc = s.final_check()
out = np.array(rows)
full = np.vstack([np.asarray(R.Session.__dict__ and demo[:0])] if False else [out])
arm = [j for j in range(s.nu) if j not in (7, 15)]
prev = np.vstack([s.step_limit[None] * 0 + rows[0][None]]) if False else None
s.save_trajectory(out, a.out)
print(json.dumps({"final_check": fc["success"], "end": {k: fc["end"][k] for k in ("goal", "released", "at_rest", "breakdown")},
                  "settled": {k: fc["settled"][k] for k in ("goal", "released", "at_rest", "breakdown")},
                  "state_sha": fc["state_sha"], "settled_sha": fc["settled_sha"], "rows": len(out), "out": a.out,
                  "wall_s": round(time.time() - t0, 1)}), flush=True)
