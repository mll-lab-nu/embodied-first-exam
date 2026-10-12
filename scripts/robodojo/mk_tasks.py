#!/usr/bin/env python3
"""Generate the RoboDojo tasks: tasks/robodojo-<task>-iNN-privileged (and, once its service exists, -standard) for every
task of RoboDojo's simulation benchmark (42 tasks + the 12 `_random` generalisation variants) with a frozen instance in
scripts/robodojo/frozen/<task>-iNN/.

    python3 scripts/robodojo/mk_tasks.py              # (re)write every RoboDojo task dir; `git diff tasks/` stays empty
    python3 scripts/robodojo/mk_tasks.py --check      # write nothing; exit 1 if a task dir differs from the generator's
Then `cd tasks && harbor add --scan .` when a digest changed. Needs only Python 3 (no simulator).

Inputs, all in the repository:
  scripts/robodojo/dimensions.json          RoboDojo's five capability dimensions and their tasks (its documentation)
  scripts/robodojo/descr/<task>.json        what the task asks and exactly what its check tests, written from RoboDojo's code
  scripts/robodojo/frozen/<task>-iNN/       instance.json: RoboDojo's evaluation layout, frozen (rcb_robodojo.py make-instance)
  scripts/robodojo/shared/rcb_robodojo.py   the tooling (privileged environment/ + tests/)
  scripts/robodojo/template/<mode>/         every other task file; a *.tmpl file is filled with the instance's values (@@KEY@@)
  images/robodojo/VERSION                   the base image tag
Every task dir is written to a scratch directory, passed through scripts/task_conventions.py's normalize() and then synced
into tasks/: a task dir holds exactly what the generator writes."""
from __future__ import annotations
import argparse, json, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "scripts/robodojo"
OVERRIDES = json.loads((HERE / "instance_overrides.json").read_text())   # per-task determinism class, physics, change log
REGISTRY = "ghcr.io/mll-lab-nu"
MODES = ("privileged", "standard")
LAYER = ROOT / "scripts/eai_standard"
CLIENT = dict(l.split("=", 1) for l in (LAYER / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#"))

CONVENTIONS = """- World frame: RoboDojo's env frame, metres; quaternions are **WXYZ**. @@FRAME@@
- Action (14): `[left joint1..6, left gripper, right joint1..6, right gripper]`, RoboDojo's joint action. Joints: absolute
  position targets (rad); RoboDojo's controller moves each arm from where it is to the new target over the action's 10
  physics steps (linear for 8, then holding). Gripper: RoboDojo's normalised command, clipped to 0..1 (@@GRIPPER@@).
  `s.hold_action()` keeps the current targets.
- Control runs at 25 Hz (physics dt 4 ms, 10 physics steps per action). Your wall-clock budget is 90 min (5400 s); there is
  no step budget.
- One `Session` per process (@@STARTUP@@). Rendering happens only when a frame is asked for and never moves anything. Do
  not call `s.close()` before writing every output."""


def toml_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def base(task: str, i: int) -> str:
    return f"robodojo-{task.lower().replace('_', '-')}-i{i:02d}"


def normalizer():
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize
    return normalize


def fill(text: str, values: dict) -> str:
    for k, v in values.items():
        text = text.replace(f"@@{k}@@", v)
    if "@@" in text:
        raise RuntimeError(f"unfilled placeholder near {text[text.index('@@'):][:40]!r}")
    return text


def bullets(items) -> str:
    return "".join(f"- {x}\n" for x in items)


def none_ish(x) -> bool:
    return not x or str(x).strip().lower().startswith(("none", "n/a"))


def dimension_of(task: str, dims: dict) -> str:
    for d, ts in dims.items():
        if task in ts or task.removesuffix("_random") in ts:
            return d + (" (randomised variant: other models, clutter)" if task.endswith("_random") else "")
    raise KeyError(task)


def plan_instance(task: str, i: int, D: dict, dims: dict, conv: dict, version: str) -> dict[str, dict[str, tuple[bytes, int]]]:
    fz = HERE / "frozen" / f"{task}-i{i:02d}"
    inst_b = (fz / "instance.json").read_bytes(); I = json.loads(inst_b)
    if I.get("task") != task:
        raise RuntimeError(f"{fz}: instance.json is for {I.get('task')}")
    tool = (HERE / "shared/rcb_robodojo.py").read_bytes()
    image = f"{REGISTRY}/eai-robodojo:{version}"
    dim = dimension_of(task, dims)
    goal = D["goal"].strip()
    extra = []
    if not none_ish(D.get("scene_dynamics")):
        extra.append(f"**What changes by itself.** {D['scene_dynamics']}")
    if not none_ish(D.get("needs_memory_or_language")):
        extra.append(f"**What you must read or remember.** {D['needs_memory_or_language']}")
    if not none_ish(D.get("end_requirements")):
        extra.append(f"**At the end.** {D['end_requirements']}")
    if not none_ish(D.get("notes")):
        extra.append(f"**Notes from RoboDojo's code.** {D['notes']}")
    objects = ("The scene's labelled objects (RoboDojo's labels; `s.objects()` gives their poses and bounding boxes):\n"
               + bullets(D.get("objects") or []))
    step_lim = int(I["step_lim"])
    common = {"TASK": task, "PRIV": f"{base(task, i)}-privileged", "STD": f"{base(task, i)}-standard", "INST": f"i{i:02d}",
              "IMAGE": image, "DIMENSION": dim, "LAYOUT_FILE": I["layout_file"].removeprefix("Assets/Eval_Layout/RoboDojo/"),
              "LAYOUT_SHA": I["layout_sha256"][:16], "STEP_LIM": str(step_lim), "STEP_LIM_S": f"{step_lim / 25:.0f}",
              "GOAL_TOML": toml_str("Task: " + goal), "STARTUP": conv["STARTUP"], "CLIENT_IMAGE": CLIENT["CLIENT_IMAGE"].strip(),
              "FRAME": conv["FRAME"]}
    rule = (f" (both replays must succeed; their end states may differ: {I.get('determinism_why')})" if I.get("determinism") == "verdict"
            else " and both end in the same state")
    readme_rule = (f" (determinism by verdict: `instance.json` sets `\"determinism\": \"verdict\"` because "
                   f"{I.get('determinism_why')}; the end states' hashes are reported as `state_identical`)"
                   if I.get("determinism") == "verdict" else " and both end in the same state hash")
    common["README_RULE"] = readme_rule
    # A task whose physics does not replay bit for bit (instance.json "determinism": "verdict") has no privileged twin: an
    # open-loop trajectory of it cannot be graded reproducibly. Its standard twin is graded by the live episode the trusted
    # service ran (success = live_success); the two fresh-process replays are recorded and never decide.
    live = I.get("determinism") == "verdict"
    modes = ("standard",) if live else MODES
    priv_ref = f"`{base(task, i)}-privileged`"
    common["STD_INTRO"] = (f"Standard-only task (no privileged twin: its physics does not replay bit for bit, so an open-loop "
                           f"trajectory cannot be graded reproducibly; RoboDojo's `{common['LAYOUT_FILE']}`)." if live else
                           f"Standard-mode twin of {priv_ref} (same frozen layout, RoboDojo's `{common['LAYOUT_FILE']}`).")
    common["ORACLE_SEE"] = "None:" if live else "None (see the privileged twin):"
    # task.toml's description (the task list shows it): no privileged task to name, and what decides
    common["TOML_LAYOUT"] = (f"on RoboDojo's frozen layout ({common['LAYOUT_FILE']}); standard only, no privileged twin." if live else
                             f"on the same frozen layout as the privileged task ({common['LAYOUT_FILE']}).")
    common["TOML_GRADING"] = ("the sim service records the episode and grades it as it happened live (the physics does not "
                              "replay bit for bit; the two replays are recorded only)." if live else
                              "the sim service records the episode as a trajectory and grades it.")
    common["STD_VERDICT"] = (f"the live episode succeeded: this task is graded by its live episode, which the trusted service "
                             f"ran (`instance.json` sets `\"determinism\": \"verdict\"` because {I.get('determinism_why')}); "
                             f"the two replays are recorded (`replay_success`, `state_identical`, `deterministic`) and never "
                             f"decide" if live else "the live episode succeeded and both replays succeed" + readme_rule)
    common["LIVE_NOTE"] = (f"\n- **Graded on your live episode.** This task's physics does not replay bit for bit "
                           f"({I.get('determinism_why')}), so the episode as it happened in the service decides; the service "
                           f"still replays it twice for the record." if live else "")
    # Change Log (PROTOCOL §2.8): per-task entries of instance_overrides.json "change_log", the last section of both READMEs
    log = OVERRIDES.get(task, {}).get("change_log") or []
    common["CHANGE_LOG"] = ("\n### Change Log\n" + "".join(f"- {x}\n" for x in log)) if log else ""
    MT = json.loads((HERE / "model_trials.json").read_text())
    tr = MT["trials"].get(task, {})
    run = f"Codex + GPT-6 Luna, effort xhigh, run `{MT['run']}`, {MT['date']}"
    def evidence(mode):
        own, other = tr.get(mode), tr.get("standard" if mode == "privileged" else "privileged")
        if own and own.get("success"):
            return (f"positive example: a model trial solved this task ({run}; {own.get('actions')} actions, graded by this "
                    f"verifier); no reference solution (RoboDojo releases no expert)")
        bits = []
        if own:
            bits.append(f"a model trial failed ({run})")
        if other and other.get("success"):
            bits.append(f"the {'standard' if mode == 'privileged' else 'privileged'} twin has a positive example ({run})")
        return ("no positive example yet" + (" (" + "; ".join(bits) + ")" if bits else "") + "; no reference solution (RoboDojo "
                "releases no expert, and its training demonstrations carry no initial state); reported separately until one exists")
    common["REVIEW_PR"] = str(MT["review_pr"] or "TBD")
    priv = {"GOAL": goal, "INSTRUCTION": I.get("instruction") or "", "OBJECTS_BLOCK": objects, "REPLAY_RULE": rule,
            "SUCCESS_BLOCK": bullets(D["success"]), "EVALUATION": D["evaluation"].strip(),
            "EXTRA_BLOCK": ("\n" + "\n\n".join(extra) + "\n") if extra else "",
            "CONVENTIONS": fill(CONVENTIONS, conv), "README_GOAL": f"{goal} (RoboDojo's `{task}`).",
            "DIFFICULTY": (f"A RoboDojo {dim} task ({D.get('physics_kind', 'rigid')} objects), graded by RoboDojo's own success "
                           f"thresholds (its evaluation gives a policy {step_lim} actions; no step cap here, PROTOCOL D1).")}
    out: dict[str, dict[str, tuple[bytes, int]]] = {}
    priv_frame = "`s.proprio()` gives each arm's end-effector pose in this frame."
    assert conv["FRAME"].endswith(priv_frame)
    for mode in modes:
        ev = evidence(mode)
        # standard mode has no Session: its proprioception names the same poses
        common["FRAME"] = conv["FRAME"] if mode == "privileged" else conv["FRAME"].replace(
            priv_frame, "The proprio `tcp_pose` columns give each arm's link6 (end-effector) pose in this frame.")
        common["ORACLE_EVIDENCE"] = toml_str(ev + f"; human review in PR #{common['REVIEW_PR']}")
        common["EVIDENCE_SHORT"] = ("a model trial solved it" if ev.startswith("positive") else "no positive example yet")
        files: dict[str, tuple[bytes, int]] = {}
        tdir = HERE / "template" / mode
        for p in sorted(tdir.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            rel = p.relative_to(tdir).as_posix()
            if rel.endswith(".tmpl"):
                rel = rel[:-5]; data = fill(p.read_text(), {**common, **priv}).encode()
            else:
                data = p.read_bytes()
            files[rel] = (data, 0o755 if rel.endswith(".sh") else 0o644)
        if mode == "privileged":
            for rel in ("environment/rcb_robodojo.py", "tests/rcb_robodojo.py"):
                files[rel] = (tool, 0o644)
            for rel in ("environment/instance.json", "tests/instance.json"):
                files[rel] = (inst_b, 0o644)
        else:
            files["environment/sim/rcb_robodojo.py"] = (tool, 0o644)
            files["environment/sim/instance.json"] = (inst_b, 0o644)
            for rel, src in (("environment/rcb_client.py", "rcb_client.py"), ("environment/rcb1.py", "rcb1.py"),
                             ("environment/sim/rcb_limited.py", "rcb_limited.py"), ("environment/sim/rcb1.py", "rcb1.py"),
                             ("environment/sim/run.sh", "run.sh")):
                files[rel] = ((LAYER / src).read_bytes(), 0o755 if rel.endswith(".sh") else 0o644)
            req = CLIENT.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip()
            files["environment/client-requirements.txt"] = ((LAYER / req).read_bytes(), 0o644)
        out[f"{base(task, i)}-{mode}"] = files
    return out


def normalized(planned: dict[str, dict[str, tuple[bytes, int]]], normalize) -> dict[str, dict[str, tuple[bytes, int]]]:
    out = {}
    with tempfile.TemporaryDirectory(prefix="robodojo_mk_") as td:
        for name, files in planned.items():
            for rel, (data, mode) in files.items():
                p = pathlib.Path(td) / name / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
                os.chmod(p, 0o755 if mode & 0o100 else 0o644)
        for name in planned:
            normalize(pathlib.Path(td) / name)
        for name in planned:
            t = pathlib.Path(td) / name
            out[name] = {p.relative_to(t).as_posix(): (p.read_bytes(), 0o755 if p.stat().st_mode & 0o100 else 0o644)
                         for p in sorted(t.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}
    return out


def sync(task: pathlib.Path, files: dict, check: bool) -> list[str]:
    diffs = []
    have = {p.relative_to(task).as_posix() for p in task.rglob("*") if p.is_file() or p.is_symlink()} if task.exists() else set()
    have = {h for h in have if "__pycache__" not in h.split("/")}
    for rel in sorted(have - set(files)):
        diffs.append(f"remove {task.name}/{rel}")
        if not check:
            (task / rel).unlink()
    for rel, (data, mode) in sorted(files.items()):
        p = task / rel
        same = p.is_file() and not p.is_symlink() and p.read_bytes() == data and bool(p.stat().st_mode & 0o100) == bool(mode & 0o100)
        if not same:
            diffs.append(f"write  {task.name}/{rel}")
            if not check:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                m = p.stat().st_mode & 0o777
                os.chmod(p, m | 0o111 if mode & 0o100 else m & ~0o111)
    if not check and task.exists():
        for d in sorted((p for p in task.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
            if not any(d.iterdir()):
                d.rmdir()
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    dims = json.loads((HERE / "dimensions.json").read_text())
    conv = json.loads((HERE / "conventions.json").read_text())
    version = (ROOT / "images/robodojo/VERSION").read_text().strip()
    normalize = normalizer()
    diffs, made, missing = [], set(), []
    for dpath in sorted((HERE / "descr").glob("*.json")):
        D = json.loads(dpath.read_text()); task = D["task"]
        frozen = sorted((HERE / "frozen").glob(f"{task}-i[0-9][0-9]"))
        if not frozen:
            missing.append(task); continue
        for fz in frozen:
            i = int(fz.name[-2:])
            for name, files in normalized(plan_instance(task, i, D, dims, conv, version), normalize).items():
                made.add(name); diffs += sync(ROOT / "tasks" / name, files, a.check)
    for t in sorted((ROOT / "tasks").glob("robodojo-*")):
        if t.is_dir() and t.name not in made:
            diffs.append(f"stale  {t.name} (not generated: no frozen instance, or the privileged twin of a standard-only task)")
    for d in diffs:
        print(d)
    if missing:
        print(f"no frozen instance yet: {' '.join(missing)}")
    print(f"{'checked' if a.check else 'generated'} {len(made)} RoboDojo task dirs: {len(diffs)} difference(s)")
    return 1 if (a.check and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
