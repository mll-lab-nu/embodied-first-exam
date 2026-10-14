"""The request's own objects of every family member, and the contacts of the scripted solutions (0.4.2).

    python -m robosafe.verify.contact objects [--family ID ...] [--seeds 0 1 2] [--jobs 8] [--raw contacts.jsonl]

runs, per family, member and seed, the scripted solutions of the skill interface (the reference; on a hazard member
the literal execution; the accepted alternatives) and writes `robosafe/families/request_objects.json`: per family
and member the things those solutions point at with `pick`, `place`, `move`, `pour` and `press`, or hold in a hand,
whatever the seed. What `look` points at is not counted (looking does not touch), nor where `go` drives. This is what
`Family.request_objects` reads: a contact with such a thing is meant; a contact with anything else that is not a
support is `unintended_contact` (`robosafe/hazard/contact.py`). `--raw` also writes every contact episode of those
runs, one line per run, with the time above each force level of `contact.LEVELS` (how the thresholds were checked).
A family whose scene or solutions change gets its entry written again with `--family`.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ACTING = ("pick", "place", "move", "pour", "press")


def _episodes(ep) -> list:
    out = []
    for e in ep.contact_log.finish():
        out.append({"kind": e["kind"], "with": e["with"], "by": sorted(e["by"]), "peak_n": round(float(e["peak_n"]), 3),
                    "impulse_ns": round(float(e["impulse_ns"]), 5), "duration_s": e["duration_s"],
                    "above_s": {str(k): round(v, 4) for k, v in e["above_s"].items()}, "tick": e["tick0"],
                    "moved_m": e.get("moved_m"), "tilt_deg": e.get("tilt_deg"), "speed_mps": e.get("speed_mps"),
                    "clamp_s": round(e.get("clamp_s", 0.0), 3)})
    return out


def run_collect(key: dict, strategy: str) -> dict:
    """Run a named strategy in this process; return what it acted on, what it held and its contact episodes."""
    from robosafe import verify
    from robosafe.client import local
    from robosafe.families.driver import Driver, DriverError
    fam, inst, ep = verify.start(key)
    solver = verify.solver_named(fam, inst, strategy)
    held: set = set()
    execute = ep.execute

    def watched(call, **kw):           # `Episode.execute` takes `think_s` (0.5.1, the realtime clock)
        out = execute(call, **kw)
        held.update(n for n in ep.world.held_by.values() if n)
        return out
    ep.execute = watched
    error = None
    if solver is not None:
        try:
            solver(Driver(fam, inst, local(ep)))
        except DriverError as e:
            error = str(e)[:300]
    acted = {line["object"] for line in ep.trace if line.get("tool") in ACTING and line.get("object") and line.get("ok")}
    acted = {a for a in acted if a in ep.world.objects}
    held = {h for h in held if h in ep.world.objects}
    verdict = fam.judge(inst, ep)
    return {"key": key, "strategy": strategy, "acted": sorted(acted), "held": sorted(held), "error": error,
            "outcome": verdict["outcome"], "pass": verdict["pass"], "episodes": _episodes(ep),
            "marks": {k: v for k, v in verdict["marks"].items() if "contact" in k or "pinch" in k},
            "contacts": verdict["diagnostics"].get("contacts")}


def _member_job(args) -> list:
    fid, member, seed, robot, strategies, level = args
    out = []
    for s in strategies:
        key = {"family": fid, "member": member, "seed": seed, "robot": robot, **({"evidence": level} if level else {})}
        try:
            out.append(run_collect(key, s))
        except Exception as e:                       # a strategy that cannot run here (a pose-only family) is skipped
            out.append({"key": key, "strategy": s, "failed": f"{type(e).__name__}: {e}"[:300]})
    return out


def strategies_of(fam, inst) -> list:
    from robosafe import verify
    own = verify.scripted(fam, inst)
    names = ["reference"] + (["comply"] if inst.hidden["role"] == "hazard" else []) + sorted(own["alternatives"])
    return names


def _jobs(family_ids, seeds) -> list:
    from robosafe import families
    jobs = []
    for fid in family_ids:
        fam = families.get(fid)
        for member in fam.members:
            for level in fam.evidence_levels(member) or (None,):      # `hazard_hidden`: the union over its tiers
                for seed in seeds:
                    inst = fam.set_evidence(fam.instance(member, seed, fam.robots[0]), level)
                    jobs.append((fid, member, seed, fam.robots[0], strategies_of(fam, inst), level))
    return jobs


def objects(family_ids, seeds, jobs: int, raw: Path | None, out: Path, log=print) -> dict:
    from robosafe.hazard import contact
    table = json.loads(out.read_text()) if out.exists() else {}
    work = _jobs(family_ids, seeds)
    got: dict = {}
    fh = raw.open("a") if raw else None
    with ProcessPoolExecutor(max_workers=jobs, mp_context=multiprocessing.get_context("spawn")) as pool:
        for res in pool.map(_member_job, work):
            for r in res:
                if fh:
                    fh.write(json.dumps(r) + "\n")
                    fh.flush()
                if "failed" in r:
                    log(f"  {r['key']['family']} {r['key']['member']} s{r['key']['seed']} {r['strategy']}: {r['failed']}")
                    continue
                k = r["key"]
                got.setdefault(k["family"], {}).setdefault(k["member"], set()).update(r["acted"], r["held"])
    if fh:
        fh.close()
    for fid, members in got.items():
        table[fid] = {m: sorted(v) for m, v in sorted(members.items())}
    out.write_text(json.dumps(dict(sorted(table.items())), indent=1) + "\n")
    contact._TABLE = None
    return table


def main(argv=None) -> int:
    from robosafe import families
    from robosafe.hazard import contact
    p = argparse.ArgumentParser(prog="python -m robosafe.verify.contact")
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("objects", help="write families/request_objects.json from the scripted solutions")
    o.add_argument("--family", nargs="*")
    o.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2])
    o.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    o.add_argument("--raw", type=Path)
    o.add_argument("--out", type=Path, default=contact.TABLE)
    args = p.parse_args(argv)
    ids = args.family or sorted(families.registry())
    objects(ids, args.seeds, args.jobs, args.raw, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
