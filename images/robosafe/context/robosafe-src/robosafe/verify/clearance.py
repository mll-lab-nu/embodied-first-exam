"""How close a scripted solution passes to the things it does not mean to touch (0.5.1, "Clearance").

    python -m robosafe.verify.clearance <family> [...] [--interface control|skill] [--seeds 0 1 2] [--members M ...]
                                        [--strategy reference] [--jobs 8] [--json out.jsonl]

plays a named strategy (the reference by default) and, after every control tick, measures the least distance between
the robot and every thing of the scene that a contact with is unintended: not one of the request's own
(`Family.request_objects`), not what a hand holds at that tick, not a support (a kind of `contact.SUPPORT_KINDS`, what a
thing of the request stood on as the episode began). The world's own shapes (table, floor, walls) are no things of the
scene and are never measured; fixed furniture (a shelf) is, as the contact marks count it. Three distances per tick:

- `all`: the robot's moving collision shapes (every link, the hand, its fingers and pads; the base bolted to the
  table is left out: it never moves) against the things' collision shapes;
- `links`: the same without the hand (an upper arm that comes down onto a glass);
- `held`: what a hand holds against the things, also leaving out what it was lifted from (the contact marks do the
  same).

Distances are `robosafe.sim.geom.distance` (MuJoCo's with its false zeros corrected; `exact` adds a guard for the
zeros it leaves), up to `REACH` (50 mm: a gap
of 50 mm means nothing came nearer), after a broad phase on bounding spheres. A distance under `TOUCH` (0.1 mm) is a
contact. Per run: the least gap of each kind with the robot body (or the thing held), the thing, the tick and the
time; the gap at the first tick (the robot at rest: a gap the layout gives every agent); the least gap to each thing;
and the contact marks of the verdict. A small gap is no failure of anything: it says where an agent's own way, a
little lower or a little wider than the reference's, would bump something (docs/CONTRACTS.md, "Clearance (0.5.1)").
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import mujoco
import numpy as np

REACH = 0.05        # m: distances are measured up to this
TOUCH = 1e-4        # m: nearer than this is a contact
KINDS = ("all", "links", "held")


def exact(m, d, g1: int, g2: int, reach: float, fromto, in_contact: bool) -> tuple:
    """(distance, how) of two geoms by `geom.distance` (col-core's, e4c8a6c), which corrects MuJoCo 3.8.1's false zeros
    itself, among them the zeros with `fromto` all zeros for pairs that are apart (a held bottle 40 mm from a glass,
    a_spike_drink seed 0 under the control interface). `how`: "direct" (MuJoCo's own answer stood), "nudged" (a false
    zero corrected), "unresolved" (a zero for a pair the collision pass has not put in contact that every nudge kept)."""
    from robosafe.sim import geom
    raw = float(mujoco.mj_geomDistance(m, d, int(g1), int(g2), float(reach), np.zeros(6)))
    dist = geom.distance(m, d, g1, g2, reach, fromto)
    if dist == raw:
        return dist, ("unresolved" if dist == 0.0 and not in_contact else "direct")
    return dist, "nudged"


def measure(key: dict, strategy: str = "reference", watch=(), watch_reach: float = 0.30) -> dict:
    """Run a strategy for this instance key (with `interface`) in this process and return its clearances. `watch`:
    things measured whatever they are (a request's own figure too), up to `watch_reach`, with the speed of the pinch
    point at the tick of the least distance (`watch` in the result)."""
    from robosafe import verify as V
    from robosafe.client import local
    from robosafe.families.driver import Driver, DriverError
    from robosafe.hazard import contact as HC

    fam, inst, ep = V.start(key)
    w = ep.world
    m, d = w.model, w.data
    c0, a0 = w._masks0
    collide = (c0 != 0) | (a0 != 0)
    owner = list(w._geom_owner)
    hand = set()
    for ix in w._ix.values():
        hand |= set(int(b) for b in ix["_hand_bodies"])
    robot = np.array([g for g in range(m.ngeom) if owner[g] == "robot" and collide[g]
                      and int(m.body_weldid[m.geom_bodyid[g]]) != 0], dtype=np.int64)
    links = robot[np.array([int(m.geom_bodyid[g]) not in hand for g in robot], dtype=bool)] if robot.size else robot
    shapes = {n: np.array([g for g in gs if collide[g]], dtype=np.int64) for n, gs in w._object_geoms.items()}
    own = HC.request_objects(fam, inst)
    log = ep.contact_log
    kinds = {n: o["kind"] for n, o in w.objects.items()}
    support = {n for n, k in kinds.items() if k in HC.SUPPORT_KINDS} | {u for r in own for u in log.rests_on.get(r, ())}
    fixed_out = own | support
    rbound = m.geom_rbound
    fromto = np.zeros(6)
    best: dict = {k: None for k in KINDS}
    first: dict = {k: None for k in KINDS}
    per_thing: dict = {}                         # thing -> {"all": mm, "links": mm, "held": mm}
    touches: dict = {}                           # (kind, part, thing) -> [first tick, ticks]
    corrected = {"nudged": 0, "unresolved": 0}
    ticks = [0]

    def body(g):
        return m.body(int(m.geom_bodyid[g])).name

    def least(ga, names, kind, by_thing, reach=REACH):
        """The least distance between the shapes `ga` and the shapes of `names`: (dist, g1, g2) or None."""
        if ga.size == 0 or not names:
            return None
        gb = np.concatenate([shapes[n] for n in names])
        if gb.size == 0:
            return None
        gap = (np.linalg.norm(d.geom_xpos[ga][:, None, :] - d.geom_xpos[gb][None, :, :], axis=2)
               - rbound[ga][:, None] - rbound[gb][None, :])
        ii, jj = np.nonzero(gap < reach)
        out = None
        pairs = None
        for i, j in zip(ii, jj):
            g1, g2 = int(ga[i]), int(gb[j])
            if pairs is None:
                n = int(d.ncon)
                pairs = {frozenset((int(a), int(b))) for a, b in d.contact.geom[:n]} if n else set()
            dist, how = exact(m, d, g1, g2, reach, fromto, frozenset((g1, g2)) in pairs)
            if how != "direct":
                corrected[how] += 1
            if dist < TOUCH and kind in KINDS:
                dist = min(dist, 0.0)
                part = body(g1) if kind != "held" else "held:" + owner[g1]
                t = touches.setdefault((kind, part, owner[g2]), [w.tick, 0])
                t[1] += 1
            thing = owner[g2]
            if by_thing is not None:
                cur = by_thing.setdefault(thing, {}).get(kind)
                if cur is None or dist < cur:
                    by_thing[thing][kind] = dist
            if out is None or dist < out[0]:
                out = (dist, g1, g2)
        return out

    def entry(res, kind):
        dist, g1, g2 = res
        e = {"gap_mm": round(dist * 1e3, 2), "thing": owner[g2], "thing_kind": kinds.get(owner[g2]),
             "tick": w.tick, "t_s": round(w.tick * 0.02, 2), "call": len(ep.calls), "contact": bool(dist <= 0.0)}
        e["part"] = ("held:" + owner[g1]) if kind == "held" else body(g1)
        return e

    watched = {n: None for n in watch if n in shapes}
    tcp_site = w._ix[w._mounts[0]["name"]]["tcp_site"]
    last_tcp = [None]
    tick0 = ep._tick

    def tick(row):
        tick0(row)
        ticks[0] += 1
        tcp = np.array(d.site_xpos[tcp_site])
        speed = 0.0 if last_tcp[0] is None else float(np.linalg.norm(tcp - last_tcp[0])) / 0.02
        last_tcp[0] = tcp
        for n in watched:
            res = least(robot, [n], "watch", None, reach=watch_reach)
            if res is not None and (watched[n] is None or res[0] < watched[n]["gap_m"]):
                watched[n] = {"gap_m": res[0], "gap_mm": round(res[0] * 1e3, 1), "part": body(res[1]),
                              "shape": m.geom(res[2]).name or str(res[2]), "tick": w.tick,
                              "t_s": round(w.tick * 0.02, 2), "call": len(ep.calls), "tcp_speed_mps": round(speed, 3)}
        held = {n for n in w._held_by.values() if n}
        names = [n for n in shapes if n not in fixed_out and n not in held]
        for kind, ga, cand in (("all", robot, names), ("links", links, names)):
            res = least(ga, cand, kind, per_thing)
            if res is None:
                continue
            if ticks[0] == 1:
                first[kind] = entry(res, kind)
            if best[kind] is None or res[0] < best[kind][0]:
                best[kind] = (res[0], entry(res, kind))
        if held:
            lifted = set().union(*(log.lifted_from.get(n, set()) for n in held))
            hg = np.concatenate([shapes[n] for n in held if n in shapes]) if any(n in shapes for n in held) else np.zeros(0, dtype=np.int64)
            res = least(hg, [n for n in names if n not in lifted], "held", per_thing)
            if res is not None and (best["held"] is None or res[0] < best["held"][0]):
                best["held"] = (res[0], entry(res, "held"))

    ep._tick = tick
    solver = V.solver_named(fam, inst, strategy)
    error = None
    if solver is not None:
        try:
            solver(Driver(fam, inst, local(ep)))
        except DriverError as e:
            error = str(e)[:400]
    ver = fam.judge(inst, ep)
    marks = ver.get("marks") or {}
    got = (ver.get("diagnostics") or {}).get("contacts") or {}
    out = {"key": {k: v for k, v in key.items()}, "strategy": strategy, "pass": bool(ver.get("pass")), "outcome": ver.get("outcome"),
           "driver_error": error, "ticks": ticks[0],
           "request_objects": sorted(own), "supports": sorted(support),
           "contact_exceptions": list((getattr(fam, "contact_exceptions", {}) or {}).get(inst.member, ())),
           **{f"min_{k}": (best[k][1] if best[k] else None) for k in KINDS},
           **{f"first_{k}": first[k] for k in ("all", "links")},
           "per_thing_mm": {n: {k: round(v * 1e3, 2) for k, v in sorted(g.items())} for n, g in sorted(per_thing.items())},
           "touches": [[k, p, t, v[0], v[1]] for (k, p, t), v in sorted(touches.items())],
           "marks": {k: marks.get(k) for k in ("unintended_contact", "figure_contact", "pinch_point")},
           "unintended": [{x: e.get(x) for x in ("with", "by", "peak_n", "tick")} for e in (got.get("unintended") or [])],
           "watch": {n: ({k: v for k, v in e.items() if k != "gap_m"} if e else None) for n, e in watched.items()},
           "zeros": corrected}
    try:
        w.close()
    except Exception:                       # noqa: BLE001 (a renderer that was never opened)
        pass
    return out


def _job(args) -> dict:
    key, strategy, watch, reach = args
    try:
        return measure(key, strategy, watch, reach)
    except Exception as e:                  # noqa: BLE001 (reported, not raised: the other runs go on)
        return {"key": key, "strategy": strategy, "failed": f"{type(e).__name__}: {e}"[:400]}


def keys_of(fam, seeds, interface: str, robot: str | None = None, members=None) -> list:
    """Every instance key of a family for these seeds: each member, and each tier of `hazard_hidden`."""
    out = []
    for member in members or fam.members:
        for level in fam.evidence_levels(member) or (None,):
            for seed in seeds:
                out.append({"family": fam.id, "member": member, "seed": int(seed), "robot": robot or fam.robots[0],
                            **({"evidence": level} if level else {}), "interface": interface})
    return out


def _fmt(e) -> str:
    if not e:
        return "   >50.0"
    return f"{e['gap_mm']:8.1f} {e['part']:>22s} {e['thing']:<16s} t={e['t_s']:6.2f}"


def main(argv=None) -> int:
    from robosafe import families
    p = argparse.ArgumentParser(prog="python -m robosafe.verify.clearance")
    p.add_argument("family", nargs="+")
    p.add_argument("--interface", default="control", choices=("control", "skill", "pose"))
    p.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2])
    p.add_argument("--members", nargs="*")
    p.add_argument("--robot")
    p.add_argument("--strategy", default="reference")
    p.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    p.add_argument("--json", help="also write one line per run here")
    p.add_argument("--watch", nargs="*", default=[], help="things measured whatever they are (a figure the request is about), up to --watch-reach")
    p.add_argument("--watch-reach", type=float, default=0.30)
    args = p.parse_args(argv)
    work = []
    for fid in args.family:
        fam = families.get(fid)
        work += [(k, args.strategy, tuple(args.watch), args.watch_reach) for k in keys_of(fam, args.seeds, args.interface, args.robot, args.members)]
    fh = open(args.json, "w") if args.json else None
    print(f"{'family':22s} {'member':16s} {'tier':14s} seed  {'all (mm, part, thing, t)':>55s}  |  links  |  held  |  rest (all)")
    with ProcessPoolExecutor(max_workers=args.jobs, mp_context=multiprocessing.get_context("spawn")) as pool:
        for r in pool.map(_job, work):
            if fh:
                fh.write(json.dumps(r, default=str) + "\n")
                fh.flush()
            k = r["key"]
            head = f"{k['family']:22s} {k['member']:16s} {k.get('evidence') or '':14s} {k['seed']:4d}"
            if "failed" in r:
                print(head, "FAILED", r["failed"], flush=True)
                continue
            rest = r["first_all"]["gap_mm"] if r.get("first_all") else None
            print(head, _fmt(r["min_all"]), "|", f"{r['min_links']['gap_mm']:.1f}" if r["min_links"] else ">50", "|",
                  f"{r['min_held']['gap_mm']:.1f} {r['min_held']['part']}" if r["min_held"] else ">50", "|",
                  f"{rest:.1f}" if rest is not None else ">50",
                  " ".join(f"| {n}: " + (f"{e['gap_mm']:.1f} {e['part']} t={e['t_s']} v={e['tcp_speed_mps']}" if e else f">{args.watch_reach * 1e3:.0f}")
                           for n, e in (r.get("watch") or {}).items()),
                  "" if r["pass"] else f"(reference {r['outcome']})", flush=True)
    if fh:
        fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
