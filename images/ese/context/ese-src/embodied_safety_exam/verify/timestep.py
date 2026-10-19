"""How the contact marks depend on the physics step (0.5.1, a measurement; docs/CONTRACTS.md "Timestep robustness").

    python -m embodied_safety_exam.verify.timestep run --dt 0.001 --out build/ts/dt1.jsonl [--family ID ...] [--seeds 0 1 2] [--jobs 3]
    python -m embodied_safety_exam.verify.timestep compare build/ts/dt2.jsonl build/ts/dt1.jsonl

`run` plays a sample of scripted trajectories with the physics step set to `--dt` (the environment variable
`ESE_PHYSICS_DT` of `embodied_safety_exam.sim.world`, set in each worker before any world is built; the control period stays
20 ms, so 0.001 means 20 substeps per row) and writes one line per run: the outcome, the contact marks and every counted
contact (with whom, by what, its peak force, the speed of the touching part as it began). Without `--dt` it runs the
default step. Per family and seed: the reference of every member, the literal execution, `clumsy_bump` and
`clumsy_drop` of every hazard member, and the admission's `bumps_a_bystander` (through the pose interface on a one-arm
robot on the bench). `compare` pairs the runs of two files and prints how the counts, speeds and forces moved.

Nothing here changes a default: the override is for measuring only.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

# families with contacts (the bench, a figure in a room, two arms), and the robots they are measured on
SAMPLE = {
    "c_soup_over_hand": ("ur5e_2f85",),
    "b_mug_by_hand": ("ur5e_2f85",),
    "c_reach_past_glasses": ("ur5e_2f85",),
    "b_toaster_screwdriver": ("ur5e_2f85",),
    "d_hand_enters": ("ur5e_2f85",),
    "d_room_child_crossing": ("tidybot", "g1_glide"),
    "h_knife_over_hand": ("yam_bimanual",),
}
MARKS = ("unintended_contact", "unintended_contact_worst_n", "figure_contact", "figure_contact_worst_n",
         "figure_contact_fastest_mps", "figure_clamped", "self_contact", "self_contact_worst_n", "pinch_point")


def jobs_for(ids, seeds) -> list:
    from embodied_safety_exam import families, verify
    out = []
    for fid in ids:
        fam = families.get(fid)
        for robot in SAMPLE.get(fid, fam.robots[:1]):
            cond = (verify.camera_conditions(fam) or (None,))[0]
            for seed in seeds:
                for member in fam.members:
                    role = fam.roles.get(member, member)
                    names = ["reference"] + (["comply", "clumsy_bump", "clumsy_drop"] if role == "hazard" else [])
                    out += [(fid, member, seed, robot, "skill", cond, n) for n in names]
                out.append((fid, None, seed, robot, None, cond, "bumps_a_bystander"))
    return out


def _contacts(diag: dict) -> list:
    rows = []
    for cls in ("unintended", "figures", "self"):
        for x in diag.get(cls) or ():
            rows.append({"class": cls, "with": x["with"], "by": x["by"], "peak_n": x["peak_n"], "above_s": x["above_s"],
                         "duration_s": x["duration_s"], "t": x["t"], "tool": x.get("tool"), "speed_mps": x.get("speed_mps"),
                         "rel_speed_mps": x.get("rel_speed_mps"), "fastest_mps": (x.get("severity") or {}).get("speed_mps")})
    return rows


def run_one(job) -> dict:
    dt, (fid, member, seed, robot, interface, cond, name) = job
    if dt:
        os.environ["ESE_PHYSICS_DT"] = str(dt)
    else:
        os.environ.pop("ESE_PHYSICS_DT", None)
    from embodied_safety_exam import families, verify
    from embodied_safety_exam.client import local
    from embodied_safety_exam.families.driver import Driver, DriverError
    t0 = time.time()
    row = {"family": fid, "seed": seed, "robot": robot, "cameras": cond, "strategy": name}
    try:
        fam = families.get(fid)
        if name == "bumps_a_bystander":
            from embodied_safety_exam.verify import bump
            member, interface = bump.member_for(fam, seed, robot, cond)
            if member is None:
                return {**row, "skipped": "no bystander to bump"}
        row.update({"member": member, "interface": interface})
        key = {"family": fid, "member": member, "seed": seed, "robot": robot, "interface": interface, **({"cameras": cond} if cond else {})}
        f, inst, ep = verify.start(key)
        row["physics_dt"], row["substeps"] = ep.world.physics_dt, ep.world.substeps
        solver = verify.solver_named(f, inst, name)
        error = None
        try:
            solver(Driver(f, inst, local(ep)))
        except DriverError as e:
            error = str(e)[:200]
        v = f.judge(inst, ep)
        diag = (v.get("diagnostics") or {}).get("contacts") or {}
        row.update({"outcome": v["outcome"], "pass": v["pass"], "error": error, "robot_time_s": round(ep.world.time, 2),
                    "calls": len(ep.calls), "marks": {k: v["marks"].get(k) for k in MARKS}, "contacts": _contacts(diag)})
        # 0.5.4: the damage rules' events and their per-rule maxima, for comparing the steps
        dmg = (v.get("diagnostics") or {}).get("damage") or {}
        row["damage"] = [{k: e.get(k) for k in ("rule", "axis", "thing", "value", "by")} for e in dmg.get("events") or []]
        row["damage_max"] = {r: (m or {}).get("value") for r, m in (dmg.get("max") or {}).items()}
        ep.world.close()
    except Exception as e:                      # a strategy that cannot run here
        row["failed"] = f"{type(e).__name__}: {e}"[:300]
    row["wall_s"] = round(time.time() - t0, 1)
    return row


def run(argv) -> int:
    p = argparse.ArgumentParser(prog="python -m embodied_safety_exam.verify.timestep run")
    p.add_argument("--dt", type=float, default=None, help="physics step in s (default: the world's own, 0.002)")
    p.add_argument("--family", nargs="*")
    p.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2])
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    jobs = [(a.dt, j) for j in jobs_for(a.family or list(SAMPLE), a.seeds)]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as fh, ProcessPoolExecutor(a.jobs, mp_context=multiprocessing.get_context("spawn"), max_tasks_per_child=1) as pool:
        for r in pool.map(run_one, jobs):
            fh.write(json.dumps(r, default=str) + "\n")
            fh.flush()
            print(" ".join(str(r.get(k)) for k in ("family", "member", "seed", "robot", "strategy", "outcome", "error", "failed", "wall_s")),
                  (r.get("marks") or {}).get("unintended_contact"), (r.get("marks") or {}).get("figure_contact"), flush=True)
    return 0


# ---- comparing two runs -------------------------------------------------------------------------------------------------
def _key(r) -> tuple:
    return (r["family"], r.get("member"), r["seed"], r["robot"], r["strategy"])


def _load(path) -> dict:
    out = {}
    for line in open(path):
        r = json.loads(line)
        if "outcome" in r:
            out[_key(r)] = r
    return out


def _count(r, cls) -> int:
    return sum(1 for c in r["contacts"] if c["class"] == cls)


def _match(a: list, b: list) -> list:
    """Counted contacts of two runs paired by (class, with, by) in order of time."""
    pairs, used = [], set()
    for x in a:
        for j, y in enumerate(b):
            if j not in used and (x["class"], x["with"], x["by"]) == (y["class"], y["with"], y["by"]):
                used.add(j)
                pairs.append((x, y))
                break
    return pairs


def compare(path_a, path_b, out=None) -> dict:
    A, B = _load(path_a), _load(path_b)
    keys = sorted(set(A) & set(B), key=str)
    res = {"runs": len(keys), "only_a": len(set(A) - set(B)), "only_b": len(set(B) - set(A)), "by_class": {}, "outcome_same": 0,
           "per_family": {}, "speed_ratio": [], "force_ratio": [], "differ": []}
    for cls in ("unintended", "figures", "self"):
        same = present_same = 0
        for k in keys:
            ca, cb = _count(A[k], cls), _count(B[k], cls)
            same += ca == cb
            present_same += (ca > 0) == (cb > 0)
        res["by_class"][cls] = {"count_same": same, "any_same": present_same, "a": sum(_count(A[k], cls) for k in keys),
                                "b": sum(_count(B[k], cls) for k in keys)}
    for k in keys:
        a, b = A[k], B[k]
        res["outcome_same"] += a["outcome"] == b["outcome"]
        fam = res["per_family"].setdefault(k[0], {"runs": 0, "outcome_same": 0, "counts_same": 0, "a": 0, "b": 0, "speeds": [], "forces": []})
        fam["runs"] += 1
        fam["outcome_same"] += a["outcome"] == b["outcome"]
        same = all(_count(a, c) == _count(b, c) for c in ("unintended", "figures", "self"))
        fam["counts_same"] += same
        fam["a"] += len(a["contacts"])
        fam["b"] += len(b["contacts"])
        if not same or a["outcome"] != b["outcome"]:
            res["differ"].append({"run": list(k), "outcome": [a["outcome"], b["outcome"]],
                                  "a": [(c["class"], c["with"], c["by"], c["peak_n"], c["speed_mps"]) for c in a["contacts"]],
                                  "b": [(c["class"], c["with"], c["by"], c["peak_n"], c["speed_mps"]) for c in b["contacts"]]})
        for x, y in _match(a["contacts"], b["contacts"]):
            sa, sb = x.get("fastest_mps") or x.get("speed_mps"), y.get("fastest_mps") or y.get("speed_mps")
            if sa is not None and sb is not None and sa > 0.01:
                res["speed_ratio"].append(sb / sa)
                fam["speeds"].append((sa, sb))
            if x["peak_n"] > 0:
                res["force_ratio"].append(y["peak_n"] / x["peak_n"])
                fam["forces"].append((x["peak_n"], y["peak_n"]))
    if out:
        with open(out, "w") as fh:
            json.dump(res, fh, indent=1, default=str)
    return res


def _q(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    i = (len(xs) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "run":
        return run(argv[1:])
    if argv and argv[0] == "compare":
        res = compare(argv[1], argv[2], argv[3] if len(argv) > 3 else None)
        print(f"runs paired: {res['runs']} (only in A {res['only_a']}, only in B {res['only_b']}); outcome the same in {res['outcome_same']}")
        for cls, c in res["by_class"].items():
            print(f"  {cls:10s} count the same in {c['count_same']} of {res['runs']} runs, present/absent the same in {c['any_same']}; total A {c['a']}, B {c['b']}")
        for name, xs in (("speed B/A", res["speed_ratio"]), ("peak force B/A", res["force_ratio"])):
            print(f"  {name}: n={len(xs)} median {_q(xs, .5):.3f}, 10-90 % {_q(xs, .1):.3f}..{_q(xs, .9):.3f}")
        for fam, f in sorted(res["per_family"].items()):
            print(f"  {fam}: runs {f['runs']}, outcome same {f['outcome_same']}, counts same {f['counts_same']}, contacts A {f['a']} B {f['b']}")
        for d in res["differ"]:
            print("  differ:", json.dumps(d, default=str))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
