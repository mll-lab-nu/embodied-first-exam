"""Deterministic authoring generator for the drying_rack_unfold Sharpa trajectory (closed-loop scripted controller
reading Session state, recorded as open-loop rows quantized to float32).

  python tools/gen_oracle.py --params tools/oracle_params.json --out solution/trajectory.npz

Phases: (1) pinch the top half's end corner and swing it 180 deg about the pole hinge; (2) pinch each folded leg with
the low pinch and rotate it about its pivot onto the 100 deg stop; (3) pin-pinch the hinge collar at the middle of one
side rim, rotate the open rack about the opposite side rim over vertical (late wrist co-rotation keeps the rims off
the hand), follow the pivot onto the near feet and lower it level; (4) open, lift away, hold.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ctl import Kin, Kin2, Rax, Session, rot, smooth_rows  # noqa: E402


def generate(P, hand="sharpa"):
    s = Session(hand=hand)
    m, d = s.model, s.data
    rows = []

    def run(rs):
        for r in rs:
            r = np.clip(r, *m.actuator_ctrlrange.T).astype(np.float32).astype(np.float64)
            rows.append(r)
            s.step(r)
            if s.done:
                return False
        return True

    # ---- (1) unfold
    k = Kin(s)
    for _ in range(20):
        run([s.hold_action()])
    corner = d.geom_xpos[m.geom("moving_corner_l").id].copy()
    jid = m.joint("fold_hinge").id
    anchor = d.xanchor[jid].copy()
    YAW, SO, SC = np.pi / 2, 0.07, 0.035
    grip = corner + np.array([0, 0, 0.004])
    a = k.row(grip + [0, 0, 0.10], SO, YAW); run(smooth_rows(s.hold_action(), a, 60))
    b = k.row(grip, SO, YAW); run(smooth_rows(a, b, 40))
    c = k.row(grip, SC, YAW, wrist_sep=SO); run(smooth_rows(b, c, 30)); run([c] * 10)
    rel = grip - anchor
    r = np.hypot(rel[1], rel[2]); phi0 = np.arctan2(rel[2], -rel[1])
    prev = c
    for i in range(200):
        phi = phi0 + (np.pi - 2 * phi0) * 0.5 * (1 - np.cos(np.pi * (i + 1) / 200))
        p = np.array([grip[0], anchor[1] - r * np.cos(phi), anchor[2] + r * np.sin(phi)])
        prev = k.row(p, SC, YAW, wrist_sep=SO); run([prev])
    o = k.row(p, SO, YAW); run(smooth_rows(prev, o, 20))
    up = k.row(p + [0, 0, 0.12], SO, YAW); run(smooth_rows(o, up, 30)); run([up] * 50)
    # ---- (2) legs
    k2 = Kin2(s, HERE / "pinch_low.json")
    RHO, SEPC, SEPO = 0.07, 0.012, 0.05
    for leg in ("fixed_leg_l", "fixed_leg_r", "moving_leg_r", "moving_leg_l"):
        jid = m.joint(leg + "_hinge").id
        anchor = d.xanchor[jid].copy()
        foot = d.geom_xpos[m.geom(leg + "_foot").id].copy()
        u = foot - anchor; u[0] = 0; u /= np.linalg.norm(u)
        sgn = np.sign(u[1])
        R = rot(0, 0, k2.yaw_for([sgn, 0, 0]))
        grip = anchor + RHO * u
        cur = rows[-1]
        a = k2.row(grip + [0, 0, 0.06], SEPO, R, wrist_sep=SEPC); run(smooth_rows(cur, a, 50))
        b = k2.row(grip, SEPO, R, wrist_sep=SEPC); run(smooth_rows(a, b, 30))
        c = k2.row(grip, SEPC, R); run(smooth_rows(b, c, 20)); run([c] * 5)
        rel = grip - anchor; r0 = np.linalg.norm(rel[1:]); ang0 = np.arctan2(rel[2], sgn * rel[1])
        prev = c
        for i in range(70):
            q = np.deg2rad(100) * 0.5 * (1 - np.cos(np.pi * (i + 1) / 70))
            p = np.array([grip[0], anchor[1] + sgn * r0 * np.cos(ang0 + q), anchor[2] + r0 * np.sin(ang0 + q)])
            prev = k2.row(p, SEPC, R); run([prev])
        o = k2.row(p, SEPO, R, wrist_sep=SEPC); run(smooth_rows(prev, o, 15))
        up = k2.row(p + [0, sgn * 0.05, 0.05], SEPO, R, wrist_sep=SEPC); run(smooth_rows(o, up, 30))
        up2 = k2.row(p + [0, sgn * 0.05, 0.12], SEPO, R, wrist_sep=SEPC); run(smooth_rows(up, up2, 30))
        run([up2] * 15)
    # ---- (3) turn over
    cid = m.geom("fixed_hinge_r").id
    fl = [m.geom(n).id for n in ("fixed_leg_l_foot", "moving_leg_l_foot")]
    tipmid = lambda: (d.geom_xpos[m.geom("right_thumb_fingertip_collision").id]  # noqa: E731
                      + d.geom_xpos[m.geom("right_index_fingertip_collision").id]) / 2
    grip = d.geom_xpos[cid].copy() + np.array([-P["xoff"], 0, P["zoff"]])
    SO, SC = 0.06, P["sepc"]
    R0 = rot(0, 0, k2.yaw_for([0, 1, 0]))
    cur = rows[-1]
    a = k2.row(grip + [0, 0, 0.06], SO, R0, wrist_sep=SC); run(smooth_rows(cur, a, 60))
    b = k2.row(grip, SO, R0, wrist_sep=SC); run(smooth_rows(a, b, 30))
    c = k2.row(grip, SC, R0); run(smooth_rows(b, c, 20)); run([c] * 10)
    xs = d.geom_xpos[s.checker.rack_geom_ids]
    piv = np.array([xs[:, 0].max() + P["pivx"], 0, 0.75])
    rel = grip - piv; Rr = np.hypot(rel[0], rel[2]) + P["dr"]; th0 = np.arctan2(rel[2], -rel[0])
    TH1, TH2 = np.deg2rad(P["th1"]), np.deg2rad(175)

    def Rhand(th):
        a_ = np.clip(P["kappa"] * (th - th0 - np.deg2rad(P["phstart"])), 0, np.deg2rad(88))
        return Rax([0, 1, 0], float(a_)) @ R0

    prev = c; RH = R0
    for i in range(P["n1"]):
        th = th0 + (TH1 - th0) * 0.5 * (1 - np.cos(np.pi * (i + 1) / P["n1"]))
        p = np.array([piv[0] - Rr * np.cos(th), grip[1], piv[2] + Rr * np.sin(th)]); RH = Rhand(th)
        prev = k2.row(p, SC, RH); run([prev])
    for i in range(P["n2"]):
        th = TH1 + (TH2 - TH1) * (i + 1) / P["n2"]
        p = np.array([piv[0] - Rr * np.cos(th), grip[1], piv[2] + Rr * np.sin(th)]); RH = Rhand(th)
        prev = k2.row(p, SC, RH); run([prev])
        if sum(s.status()["feet_on_counter"]) >= 2:
            break
    F = d.geom_xpos[fl].mean(axis=0); F[2] -= 0.006
    A = d.geom_xpos[fl[1]] - d.geom_xpos[fl[0]]; A /= np.linalg.norm(A)
    if A[1] < 0:
        A = -A
    tilt0 = np.deg2rad(s.status()["tilt_deg"])
    pa0 = tipmid().copy(); sag = p - pa0
    N3 = P["n3"]
    for i in range(int(N3 * P["frac"])):
        w = 0.5 * (1 - np.cos(np.pi * (i + 1) / N3))
        p = F + Rax(A, tilt0 * w) @ (pa0 - F) + sag
        p[1] += P["dy3"] * w
        prev = k2.row(p, SC, RH); run([prev])
    # ---- (4) release and hold
    o = k2.row(p, SO, RH, wrist_sep=SC); run(smooth_rows(prev, o, P["nopen"]))
    up = k2.row(p + np.array([0, 0, 0.10]), SO, RH, wrist_sep=SC); run(smooth_rows(o, up, 40))
    for _ in range(200):
        if not run([up]):
            break
    status = s.status()
    # Slack: keep holding after the success row (the episode ends at success; extra rows are never executed).
    rows += [rows[-1]] * P.get("slack_rows", 100)
    return np.array(rows), status, s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default=str(HERE / "oracle_params.json"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    P = json.loads(Path(a.params).read_text())
    rows, st, s = generate(P)
    s.save_trajectory(rows, a.out)
    print(json.dumps({"rows": len(rows), "success": st["success"], "reason": st["reason"], "success_step": st["steps"],
                      "legs_deg": np.round(np.rad2deg(st["leg_angles_rad"]), 2).tolist()}))
