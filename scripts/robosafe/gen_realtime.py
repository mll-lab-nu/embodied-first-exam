#!/usr/bin/env python3
"""Generate RoboSafeBench's standard-realtime tasks: tasks/cell-<slug>-i<NN>-standard-realtime (eai-standard/2.3), one
per instance of the realtime set (make_rt_instances.py REALTIME_FAMILIES: the families with a hazard that appears
mid-task and a_pet_appliance), the
standard task's instance under RoboSafeBench's realtime clock (docs/benchmarks/robosafe.md, "Standard-realtime tasks").

    python3 scripts/robosafe/gen_realtime.py render     # (re)write every realtime task dir; `git diff tasks/` stays empty
    python3 scripts/robosafe/gen_realtime.py check      # write nothing; exit 1 if a task dir differs
Then `cd tasks && harbor add --scan .` when a digest changed. Needs only Python 3 (no simulator).

Inputs, all in the repository, besides what gen_tasks.py reads:
  scripts/robosafe/instances_rt/<slug>-iNN.json  the instance under the realtime clock (make_rt_instances.py, in the image)
  scripts/robosafe/oracles_rt/<slug>-iNN.json    the reference, nothing and `done` at once under the realtime clock
  scripts/robosafe/oracles/<slug>-iNN.{json,npz} the reference's rows (the standard task's)
  scripts/robosafe/shared/realtime/              the realtime service (rcb_rsb_rt.py), the layer and client
                                                 (rcb_realtime.py, rcb_client.py: scripts/humanoidbench/shared/realtime/,
                                                 byte-identical), the grader (grade.py on the standard grade.py) and the
                                                 reference's driver (oracle_rt.py, solve.sh)
  scripts/robosafe/templates/realtime/           every other task file; templates/arms/<robot>/realtime/ the
                                                 instruction's paragraphs about time
"""

import argparse
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gen_tasks as G  # noqa: E402

ROOT = G.ROOT
RT = HERE / "shared/realtime"
STD = HERE / "shared/standard"
MODE = "standard-realtime"
SIM_RT = ("rcb_realtime.py", "rcb_rsb_rt.py")


def realtime_set(sel: dict) -> list:
    """The slugs of make_rt_instances.py's REALTIME_FAMILIES (RoboSafeBench family ids) in families.json."""
    text = (HERE / "make_rt_instances.py").read_text()
    ids = re.findall(r'"([a-z0-9_]+)"', re.search(r"^REALTIME_FAMILIES = \((.*?)\)", text, re.M | re.S).group(1))
    by_id = {f["rsb"]: slug for slug, f in sel.items()}
    return [by_id[i] for i in ids]


def service_limit(name: str) -> int:
    m = re.search(rf'^{name} = int\(os\.environ\.get\("[A-Z_]+"\) or (\d+)\)', (RT / "rcb_rsb_rt.py").read_text(), re.M)
    return int(m.group(1))


def task_dir(slug: str, nn: str) -> str:
    return f"{G.PREFIX}-{slug}-{nn}-{MODE}"


def agent_timeout() -> int:
    from task_conventions import cutoff_sec
    return int(cutoff_sec(G.BENCHMARK, MODE))


def arms_rt(robot: str) -> dict:
    d = G.ARMS / robot / "realtime"
    if not d.is_dir():
        raise RuntimeError(f"no realtime instruction text for the robot {robot!r} ({d.relative_to(ROOT)})")
    return {f"ARMS_RT_{f.stem}": f.read_text().rstrip("\n") for f in sorted(d.glob("*.md"))}


def rt_fault(slug: str, nn: str) -> str | None:
    p = HERE / "oracles_rt" / f"{slug}-{nn}.json"
    if not p.exists():
        return "no reference checked under the realtime clock (make_rt_instances.py)"
    o = json.loads(p.read_text())
    if not o["result"]["pass"]:
        return f"the reference ends {o['result']['outcome']} under the realtime clock"
    if o["nop"]["pass"] or o["done_at_once"]["pass"]:
        return "a trivial strategy passes under the realtime clock"
    return None


def realtime_robots() -> tuple:
    text = (HERE / "make_rt_instances.py").read_text()
    return tuple(re.findall(r'"([a-z0-9_]+)"', re.search(r"^REALTIME_ROBOTS = \((.*?)\)", text, re.M).group(1)))


def served(slug: str, fam: dict) -> list:
    """The members of the family its standard tasks serve (gen_tasks.held_back: the admission's served set, the
    references): the realtime set takes them, never a fixed list."""
    return [nn for nn in fam["instances"]
            if G.robot_of(fam, nn) in realtime_robots() and G.held_back(slug, nn, fam) is None]


def held_back(slug: str, nn: str, fam: dict) -> str | None:
    if why := G.held_back(slug, nn, fam):
        return why
    for other in served(slug, fam):              # a family is served whole: every member its standard tasks serve
        if why := rt_fault(slug, other):
            return why if other == nn else f"{other} of the family: {why}"
    return None


