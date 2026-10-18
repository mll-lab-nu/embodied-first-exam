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
LAGS = 4                 # #328 review: the row may answer a state up to LAGS - 1 control steps old


def seat_won(episode: str, seat: str) -> bool:
    """robot_coding_bench (board 0151: the standard modes are graded by the live match, no replay to grade it): the audit
    can only take a win away (tests/fexam_reward.py), so it replays the match only when the live verdict in final.json
    (next to episode.jsonl) is a win of the seat's side; an unreadable final.json is audited as a win."""
    try:
        d = json.loads(open(os.path.join(os.path.dirname(os.path.abspath(episode)), "final.json")).read())
        return d.get("match_winner") == (d.get("sides") or {}).get(seat, seat)
    except Exception:  # noqa: BLE001
        return True


def replay_agrees(episode: str, res: dict):
    """robot_coding_bench (#328 review): the audit's replay reproduces the live match final.json recorded (state digest,
    scores, winner, steps); False: its samples are not the live match's (tests/fexam_reward.py: the audit is missing);
    None: no final.json to compare with."""
    try:
        d = json.loads(open(os.path.join(os.path.dirname(os.path.abspath(episode)), "final.json")).read())
    except Exception:  # noqa: BLE001
        return None
    return bool(res.get("state_sha") == d.get("state_sha") and res.get("scores") == d.get("scores")
                and res.get("winner") == d.get("match_winner") and res.get("k") == d.get("steps"))


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
    ap.add_argument("--selftest-type", choices=("joints", "traj"), default="joints",
                    help="the positive control's command type (traj: one-row plans)")
    ap.add_argument("--selftest-lag", type=int, default=0, help="the positive control answers states this many steps old")
    ap.add_argument("--always", action="store_true", help="audit even when the seat did not win the live match")
    a = ap.parse_args()
    if not a.selftest and not a.always and not seat_won(a.episode, a.seat):
        print(json.dumps({"skipped": f"seat {a.seat} did not win the live match: nothing to audit (no replay)"}))
        return
    sys.path[:0] = [a.sim, os.path.join(a.sim, "sport")]
    import torch
    from core.episode import load_plugin, read_rows, replay
    sport = load_plugin(os.path.join(a.sim, "sport", "plugin.py"))
    import soccer as S
    rows = read_rows(a.episode) if not a.selftest else []
    samples = []
    hist = {}            # robot -> [(control step, its state, the row it asked for at that step)], the last LAGS + 1
    team = a.seat[0]
    mine = (team + "1", team + "2")

    def requested(w, n):
        """The row robot n asked for at this control step, before the world's limiter: the current row of its plan (a
        `joints` act is a one-row plan, soccer.World._set_prog), non-finite entries keeping the row in effect, or the
        row it holds when no plan row applies."""
        row = np.asarray(w.jrow[n], np.float32)
        plan = w.jplan.get(n)
        if plan is not None:
            k0, rr = plan
            j = min(w.k - k0, len(rr) - 1)
            if j >= 0:
                return np.where(np.isfinite(rr[j]), rr[j], row).astype(np.float32)
        return row

    def pre_step(match):
        """robot_coding_bench (#328 review): every control step, after the commands of the step took effect and before
        the world steps, the state the row meets and the row each of the seat's robots asked for, whatever command
        produced it (`joints`, `traj`, `hold`); the earlier sampler saw `joints` command rows only, so a program on
        `traj` plans was never audited (and its win voided for want of samples). A fallen or penalized robot, or one
        the referee holds after a placement, is not sampled and its history restarts (its rows do not act, or it was
        moved). A sample keeps the states of its last LAGS steps (the previous row as the last action): a program that runs the
        policy on a state one or more steps old (a late answer, a plan from k0 = s + 1) is fitted at its lag."""
        w = match.w
        k = int(w.k)
        for n in mine:
            if n not in w.jrow:
                continue
            held = w.held.get(n)
            if w.fallen.get(n) is not None or w.penalty.get(n) is not None or (held is not None and k < held):
                hist.pop(n, None)
                continue
            r = w.rob[n]
            d = w.d
            st = dict(dq=d.qpos[r.jq].astype(np.float32), dv=d.qvel[r.jv].astype(np.float32),
                      quat=d.sensordata[r.s_quat:r.s_quat + 4][[1, 2, 3, 0]].astype(np.float32),
                      gyro=d.sensordata[r.s_gyro:r.s_gyro + 3].astype(np.float32))
            h = [e for e in hist.get(n, []) if e[0] != k][-LAGS:]   # a stoppage: the same step again
            if h and h[-1][0] != k - 1:
                h = []
            h.append((k, st, requested(w, n)))
            hist[n] = h
            if k % a.every:
                continue
            # lag L: the row asked at k answers the state of step k - L; the policy's last action is still the row asked
            # at k - 1 (its previous output)
            lags = [dict(lag=lag, prev=h[-2][2], **h[-1 - lag][1]) for lag in range(LAGS) if len(h) >= max(2, lag + 1)]
            if lags:
                samples.append(dict(robot=n, k=k, q=h[-1][2], lags=lags))

    def instrument(match):
        """core.episode.replay's observer (called first with the new match): wrap its step() with pre_step."""
        if getattr(match, "_fp_wrapped", False):
            return
        step = match.step

        def wrapped(*args, **kw):
            pre_step(match)
            return step(*args, **kw)
        match.step = wrapped
        match._fp_wrapped = True

    if a.selftest:          # positive control: team A driven by the released policy through joint rows
        from core.sport import MatchConfig
        cfg = MatchConfig(sport="soccer", format="single", seats=("A",), seed=7, first="A", level=1, action_level="low")
        m = sport.build(cfg)
        instrument(m)
        layer = sport.action_layer("low")
        drv = S.Policy(n=2)
        rng = np.random.default_rng(0)
        cmds = np.zeros((2, 3))
        queue = []
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
            queue.append(tg.copy())
            tg = queue.pop(0) if len(queue) > a.selftest_lag else None
            if tg is None:
                m.step()
                continue
            for i, ent in enumerate(("1", "2")):
                if w.fallen["A" + ent] is not None or w.penalty["A" + ent] is not None:
                    continue
                c = {"type": "joints", "q": tg[i].tolist(), "entity": ent} if a.selftest_type == "joints" else \
                    {"type": "traj", "k0": int(w.k), "q": [tg[i].tolist()], "entity": ent}
                m.apply("A", layer.parse("A", c, m, {}))
            m.step()
        agrees = None
    else:
        res = replay(sport, rows, observer=instrument)
        agrees = replay_agrees(a.episode, res)
    keep = []                # at most --max samples per robot, spread evenly over the whole match
    for n in sorted({s["robot"] for s in samples}):
        idx = [i for i, s in enumerate(samples) if s["robot"] == n]
        if len(idx) > a.max:
            idx = sorted({idx[int(round(j))] for j in np.linspace(0, len(idx) - 1, a.max)})
        keep += idx
    samples = [samples[i] for i in sorted(keep)]
    parents = len(samples)
    samples = [dict(robot=sm["robot"], parent=i, q=sm["q"], **lg) for i, sm in enumerate(samples) for lg in sm["lags"]]
    pol = S.Policy(n=1)
    nrm, scale = pol.nrm, float(pol.cfg["control"]["action_scale"])
    default = torch.tensor(pol.default)
    n = len(samples)
    if n == 0:               # always a record: a seat whose robots never had a row in effect has nothing to audit
        out = {"episode": a.episode, "seat": a.seat, "every": a.every, "flag_rad": FLAG_RAD, "samples": 0,
               "replay_agrees": agrees, "robots": {}, "flag": False}
        print(json.dumps(out))
        if a.out:
            json.dump(out, open(a.out, "w"), indent=1)
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
        fit_all = torch.minimum(err(cmd, ph), best).numpy()
    fit = np.full(parents, np.inf)       # each sample: its best lag
    lag_of = np.zeros(parents, int)
    for i, sm in enumerate(samples):
        if fit_all[i] < fit[sm["parent"]]:
            fit[sm["parent"]], lag_of[sm["parent"]] = fit_all[i], sm["lag"]
    robot_of = {sm["parent"]: sm["robot"] for sm in samples}
    out = {"episode": a.episode, "seat": a.seat, "every": a.every, "flag_rad": FLAG_RAD, "lags": LAGS,
           "samples": parents, "replay_agrees": agrees, "robots": {}}
    for robot in sorted(set(robot_of.values())):
        idx = [i for i in range(parents) if robot_of.get(i) == robot]
        e = fit[idx]
        out["robots"][robot] = dict(samples=len(idx), median_rad=round(float(np.median(e)), 4),
                                    p10_rad=round(float(np.percentile(e, 10)), 4),
                                    share_below_flag=round(float(np.mean(e < FLAG_RAD)), 3),
                                    best_lag_counts=[int(np.sum(lag_of[idx][e < FLAG_RAD] == lg)) for lg in range(LAGS)])
    out["flag"] = any(v["share_below_flag"] > 0.5 for v in out["robots"].values())
    print(json.dumps(out))
    if a.out:
        json.dump(out, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
