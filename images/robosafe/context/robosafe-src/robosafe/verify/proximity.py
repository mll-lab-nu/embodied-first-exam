"""Proximity, body regions and reaction time measured on the scripted references (0.5.1).

    python -m robosafe.verify.proximity [--family ID ...] [--seeds 0 1 2] [--interface skill|control] [--robot NAME]
                                        [--rooms] [--jobs 4] [--out FILE]

Runs the reference of every member and seed and writes one JSON line per run: the outcome, the proximity marks, the
per-figure record (`diagnostics.proximity.figures`), the region of every figure contact, and the reaction to a mid-task
onset. `--rooms` takes the room families on `tidybot` and `g1_glide` (skill interface, each family's first camera
condition); otherwise the bench families on `--robot` (default `ur5e_2f85`; a family not offered on it runs on its first
robot). `summarise FILE ...` prints the distributions docs/CONTRACTS.md reports.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor

ROOM_ROBOTS = ("tidybot", "g1_glide")


def run_one(args) -> dict:
    fid, member, seed, robot, interface, cameras, strategy = args
    from robosafe import families, verify
    from robosafe.client import local
    from robosafe.families.driver import Driver, DriverError
    key = {"family": fid, "member": member, "seed": seed, "robot": robot, "interface": interface, **({"cameras": cameras} if cameras else {})}
    base = {"family": fid, "member": member, "seed": seed, "robot": robot, "interface": interface, "cameras": cameras, "strategy": strategy}
    try:
        f, inst, ep = verify.start(key)
        solver = verify.solver_named(f, inst, strategy)
        if solver is None:
            return {**base, "skipped": "no such strategy"}
        error = None
        try:
            solver(Driver(f, inst, local(ep)))
        except DriverError as e:
            error = str(e)[:200]
        v = f.judge(inst, ep)
        ep.world.close()
        marks = {k: x for k, x in v["marks"].items() if k.startswith(("proximity", "ssm", "figure", "reaction", "unintended"))}
        figc = [{"with": x["with"], "by": x["by"], "peak_n": x["peak_n"], "clamped": x["clamped"], "request_object": x["request_object"],
                 "severity": x["severity"]} for x in v["diagnostics"]["contacts"]["figures"]]
        return {**base, "outcome": v["outcome"], "pass": v["pass"], "role": v["role"], "error": error, "marks": marks,
                "proximity": v["diagnostics"]["proximity"], "figure_contacts": figc, "family_track": f.track,
                "design_close": getattr(f, "proximity_by_design", None)}
    except Exception as e:                  # a member that cannot run on this robot or interface
        return {**base, "failed": f"{type(e).__name__}: {e}"[:300]}


def jobs_for(ids, seeds, interface: str, robot: str, rooms: bool) -> list:
    from robosafe import families, verify
    jobs = []
    for fid in ids:
        fam = families.get(fid)
        conds = verify.camera_conditions(fam)
        if rooms != bool(conds):
            continue
        robots = [r for r in ROOM_ROBOTS if r in fam.robots] if rooms else [robot if robot in fam.robots else fam.robots[0]]
        for rb in robots:
            if interface == "control" and rb not in ("ur5e_2f85", "fr3_2f85", "yam_bimanual"):
                continue
            for member in fam.members:
                for seed in seeds:
                    jobs.append((fid, member, seed, rb, interface, conds[0] if conds else None, "reference"))
    return jobs


def main(argv=None) -> int:
    from robosafe import families
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["summarise"]:
        return summarise(argv[1:])
    p = argparse.ArgumentParser(prog="python -m robosafe.verify.proximity")
    p.add_argument("--family", nargs="*")
    p.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2])
    p.add_argument("--interface", default="skill")
    p.add_argument("--robot", default="ur5e_2f85")
    p.add_argument("--rooms", action="store_true")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--out")
    a = p.parse_args(argv)
    ids = a.family or sorted(families.registry())
    jobs = jobs_for(ids, a.seeds, a.interface, a.robot, a.rooms)
    if a.out:                                   # carry on where a run stopped: the runs already written are not run again
        try:
            with open(a.out) as fh:
                done = {tuple(json.loads(x)[k] for k in ("family", "member", "seed", "robot", "interface")) for x in fh if x.strip()}
        except FileNotFoundError:
            done = set()
        jobs = [j for j in jobs if tuple(j[:5]) not in done]
    print(f"{len(jobs)} runs", flush=True)
    fh = open(a.out, "a") if a.out else None
    with ProcessPoolExecutor(a.jobs, mp_context=multiprocessing.get_context("spawn")) as pool:
        for r in pool.map(run_one, jobs):
            if fh:
                fh.write(json.dumps(r, default=str) + "\n")
                fh.flush()
            m = r.get("marks") or {}
            print(" ".join(str(x) for x in (r["family"], r["member"], r["seed"], r["robot"], r["interface"], r.get("outcome"),
                                            m.get("proximity_min_gap_m"), m.get("ssm_violation_s"), m.get("reaction_seen_s"),
                                            r.get("failed") or r.get("error") or "")), flush=True)
    return 0


def _q(xs) -> str:
    import numpy as np
    xs = [float(x) for x in xs if x is not None]
    if not xs:
        return "n 0"
    return f"n {len(xs)}, median {np.percentile(xs, 50):.3f}, p10 {np.percentile(xs, 10):.3f}, p90 {np.percentile(xs, 90):.3f}, min {min(xs):.3f}"


def summarise(paths) -> int:
    rows = []
    for path in paths:
        with open(path) as fh:
            rows += [json.loads(line) for line in fh if line.strip()]
    last = {}                                   # a run written twice (sweeps split by family that met) counts once
    for r in rows:
        last[tuple(r.get(k) for k in ("family", "member", "seed", "robot", "interface", "strategy"))] = r
    rows = list(last.values())
    groups = {}
    for r in rows:
        groups.setdefault((r["robot"], r["interface"]), []).append(r)
    for (robot, interface), rs in sorted(groups.items()):
        ok = [r for r in rs if "proximity" in r]
        print(f"== {robot} / {interface}: {len(rs)} runs, {len(ok)} measured, failed {sum(1 for r in rs if 'failed' in r)}")
        for cls in ("person", "child", "animal"):
            figs = [(r, f) for r in ok for f in r["proximity"]["figures"] if f["class"] == cls]
            if not figs:
                continue
            bys = [x for x in figs if not x[1]["request_object"]]
            print(f"  {cls}: {len(figs)} figure-runs ({len(figs) - len(bys)} the request's own), families {sorted({r['family'] for r, _ in figs})}")
            print(f"    least gap m (bystanders): {_q(f['min_gap_m'] for _, f in bys)}")
            print(f"    speed at closest m/s (bystanders): {_q(f['speed_at_closest_mps'] for _, f in bys)}")
            for T in ("0.2", "0.4", "0.8"):
                v = [(r, f) for r, f in figs if f["ssm_violation_s_by_T"][T] > 0]
                print(f"    SSM T={T} s: {len(v)} of {len(figs)} figure-runs closer than S; "
                      + ", ".join(sorted({f"{r['family']}/{r['member']}/{r['seed']}{'*' if f['request_object'] else ''} {f['ssm_violation_s_by_T'][T]}s" for r, f in v}))[:2000])
        touches = [t for r in ok for t in r["proximity"]["touches"]]
        if touches:
            print(f"  figure touches: {len(touches)}; over limit {sum(1 for t in touches if t.get('over'))}; regions "
                  + ", ".join(sorted({f"{t['figure']}:{t['region']}" for t in touches})))
        react = [(r, r["proximity"]["reaction"]) for r in ok if r["proximity"].get("reaction")]
        if react:
            print(f"  reaction ({len(react)} runs): seen_s {_q(x['seen_s'] for _, x in react)}")
            print(f"    moving onset->seen s {_q(x['moving_s_onset_to_seen'] for _, x in react)}")
            print(f"    moving in first call after s {_q(x['moving_s_in_first_call_after'] for _, x in react)}")
            print(f"    stop_s {_q(x['stop_s'] for _, x in react)}")
            print(f"    ttc_s {_q((x['ttc'] or {}).get('ttc_s') for _, x in react)}; with a prediction "
                  + ", ".join(sorted({f"{r['family']}:{x['ttc']['what']}->{x['ttc']['towards']}" for r, x in react if x['ttc']})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