def plan(slug: str, fam: dict, nn: str, version: str) -> dict:
    inst_raw = (HERE / "instances_rt" / f"{slug}-{nn}.json").read_bytes()
    inst = json.loads(inst_raw)
    std = json.loads((HERE / "instances" / f"{slug}-{nn}.json").read_text())
    same_key = {k: v for k, v in inst["key"].items() if k != "max_time_s"} == {**std["key"], "clock": "realtime"}
    if not same_key or inst["task_text"] != std["task_text"]:
        raise RuntimeError(f"instances_rt/{slug}-{nn}.json is not the standard instance under the realtime clock")
    orc = json.loads((HERE / "oracles" / f"{slug}-{nn}.json").read_text())
    ort = json.loads((HERE / "oracles_rt" / f"{slug}-{nn}.json").read_text())
    vals = G.values(slug, nn, fam, inst, orc, version)
    evidence = (f"RoboSafeBench's scripted reference of this member, compiled into rows of the action types and played "
                f"as chained plans under the realtime clock, passes (make_rt_instances.py, RoboSafeBench "
                f"{inst['robosafe_version']}); doing nothing and exiting `done` at once fail")
    vals.update({
        **arms_rt(inst["key"]["robot"]),
        "TASK": task_dir(slug, nn), "STD_TASK": G.task_dir(slug, nn), "AGENT_TIMEOUT": agent_timeout(),
        "ORACLE_EVIDENCE": G.toml_str(evidence), "MAX_CAMERAS": service_limit("RT_CAMERAS"),
        "WATCH_IMAGES": service_limit("RT_WATCH_IMAGES_PER_S"), "ROBOSAFE_VERSION": inst["robosafe_version"],
        "PICTURE_STEPS": service_limit("PICTURE_STEPS"),
        "PICTURE_S": G.fmt(round(service_limit("PICTURE_STEPS") * inst["control"]["control_dt"], 4)),
    })
    # the arms' realtime paragraphs carry placeholders of their own: fill them first
    vals = {k: (G.fill(v, {x: y for x, y in vals.items() if not x.startswith("ARMS_")}) if k.startswith("ARMS_RT_") else v)
            for k, v in vals.items()}
    files = G.files_of(HERE / "templates/realtime", vals)
    files["environment/rcb_client.py"] = ((RT / "rcb_client.py").read_bytes(), 0o644)
    files["environment/rcb1.py"] = ((STD / "rcb1.py").read_bytes(), 0o644)
    req = G.CLIENT["CLIENT_REQUIREMENTS"].strip()
    files["environment/client-requirements.txt"] = ((ROOT / "scripts/eai_standard" / req).read_bytes(), 0o644)
    for name in G.SIM_FILES:
        files[f"environment/sim/{name}"] = ((STD / name).read_bytes(), 0o644)
    for name in SIM_RT:
        files[f"environment/sim/{name}"] = ((RT / name).read_bytes(), 0o644)
    files["environment/sim/instance.json"] = (inst_raw, 0o644)
    files["tests/grade.py"] = ((RT / "grade.py").read_bytes(), 0o644)
    files["tests/grade_rsb.py"] = ((STD / "grade.py").read_bytes(), 0o644)
    files["solution/solve.sh"] = ((RT / "solve.sh").read_bytes(), 0o755)
    files["solution/oracle_rt.py"] = ((RT / "oracle_rt.py").read_bytes(), 0o644)
    files["solution/oracle.json"] = (json.dumps({"plan": orc["plan"]}).encode() + b"\n", 0o644)
    if orc.get("arrays"):
        files["solution/oracle.npz"] = ((HERE / "oracles" / f"{slug}-{nn}.npz").read_bytes(), 0o644)
    del ort
    return {task_dir(slug, nn): files}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("render", "check"))
    ap.add_argument("--out", default=str(ROOT / "tasks"))
    a = ap.parse_args()
    check = a.cmd == "check"
    out = pathlib.Path(a.out)
    os.umask(0o022)
    sel = json.loads((HERE / "families.json").read_text())["families"]
    version = (ROOT / "images/robosafe/VERSION").read_text().strip()
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize
    diffs, made, held = [], set(), []
    for slug in realtime_set(sel):
        fam = sel[slug]
        for nn in fam["instances"]:
            if G.robot_of(fam, nn) not in realtime_robots():
                continue                                # a robot the realtime set is not served on
            if why := G.held_back(slug, nn, fam):       # not served in the standard tasks either
                held.append(f"{task_dir(slug, nn)}: {why}")
                continue
            if not (HERE / "instances_rt" / f"{slug}-{nn}.json").exists():
                diffs.append(f"missing {slug}-{nn}: no realtime instance (make_rt_instances.py)")
                continue
            if why := held_back(slug, nn, fam):
                held.append(f"{task_dir(slug, nn)}: {why}")
                continue
            for name, files in G.normalized(plan(slug, fam, nn, version), normalize).items():
                made.add(name)
                diffs += G.sync(out / name, files, check)
    for t in sorted(out.glob(f"{G.PREFIX}-*-{MODE}")):
        if t.is_dir() and t.name not in made:
            diffs.append(f"stale  {t.name} (no realtime instance for it: remove it)")
    for d in diffs:
        print(d)
    for h in held:
        print("held back", h)
    print(f"{'checked' if check else 'generated'} {len(made)} RoboSafeBench standard-realtime task dirs "
          f"({len(held)} held back): {len(diffs)} difference(s)")
    return 1 if (check and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
