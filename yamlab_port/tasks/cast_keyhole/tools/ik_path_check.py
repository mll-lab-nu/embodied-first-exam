"""Offline IK feasibility of the oracle's nominal TCP paths (design v4) from a logged settled state.

usage: python ik_path_check.py <tier> <states.npz> <step> [json params]
For each arm and jaw sign: multi-start seeds at the grasp; IK-tracks the nominal path
(pregrasp -> grasp -> lift -> setup -> turn -> channel) and reports per phase the fails and min joint margin.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyhole_geometry as kg
import plan2 as pl
import yam_kin as yk
from layout import Scene, T_from, TABLE_Z

tier, path, k = sys.argv[1], sys.argv[2], int(sys.argv[3])
P = dict(gold_y=-0.004, gold_x_tcp=0.061, silver_y=-0.0024, silver_x_tcp=-0.051, work_bar=[0.50, -0.07],
         h_bar=0.0405, split=0.5, lift=0.02, chan_extra=0.04, pre_back=0.06)
if len(sys.argv) > 4:
    P.update(json.loads(sys.argv[4]))
sc = Scene(tier)
REL = pl.Relative(sc.record, tier)
z = np.load(path)
Tp = {}
for n in kg.NAMES:
    st = z[f"keyhole_{n}"][k]
    Tp[n] = T_from(Rotation.from_quat(st[[4, 5, 6, 3]]), st[:3]) @ sc.T_part_plate[n]


def tr(T, d):
    o = T.copy(); o[:3, 3] += d; return o


# nominal object path
frames = []
Tg0, Ts0 = Tp["gold"], Tp["silver"]
for u in np.linspace(0, 1, 6):
    frames.append(("lift", tr(Tg0, [0, 0, P["lift"] * u]), tr(Ts0, [0, 0, P["lift"] * u])))
Tg2, Ts2 = frames[-1][1], frames[-1][2]
R_lv = Rotation.align_vectors([[0, 0, -1.0]], [Tg2[:3, 2]])[0].as_matrix()
bar2 = Tg2[:3, :3] @ REL.c0 + Tg2[:3, 3]
Tg_goal = pl.rot_about(Tg2, R_lv, bar2)
Tg_goal[:3, 3] += np.r_[P["work_bar"][0], P["work_bar"][1], TABLE_Z + P["h_bar"]] - bar2
align = REL.align(Tg2, Ts2)
for u in np.linspace(0, 1, 30)[1:]:
    Tg = pl.interp_T(Tg2, Tg_goal, u)
    frames.append(("setup", Tg, Tg @ align(u)))
f_turn, _ = REL.sampler(REL.stage("turn"))
for u in np.linspace(0, 1, 30)[1:]:
    frames.append(("turn", Tg_goal, Tg_goal @ f_turn(u)))
f_ch, _ = REL.sampler(REL.stage("channel"), extra=np.array([0.0, -P["chan_extra"], 0.0]))
rel0 = f_ch(0.0)
for u in np.linspace(0, 1, 60)[1:]:
    rel = f_ch(u)
    d = Tg_goal[:3, :3] @ (rel[:3, 3] - rel0[:3, 3])
    Tg = tr(Tg_goal, -P["split"] * d)
    frames.append(("channel", Tg, Tg @ rel))

rng = np.random.default_rng(0)
out = {}
for n, side, mk in (("gold", "left", lambda j: pl.gold_grasp(P["gold_y"], P["gold_x_tcp"], j)),
                    ("silver", "right", lambda j: pl.silver_edge_grasp(P["silver_y"], P["silver_x_tcp"], j))):
    for jaw in (1.0, -1.0):
        G = mk(jaw)
        idx = 1 if n == "gold" else 2
        T0 = frames[0][idx] @ G
        pre = T0.copy(); pre[:3, 3] -= P["pre_back"] * T0[:3, 0]
        path_T = [("pre", pre)] + [("approach", pl.interp_T(pre, T0, u)) for u in np.linspace(0, 1, 8)[1:]] + \
                 [(fr[0], fr[idx] @ G) for fr in frames]
        best = None
        for trial in range(60):
            q0 = yk.LOWER + rng.random(6) * (yk.UPPER - yk.LOWER)
            q, ok, _, _ = yk.ik(yk.world_to_base(pre, side), q0, iters=150)
            if not ok:
                continue
            res, qc, worst = {}, q, np.inf
            for ph, T in path_T:
                qn, ok, ep, er = yk.ik(yk.world_to_base(T, side), qc, iters=80, margin=0.0)
                m = float(np.min(np.minimum(qn - yk.LOWER, yk.UPPER - qn)))
                jump = float(np.abs(qn - qc).max())
                r = res.setdefault(ph, [0, np.inf, 0.0])
                r[0] += (not ok); r[1] = min(r[1], m); r[2] = max(r[2], jump)
                qc = qn
            score = (-sum(v[0] for v in res.values()), min(v[1] for v in res.values()))
            if best is None or score > best[0]:
                best = (score, {ph: [v[0], round(v[1], 3), round(v[2], 3)] for ph, v in res.items()}, q.round(3).tolist())
        out[f"{n}_jaw{jaw:+.0f}"] = None if best is None else dict(fails_minmargin=best[0], phases=best[1], seed=best[2])
        print(f"{n} jaw {jaw:+.0f}:", json.dumps(out[f"{n}_jaw{jaw:+.0f}"]), flush=True)
