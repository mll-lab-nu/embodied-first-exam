"""policy_fingerprint.py: did a joint-level seat drive its robots with the released Booster walking policy? (SOCJV3
2026-10-14; the action-fingerprint check of the rule "no walking or balancing policy you did not build", needed now
that the GPU seat holds the policy file for the GPU opponents.)

Replays the match from its episode.jsonl (core.episode.replay: the service's own deterministic fresh-process replay)
and, for a sample of the seat's joint commands, asks how close the released policy could have come to the row the
seat actually sent, from the state the robot was in when the row took effect:

    row_hat(c, phase) = default + action_scale * policy(obs(state, command c, gait phase, last action))

with the policy's last action taken from the seat's own previous row ((prev_row - default) / action_scale, as a seat
that ran the policy would have it), and the free inputs (the velocity command c and the gait phase) fitted per sample
(a grid, then gradient steps through the TorchScript network). A seat that ran the policy, even with its own
commands, has a fitted error near zero on most samples; any other controller does not (the network maps a 47-number
state to 12 targets: three free command numbers and a phase cannot fit arbitrary rows). The report gives the
distribution of the fitted RMS error (rad) per robot and the share of samples below a threshold (FLAG_RAD).

    python3 policy_fingerprint.py EPISODE.jsonl SIM_DIR [--every 10] [--seat A] [--max 600] [--out OUT.json]
(SIM_DIR = the task's environment/sim, with core/ and sport/; needs torch, mujoco 3.3.7: the soccer image.)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

FLAG_RAD = 0.02


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("sim")
    ap.add_argument("--every", type=int, default=10)
    ap.add_argument("--seat", default="A")
    ap.add_argument("--max", type=int, default=600)
    ap.add_argument("--iters", type=int, default=150)
    ap.add_argument("--out", default=None)
    ap.add_argument("--selftest", type=int, default=0, help="positive control: N steps of team A on the released policy")
    a = ap.parse_args()
    sys.path[:0] = [a.sim, os.path.join(a.sim, "sport")]
    import torch
    from core.episode import load_plugin, read_rows, replay
    sport = load_plugin(os.path.join(a.sim, "sport", "plugin.py"))
    import soccer as S
    rows = read_rows(a.episode) if not a.selftest else []
    samples = []
    prev = {}
    team = a.seat[0]

    def on_cmd(match, row, info):
        cmd = row.get("cmd") or {}
        if row.get("seat") != a.seat or cmd.get("type") != "joints":
            return
        robot = team + str(cmd.get("entity"))
        q = np.asarray(cmd["q"], np.float32)
        p = prev.get(robot)
        prev[robot] = q
        k = int(row["k"])
        if p is None or k % a.every or len([s for s in samples if s["robot"] == robot]) >= a.max:
            return
        w = match.w
        r = w.rob[robot]
        d = w.d
        samples.append(dict(robot=robot, k=k, q=q, prev=p, dq=d.qpos[r.jq].astype(np.float32),
                            dv=d.qvel[r.jv].astype(np.float32),
                            quat=d.sensordata[r.s_quat:r.s_quat + 4][[1, 2, 3, 0]].astype(np.float32),
                            gyro=d.sensordata[r.s_gyro:r.s_gyro + 3].astype(np.float32)))

    if a.selftest:          # positive control: team A driven by the released policy through joint rows
        from core.sport import MatchConfig
        cfg = MatchConfig(sport="soccer", format="single", seats=("A",), seed=7, first="A", level=1, action_level="low")
        m = sport.build(cfg)
        layer = sport.action_layer("low")
        drv = S.Policy(n=2)
        rng = np.random.default_rng(0)
        cmds = np.zeros((2, 3))
        for k in range(a.selftest):
            if m.w.stopped:
                m.resume()
            if m.w.done:
                break
            if k % 100 == 0:
                cmds = rng.uniform([-0.3, -0.3, -0.8], [0.8, 0.3, 0.8], (2, 3))
            w = m.w
            rs = [w.rob["A1"], w.rob["A2"]]
            drv.infer(cmds, [w.d.qpos[r.jq].astype(np.float32) for r in rs], [w.d.qvel[r.jv].astype(np.float32) for r in rs],
                      [w.d.sensordata[r.s_quat:r.s_quat + 4][[1, 2, 3, 0]].astype(np.float32) for r in rs],
                      [w.d.sensordata[r.s_gyro:r.s_gyro + 3].astype(np.float32) for r in rs])
            for _ in range(10):
                drv.advance_gait()
            tg = drv.targets()
            for i, ent in enumerate(("1", "2")):
                if w.fallen["A" + ent] is not None or w.penalty["A" + ent] is not None:
                    continue
                row = dict(ev="cmd", k=w.k, seat="A", cmd={"type": "joints", "q": tg[i].tolist(), "entity": ent})
                on_cmd(m, row, None)
                m.apply("A", layer.parse("A", row["cmd"], m, {}))
            m.step()
    else:
        replay(sport, rows, on_cmd=on_cmd)
    pol = S.Policy(n=1)
    nrm, scale = pol.nrm, float(pol.cfg["control"]["action_scale"])
    default = torch.tensor(pol.default)
    n = len(samples)
    if n == 0:
        print(json.dumps({"samples": 0}))
        return
    base = np.zeros((n, 47), np.float32)
    for i, s in enumerate(samples):
        base[i, 0:3] = S.Policy._rot_inv(s["quat"], np.array([0.0, 0.0, -1.0])) * nrm["gravity"]
        base[i, 3:6] = s["gyro"] * nrm["ang_vel"]
        base[i, 11:23] = (s["dq"] - pol.default) * nrm["dof_pos"]
        base[i, 23:35] = s["dv"] * nrm["dof_vel"]
        base[i, 35:47] = np.clip((s["prev"] - pol.default) / scale, -nrm["clip_actions"], nrm["clip_actions"])
    base = torch.tensor(base)
    target = torch.tensor(np.stack([s["q"] for s in samples]))
    model = pol.model

    def predict(cmd, ph):
        o = base.clone()
        o[:, 6] = cmd[:, 0] * nrm["lin_vel"]
        o[:, 7] = cmd[:, 1] * nrm["lin_vel"]
        o[:, 8] = cmd[:, 2] * nrm["ang_vel"]
        o[:, 9] = torch.cos(2 * np.pi * ph)
        o[:, 10] = torch.sin(2 * np.pi * ph)
        act = model(o).clamp(-nrm["clip_actions"], nrm["clip_actions"])
        return default + scale * act

    def err(cmd, ph):
        return ((predict(cmd, ph) - target) ** 2).mean(-1).sqrt()

    best = torch.full((n,), 1e9)
    bc, bp = torch.zeros(n, 3), torch.zeros(n)
    with torch.no_grad():
        for vx in np.linspace(-1, 1, 5):
            for vy in np.linspace(-0.6, 0.6, 3):
                for wz in np.linspace(-1, 1, 5):
                    for ph in np.linspace(0, 1, 8, endpoint=False):
                        c = torch.tensor([vx, vy, wz], dtype=torch.float32).repeat(n, 1)
                        p = torch.full((n,), float(ph))
                        e = err(c, p)
                        m = e < best
                        best = torch.where(m, e, best)
                        bc[m], bp[m] = c[m], p[m]
    cmd = bc.clone().requires_grad_(True)
    ph = bp.clone().requires_grad_(True)
    opt = torch.optim.Adam([cmd, ph], lr=0.02)
    for _ in range(a.iters):
        opt.zero_grad()
        e = err(cmd, ph)
        e.sum().backward()
        opt.step()
    with torch.no_grad():
        fit = torch.minimum(err(cmd, ph), best).numpy()
    out = {"episode": a.episode, "seat": a.seat, "every": a.every, "flag_rad": FLAG_RAD, "robots": {}}
    for robot in sorted({s["robot"] for s in samples}):
        idx = [i for i, s in enumerate(samples) if s["robot"] == robot]
        e = fit[idx]
        out["robots"][robot] = dict(samples=len(idx), median_rad=round(float(np.median(e)), 4),
                                    p10_rad=round(float(np.percentile(e, 10)), 4),
                                    share_below_flag=round(float(np.mean(e < FLAG_RAD)), 3))
    out["flag"] = any(v["share_below_flag"] > 0.5 for v in out["robots"].values())
    print(json.dumps(out))
    if a.out:
        json.dump(out, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
