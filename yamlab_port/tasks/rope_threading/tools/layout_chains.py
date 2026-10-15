"""Offline enumeration of arm chains (numpy). A chain = per ring (in feeding order) the feeding and the receiving arm
(the last ring: feeding arm only); the first feeder is the arm that picks the tip. Every 2 x 2 combination per ring (32 for 3 rings)
is evaluated with the stroke solutions of layout_eval / medium_layout_search (keep=50):
  feed k   : feed poses of arm f_k (distinct gripper orientations; stroke_solutions, cone 25)
  recv k   : receive poses of arm r_k
  hand k   : f_k != r_k: hand-over pairs (feed end pose + receive start pose: arm capsules clear >= 1 cm AND TCPs >= 12 cm apart)
             f_k == r_k: same hand feeds and receives ('LL': the other arm clamps behind the ring; the clamp is NOT checked)
  xfer k   : r_k != f_k+1: arm-to-arm transfer between the rings. Only a necessary condition is checked: the receiver's receive end pose
             and the next feeder's feed start pose coexist (clearance >= 1 cm, TCPs >= 12 cm); r_k == f_k+1: direct, no check.
Ranking: feasible first; then more arm changes between rings (f_k+1 != r_k, "prefer hand change") first; then the minimum count.
"""
import itertools, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_eval as L
import medium_layout_search as M
import plan_np as PN

SIDE = {"L": "left", "R": "right"}


def stroke_table(order, fix):
    """sol[(ring, kind)][arm] = (list of (dev, path), diag) for cone 25."""
    tab = {}
    for i, r in enumerate(order):
        for kind, ts in (("feed", M.FEED_TS), ("recv", M.RECV_TS)):
            if kind == "recv" and i == len(order) - 1:
                continue
            tab[(r["name"], kind)] = {}
            for a in "LR":
                sol, dg = L.stroke_diag(SIDE[a], r["center"], r["travel"], ts, fix, 25.0)
                tab[(r["name"], kind)][a] = (sol, dict(dg, why=L.why(dg)))
    return tab


def pair_count(sols_a, arm_a, pose_a, sols_b, arm_b, pose_b, fix, top=20):
    """pairs (path of a at index pose_a, path of b at index pose_b) with arm clearance >= 1 cm and TCP distance >= 12 cm."""
    n = 0
    for _, pa in sols_a[:top]:
        qa = pa[pose_a]
        ta = L.tcp_world(SIDE[arm_a], qa)
        for _, pb in sols_b[:top]:
            qb = pb[pose_b]
            if (PN.arm_clearance(SIDE[arm_a], qa, fix, other=(SIDE[arm_b], qb, False))["arms"] >= 0.01
                    and np.linalg.norm(ta - L.tcp_world(SIDE[arm_b], qb)) >= 0.12):
                n += 1
    return n


def enumerate_chains(order, fix, picker, gate=None):
    """order: rings in feeding order (dict name/center/travel); picker 'L'/'R'; gate: dict(count, note) for pick + transition
    of the picker onto ring 1 (count = min of its numbers). -> list of chain dicts, ranked."""
    tab = stroke_table(order, fix)
    n = len(order)
    out = []
    hand_cache, xfer_cache = {}, {}
    names = [r["name"] for r in order]

    def count(k, kind, a):
        return len(tab[(names[k], kind)][a][0])

    def hand(k, f, r):
        if (k, f, r) not in hand_cache:
            hand_cache[(k, f, r)] = pair_count(tab[(names[k], "feed")][f][0], f, -1, tab[(names[k], "recv")][r][0], r, 0, fix)
        return hand_cache[(k, f, r)]

    def xfer(k, r, f):
        if (k, r, f) not in xfer_cache:
            xfer_cache[(k, r, f)] = pair_count(tab[(names[k], "recv")][r][0], r, -1, tab[(names[k + 1], "feed")][f][0], f, 0, fix)
        return xfer_cache[(k, r, f)]

    for combo in itertools.product(*[[(f, r) for f in "LR" for r in "LR"]] * (n - 1), "LR"):
        fr = list(combo[:-1]) + [(combo[-1], None)]
        steps, fail = [], None
        if fr[0][0] != picker:      # the picker must feed ring 1 (a hand-over right after the pick is a separate check)
            steps.append(dict(step="picker=first feeder", n=0, note="第一环须由捡绳的%s手喂入" % SIDE[picker]))
            fail = steps[-1]
        else:
            if gate is not None:
                steps.append(dict(step="pick+transition", n=gate["count"], note=gate["note"]))
        for k, (f, r) in enumerate(fr):
            c = count(k, "feed", f)
            tb = tab[(names[k], "feed")][f][1]
            steps.append(dict(step=f"{names[k]} 喂({f})", n=c, note=tb["why"] or "可行"))
            if r is not None:
                c = count(k, "recv", r)
                steps.append(dict(step=f"{names[k]} 接({r})", n=c, note=tab[(names[k], "recv")][r][1]["why"] or "可行"))
                if f != r:
                    h = hand(k, f, r) if count(k, "feed", f) and c else 0
                    steps.append(dict(step=f"{names[k]} 转交 {f}→{r}", n=h, note="手间距≥12cm 且胶囊间隙≥1cm 的对数"))
                else:
                    steps.append(dict(step=f"{names[k]} 同手接喂 {f}{f}", n=min(count(k, "feed", f), c), note="另一只手在环后夹住（未检查）"))
                nf = fr[k + 1][0]
                if r != nf:
                    x = xfer(k, r, nf) if c and count(k + 1, "feed", nf) else 0
                    steps.append(dict(step=f"{names[k]}→{names[k + 1]} 臂间转交 {r}→{nf}", n=x, note="接收末态与下一环喂入起点共存对数（必要条件）"))
        for s in steps:
            if s["n"] == 0 and fail is None:
                fail = s
        changes = sum(fr[k + 1][0] != fr[k][1] for k in range(n - 1))
        chain = " ".join((f + ">" + r) if r else f for f, r in fr)
        out.append(dict(chain=chain, feasible=fail is None, first_fail=None if fail is None else fail["step"],
                        first_fail_note=None if fail is None else fail["note"], min_n=min(s["n"] for s in steps), changes=changes, steps=steps))
    out.sort(key=lambda c: (not c["feasible"], -c["changes"] if c["feasible"] else 0, -c["min_n"]))
    return out, {f"{k[0]}_{k[1]}": {a: dict(poses=v[a][1]["poses"], why=v[a][1]["why"]) for a in "LR"} for k, v in tab.items()}
