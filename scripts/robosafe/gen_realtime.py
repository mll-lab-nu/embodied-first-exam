#!/usr/bin/env python3
"""Generate RoboSafeBench's standard-realtime tasks: tasks/rsb-<slug>-i<NN>-standard-realtime (eai-standard/2.3), one
per instance of the realtime set (make_rt_instances.py REALTIME_FAMILIES: the families with a hazard that appears
mid-task and a_pet_appliance), the
standard task's instance under RoboSafeBench's realtime clock (docs/benchmarks/robosafe.md, "Standard-realtime tasks").

    python3 scripts/robosafe/gen_realtime.py render     # (re)write every realtime task dir; `git diff tasks/` stays empty
    python3 scripts/robosafe/gen_realtime.py check      # write nothing; exit 1 if a task dir differs
The 0.5.4 candidate permits writes only with --selection-manifest and a separate --out.
Historical render-all examples below apply to historical registries; check remains read-only.

Every task's DIGEST is written by the normalize step (PROTOCOL §2.8). Needs only Python 3 (no simulator).

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
  scripts/robosafe/templates/rooms/<robot>/realtime/instruction.md.tmpl
                                                 a robot that drives (the TidyBot, 0.5.4): its whole realtime instruction,
                                                 in place of templates/realtime/instruction.md.tmpl and the arms' paragraphs,
                                                 with the camera condition's blocks kept (gen_tasks.room_instruction)
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


_SERVICE = {}
SERVICE_NAMES = ("RT_WATCH_IMAGES_PER_S", "PICTURE_COST_S", "PICTURE_COST_S_BY_ROBOT", "RT_WATCH_PER_S_BY_ROBOT",
                 "picture_steps", "watch_rates")


def service(name: str):
    """rcb_rsb_rt.py's own constant or function `name` (SERVICE_NAMES: the picture charge and the watch rates), taken
    from its source (the module imports numpy) and run on the source's defaults: the environment's overrides
    (RCB_RT_PICTURE_COST_S, RCB_RT_WATCH_IMAGES_PER_S, for experiments) are ignored, so a task states what its service
    does by default. No number is copied here."""
    if not _SERVICE:
        import __future__
        import ast
        import math
        import types
        tree = ast.parse((RT / "rcb_rsb_rt.py").read_text())
        body = [n for n in tree.body
                if (isinstance(n, ast.Assign) and [getattr(x, "id", None) for x in n.targets] in ([k] for k in SERVICE_NAMES))
                or (isinstance(n, ast.FunctionDef) and n.name in SERVICE_NAMES)]
        ns = {"math": math, "os": types.SimpleNamespace(environ={})}
        exec(compile(ast.Module(body=body, type_ignores=[]), "rcb_rsb_rt.py", "exec",
                     flags=__future__.annotations.compiler_flag, dont_inherit=True), ns)
        if missing := [k for k in SERVICE_NAMES if k not in ns]:
            raise RuntimeError(f"rcb_rsb_rt.py: {', '.join(missing)} not found")
        _SERVICE.update({k: ns[k] for k in SERVICE_NAMES})
    return _SERVICE[name]


def picture_cost(control_dt: float, robot: str | None = None, camera: str | None = None,
                 depth: bool = False) -> tuple[int, float]:
    """(steps, seconds) one picture is charged: rcb_rsb_rt.picture_steps (a robot's own cost of that camera where
    PICTURE_COST_S_BY_ROBOT has one, else PICTURE_COST_S), rounded up to a whole control step."""
    steps = int(service("picture_steps")(float(control_dt), robot, camera, depth))
    return steps, round(steps * float(control_dt), 4)


def watch_rate(robot: str, camera: str) -> int:
    """A watch's pictures per second of `camera` (rcb_rsb_rt.watch_rates; a robot without rates of its own: the plain
    RT_WATCH_IMAGES_PER_S, which several cameras share in the same way: cameras x video_fps at most that)."""
    return int((service("watch_rates")(robot) or {}).get(camera, service("RT_WATCH_IMAGES_PER_S")))


def watch_text(robot: str, ctl: dict) -> str:
    """@@WATCH_TEXT@@ (README's Clock row): the watch limit, as the arms' tasks have always stated it when the robot has
    no rates of its own."""
    if not service("watch_rates")(robot):
        return f"{service('RT_WATCH_IMAGES_PER_S')} per second in a watch"
    if not any(watch_rate(robot, c) > 0 for c in ctl["cameras"]):    # the walking G1: snapshots only
        return "no watch (snapshots only, each charged its picture cost)"
    return ("in a watch " + ", ".join(f"{watch_rate(robot, c)} per second of `{c}`" for c in ctl["cameras"])
            + ", shared by the watch's cameras")


def picture_table(robot: str, ctl: dict) -> str:
    """@@PICTURE_TABLE@@: what each picture of this instance's cameras (and a depth image) is charged while the clock
    runs, and how many of them a watch may return per second."""
    rows = ["| picture | robot time it costs | control steps | a watch returns at most |", "|---|---|---|---|"]
    for cam, s in ctl["cameras"].items():
        n, sec = picture_cost(ctl["control_dt"], robot, cam)
        rate = watch_rate(robot, cam)
        rows.append(f"| `{cam}` | {G.fmt(sec)} s | {n} | {f'{rate} per second' if rate > 0 else 'none (snapshots only)'} |")
        if s.get("depth"):
            n, sec = picture_cost(ctl["control_dt"], robot, cam, True)
            rows.append(f"| `{cam}`'s depth image (`include_depth=True`) | {G.fmt(sec)} s | {n} | none (no depth in a watch) |")
    return "\n".join(rows)


def task_dir(slug: str, nn: str) -> str:
    return f"{G.PREFIX}-{slug}-{nn}-{MODE}"


def agent_timeout() -> int:
    return G.CUTOFF_SEC[MODE]   # scripts/robosafe/gen_tasks.py: the benchmark's numbers per mode (PROTOCOL §2.12)


def room_rt(robot: str) -> bool:
    """A robot that drives with a realtime instruction of its own (templates/rooms/<robot>/realtime/)."""
    return (G.ROOMS / robot / "realtime" / "instruction.md.tmpl").is_file()


def arms_rt(robot: str) -> dict:
    if room_rt(robot):                                    # its own instruction: no paragraphs to fill in
        return {}
    d = G.ARMS / robot / "realtime"
    if not d.is_dir():
        raise RuntimeError(f"no realtime instruction text for the robot {robot!r} ({d.relative_to(ROOT)})")
    return {f"ARMS_RT_{f.stem}": f.read_text().rstrip("\n") for f in sorted(d.glob("*.md"))}


def rt_fault(slug: str, nn: str, seed: int | None = None, image_id: str | None = None) -> str | None:
    """The selected seed's realtime reference and trivial gates, with no fallback to canonical artifacts."""
    if why := G._own_fault(slug,nn,seed):
        return 'standard prerequisite: '+why
    if why := G.frozen_source_fault(slug,nn,seed,'instances_rt'):
        return why
    data = HERE if seed is None else HERE / "seeds" / str(seed)
    p = data / "oracles_rt" / f"{slug}-{nn}.json"
    if not p.exists():
        return "no reference checked under the realtime clock (make_rt_instances.py)"
    o = G.CI.frozen_fields(json.loads(p.read_text()))
    inst = G.CI.frozen_fields(json.loads((data/'instances_rt'/f'{slug}-{nn}.json').read_text()))
    candidate = G.CI.frozen_fields(json.loads((HERE/'families.json').read_text())).get('candidate_identity')
    if candidate is not None and (inst.get('candidate_identity') != candidate or o.get('candidate_identity') != candidate):
        return 'realtime freeze lacks matching source/digest/visual candidate identity'
    if (o.get('instance_key') != inst['key'] or o.get('start_sha') != inst['state_sha']
            or o.get('robosafebench_commit') != inst['robosafebench_commit']
            or o.get('robosafebench_version') != inst['robosafebench_version']):
        return 'realtime oracle belongs to another frozen instance or source'
    if image_id and any(value.get('robosafebench_image_id', '').removeprefix('sha256:') != image_id.removeprefix('sha256:')
                        for value in (inst, o)):
        return 'realtime freeze lacks matching actual-image identity'
    if not o["result"]["pass"]:
        return f"the reference ends {o['result']['outcome']} under the realtime clock"
    import validation_coverage as V
    selected_policy=V.policy(o)
    if selected_policy and any(not V.exact(o.get(k),v) for k,v in V.declaration(o['validation_policy']).items()):
        return 'Realtime oracle falsely claims omitted validation coverage'
    if o["nop"]["pass"] or (not selected_policy and o["done_at_once"]["pass"]):
        return "a trivial strategy passes under the realtime clock"
    return None


def serves(robot: str, family_id: str) -> bool:
    """make_rt_instances.py's serves(): the robot is a realtime robot and, where REALTIME_ROBOT_FAMILIES lists it, the
    family is one of its own (read from the source, as REALTIME_ROBOTS is)."""
    if robot not in realtime_robots():
        return False
    text = (HERE / "make_rt_instances.py").read_text()
    m = re.search(r"^REALTIME_ROBOT_FAMILIES = \{(.*?)\}\n", text, re.M | re.S)
    own = {r: re.findall(r'"([a-z0-9_]+)"', fams) for r, fams in re.findall(r'"([a-z0-9_]+)":\s*\[(.*?)\]', m.group(1), re.S)} if m else {}
    return robot not in own or family_id in own[robot]


def slowdown(robot: str) -> float:
    """The task's slowdown S: make_rt_instances.py's REALTIME_SLOWDOWN for the robot, else 1 (real time)."""
    text = (HERE / "make_rt_instances.py").read_text()
    m = re.search(r"^REALTIME_SLOWDOWN = \{(.*?)\}", text, re.M | re.S)
    table = dict((k, float(v)) for k, v in re.findall(r'"([a-z0-9_]+)":\s*([0-9.]+)', m.group(1))) if m else {}
    return table.get(robot, 1.0)


def realtime_robots() -> tuple:
    text = (HERE / "make_rt_instances.py").read_text()
    return tuple(re.findall(r'"([a-z0-9_]+)"', re.search(r"^REALTIME_ROBOTS = \((.*?)\)", text, re.M).group(1)))


def served(slug: str, fam: dict, seed: int | None = None) -> list:
    """The members of the family its standard tasks serve (gen_tasks.held_back: the admission's served set, the
    references): the realtime set takes them, never a fixed list."""
    return [nn for nn in fam["instances"]
            if serves(G.robot_of(fam, nn), fam["rsb"]) and G.held_back(slug, nn, fam, seed) is None and hidden_held(fam, nn, seed) is None]


def hidden_held(fam: dict, nn: str, seed: int | None = None) -> str | None:
    """make_rt_instances.py REALTIME_HIDDEN_HELD (read as Python literals: this script needs no simulator)."""
    import ast
    text = (HERE / "make_rt_instances.py").read_text()
    tables = {getattr(n.targets[0], "id", ""): ast.literal_eval(n.value)
              for n in ast.parse(text).body if isinstance(n, ast.Assign)
              and getattr(n.targets[0], "id", "") in ("REALTIME_HIDDEN_HELD", "REALTIME_KEY_HELD")}
    held = tables.get("REALTIME_HIDDEN_HELD", {})
    m = fam["instances"][nn]
    requested_seed = m.get("seed", 0) if seed is None else seed
    if why := tables.get("REALTIME_KEY_HELD", {}).get((fam["rsb"], m["member"], requested_seed, G.robot_of(fam, nn))):
        return why
    if m["member"] != "hazard_hidden":
        return None
    return held.get((fam["rsb"], f"hazard_hidden/{m.get('evidence')}", G.robot_of(fam, nn)))


def held_back(slug: str, nn: str, fam: dict, seed: int | None = None) -> str | None:
    if why := G.held_back(slug, nn, fam, seed) or hidden_held(fam, nn, seed):
        return why
    robot, member = G.robot_of(fam, nn), fam['instances'][nn]
    admission = G.admission(robot)
    entry = G.family_admission(admission, fam, member, clock='realtime')
    paused = G.family_admission(admission, fam, member)
    name = member['member'] + ('/' + member['evidence'] if member.get('evidence') else '')
    requested_seed = member.get('seed', 0) if seed is None else seed
    if (not entry.get('ok') or requested_seed not in entry.get('allowed_seeds', {}).get(name, [])
            or entry.get('candidate_image_id', '').removeprefix('sha256:') != paused.get('candidate_image_id', '').removeprefix('sha256:')):
        return 'no matching exact-source/image full admission under the realtime clock'
    import validation_coverage as V
    if V.policy(entry):
        return rt_fault(slug,nn,seed,image_id=entry['candidate_image_id'])
    for other in served(slug, fam, seed):              # admit each robot independently
        if G.robot_of(fam, other) != robot or fam['instances'][other].get('variant') != member.get('variant'):
            continue
        other_member = fam['instances'][other]
        other_name = other_member['member'] + ('/' + other_member['evidence'] if other_member.get('evidence') else '')
        if requested_seed not in entry.get('allowed_seeds', {}).get(other_name, []):
            continue
        if why := rt_fault(slug, other, seed, image_id=entry['candidate_image_id']):
            return why if other == nn else f"{other} of the family: {why}"
    return None


def plan(slug: str, fam: dict, nn: str, version: str, seed: int | None = None, *, publication=None) -> dict:
    data = HERE if seed is None else HERE / "seeds" / str(seed)
    inst_raw = (data / "instances_rt" / f"{slug}-{nn}.json").read_bytes()
    inst = G.CI.frozen_fields(json.loads(inst_raw))
    std = G.CI.frozen_fields(json.loads((data / "instances" / f"{slug}-{nn}.json").read_text()))
    if seed is not None and (inst["key"]["seed"] != seed or std["key"]["seed"] != seed):
        raise RuntimeError(f"{slug}-{nn}: frozen seed does not match {seed}")
    same_key = {k: v for k, v in inst["key"].items() if k != "max_time_s"} == {**std["key"], "clock": "realtime"}
    if not same_key or inst["task_text"] != std["task_text"]:
        raise RuntimeError(f"instances_rt/{slug}-{nn}.json is not the standard instance under the realtime clock")
    orc = G.CI.frozen_fields(json.loads((data / "oracles" / f"{slug}-{nn}.json").read_text()))
    ort = G.CI.frozen_fields(json.loads((data / "oracles_rt" / f"{slug}-{nn}.json").read_text()))
    if (ort.get("instance_key") != inst["key"] or ort.get("start_sha") != inst["state_sha"]
            or ort.get("robosafebench_commit") != inst["robosafebench_commit"]
            or ort.get('robosafebench_version') != inst['robosafebench_version']):
        raise RuntimeError(f"{slug}-{nn}: realtime oracle belongs to another frozen instance or source")
    if (inst['robosafebench_commit'] != std['robosafebench_commit']
            or inst['robosafebench_version'] != std['robosafebench_version']):
        raise RuntimeError(f'{slug}-{nn}: realtime and standard instances belong to different sources or versions')
    vals = G.values(slug, nn, fam, inst, orc, version, publication)
    robot, ctl = inst["key"]["robot"], inst["control"]
    evidence = (f"RoboSafeBench's scripted reference of this member, compiled into rows of the action types and played "
                f"as chained plans under the realtime clock, passes (make_rt_instances.py, RoboSafeBench "
                f"{inst['robosafebench_version']}); doing nothing and exiting `done` at once fail")
    import validation_coverage as V
    if V.policy(ort):
        evidence = (f"The native reference and do-nothing control for RoboSafeBench {inst['robosafebench_version']} "
                    "were checked, including one independent reference replay: the reference passes and doing "
                    "nothing fails. Other baselines, including done_at_once, are NOT_RUN. Public compiled "
                    "execution is checked separately.")
    vals.update({
        **arms_rt(robot),
        "TASK": task_dir(slug, nn), "STD_TASK": G.task_dir(slug, nn), "AGENT_TIMEOUT": agent_timeout(),
        "ORACLE_EVIDENCE": G.toml_str(evidence), "MAX_CAMERAS": service_limit("RT_CAMERAS"),
        "WATCH_IMAGES": service_limit("RT_WATCH_IMAGES_PER_S"), "ROBOSAFEBENCH_VERSION": inst["robosafebench_version"],
        "PICTURE_STEPS": picture_cost(ctl["control_dt"])[0], "PICTURE_S": G.fmt(picture_cost(ctl["control_dt"])[1]),
        "PICTURE_TABLE": picture_table(robot, ctl), "WATCH_TEXT": watch_text(robot, ctl),
        "SLOWDOWN": G.fmt(slowdown(robot)),
        # README's Clock row: the arms' words where S = 1 (their tasks unchanged), the slowdown where the robot has one
        "CLOCK_TEXT": "real time (`RCB_SLOWDOWN` 1)" if slowdown(robot) == 1 else
                      f"slowdown S = {G.fmt(slowdown(robot))} (`RCB_SLOWDOWN`'s default: one control step every S x control_dt "
                      "of wall time; verdicts are in robot time)",
        # what the robot does when its plan runs out (the service's hold row): a `delta` row of zeros holds it where it
        # is; the arms' position targets hold their last command
        "HOLD_WHAT": "where it is" if "delta" in ctl["action_types"] else "its last command",
    })
    # the arms' realtime paragraphs carry placeholders of their own: fill them first
    vals = {k: (G.fill(v, {x: y for x, y in vals.items() if not x.startswith("ARMS_")}) if k.startswith("ARMS_RT_") else v)
            for k, v in vals.items()}
    room = room_rt(robot)
    files = G.files_of(HERE / "templates/realtime", vals, skip=("instruction.md.tmpl",) if room else ())
    if room:
        files["instruction.md"] = (G.room_instruction(robot, inst["key"]["cameras"], vals, "realtime/instruction.md.tmpl"),
                                   0o644)
    files["environment/rcb_client.py"] = ((RT / "rcb_client.py").read_bytes(), 0o644)
    files["environment/rcb1.py"] = ((STD / "rcb1.py").read_bytes(), 0o644)
    req = G.CLIENT["CLIENT_REQUIREMENTS"].strip()
    files["environment/client-requirements.txt"] = ((ROOT / "scripts/eai_standard" / req).read_bytes(), 0o644)
    for name in G.SIM_FILES:
        files[f"environment/sim/{name}"] = ((STD / name).read_bytes(), 0o644)
    if inst.get('candidate_identity') is not None:
        files['environment/sim/candidate_identity.py'] = ((HERE/'candidate_identity.py').read_bytes(), 0o644)
    for name in SIM_RT:
        files[f"environment/sim/{name}"] = ((RT / name).read_bytes(), 0o644)
    files["environment/sim/instance.json"] = (inst_raw, 0o644)
    files["tests/grade.py"] = ((RT / "grade.py").read_bytes(), 0o644)
    files["tests/grade_rsb.py"] = ((STD / "grade.py").read_bytes(), 0o644)
    files["solution/solve.sh"] = ((RT / "solve.sh").read_bytes(), 0o755)
    files['solution/public_observation_plan.py'] = ((HERE/'public_observation_plan.py').read_bytes(),0o644)
    files['solution/public_observation_delivery.py'] = ((HERE/'public_observation_delivery.py').read_bytes(),0o644)
    files["solution/oracle_rt.py"] = ((RT / "oracle_rt.py").read_bytes(), 0o644)
    public_plan=ort.get("public_plan")
    if public_plan is not None:
        import public_observation_plan as O
        O.validate(public_plan,list(ctl["cameras"]),clock='realtime')
    files["solution/oracle.json"] = (json.dumps(public_plan if public_plan is not None else {"plan":orc["plan"]}).encode()+b"\n",0o644)
    if orc.get("arrays"):
        files["solution/oracle.npz"] = ((data / ("oracles_rt" if public_plan is not None else "oracles") / f"{slug}-{nn}.npz").read_bytes(), 0o644)
    del ort
    return {task_dir(slug, nn): files}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("render", "check"))
    ap.add_argument("--out", default=str(ROOT / "tasks"))
    ap.add_argument("--only", default="", help="comma-separated slugs, default all realtime families")
    ap.add_argument("--seed", type=int, help="render exact admitted frozen seed from seeds/S into a separate --out")
    ap.add_argument('--selection-manifest', type=pathlib.Path, help='pinned full task-ID manifest for a separate local candidate')
    ap.add_argument('--publication-receipt', type=pathlib.Path, help='verified immutable registry transport; never publishes')
    ap.add_argument('--publication-image-proof', type=pathlib.Path, help='independent actual local build receipt')
    a = ap.parse_args()
    registry = G.CI.frozen_fields(json.loads((HERE/'families.json').read_text()))
    if a.selection_manifest is not None:   # local candidate renders use maintainers' release tooling, not kept here
        raise SystemExit('--selection-manifest needs the release tooling, which is not part of this repository')
    publication=__import__('image_publication').from_args(a,registry)
    selected = None
    check = a.cmd == "check"
    out = pathlib.Path(a.out)
    if a.seed is not None and out.resolve() == (ROOT / "tasks").resolve():
        raise SystemExit("--seed renders go elsewhere than tasks/ (--out)")
    data = HERE if a.seed is None else HERE / "seeds" / str(a.seed)
    os.umask(0o022)
    sel = G.CI.frozen_fields(json.loads((HERE / "families.json").read_text()))["families"]
    version = (ROOT / "images/robosafe/VERSION").read_text().strip()
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize
    diffs, made, held = [], set(), []
    only = [x for x in a.only.split(",") if x]
    realtime_slugs = ([slug for slug, fam in sel.items()
                      if any(task_dir(slug, nn) in selected for nn in fam['instances'])]
                     if selected is not None else realtime_set(sel))
    if unknown := sorted(set(only) - set(realtime_slugs)):
        raise SystemExit(f"unknown realtime families: {unknown}")
    for slug in only or realtime_slugs:
        fam = sel[slug]
        for nn in fam["instances"]:
            if selected is not None and task_dir(slug, nn) not in selected:
                continue
            if not serves(G.robot_of(fam, nn), fam["rsb"]):
                continue                                # a robot the realtime set is not served on, or not this family
            if why := G.held_back(slug, nn, fam, a.seed) or hidden_held(fam, nn, a.seed):
                held.append(f"{task_dir(slug, nn)}: {why}")
                continue
            if not (data / "instances_rt" / f"{slug}-{nn}.json").exists():
                diffs.append(f"missing {slug}-{nn}: no realtime instance (make_rt_instances.py)")
                continue
            if why := held_back(slug, nn, fam, a.seed):
                held.append(f"{task_dir(slug, nn)}: {why}")
                continue
            for name, files in G.normalized(plan(slug, fam, nn, version, a.seed, publication=publication), normalize).items():
                made.add(name)
                diffs += G.sync(out / name, files, check)
    for t in sorted(out.glob(f"{G.PREFIX}-*-{MODE}")) if not only and selected is None else ():
        if t.is_dir() and t.name not in made:
            diffs.append(f"stale  {t.name} (no realtime instance for it: remove it)")
    for d in diffs:
        print(d)
    for h in held:
        print("held back", h)
    print(f"{'checked' if check else 'generated'} {len(made)} RoboSafeBench standard-realtime task dirs "
          f"({len(held)} held back): {len(diffs)} difference(s)")
    if selected is not None and made != selected:
        print("selected tasks remain held or missing:", sorted(selected - made))
        return 1
    return 1 if (check and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
