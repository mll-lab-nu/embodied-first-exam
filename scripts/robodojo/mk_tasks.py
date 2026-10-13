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
# The agent's time limit is not this generator's: scripts/task_cutoffs.toml is the one table (docs/PROTOCOL.md §2.12), and
# scripts/task_conventions.py (normalize) writes `[agent] timeout_sec`, the instruction's closing `## Time limit` section,
# the README row and the standard service's RCB_WALL_CLOCK_S from it (ci_checks/check-cutoffs.py compares). What is
# rendered here takes the number from the same table (agent_timeout) and the instruction's own text names none: CUTOFF
# is what RoboDojo adds to the closing `## Time limit` section, placed right after the task's introduction.
CUTOFF = {
    "privileged": """`/app/output/trajectory.npz` must be written before the time limit (`## Time limit`) is up: save a working
trajectory as soon as you have one and overwrite it as you improve it. Every Python process that opens a `Session` first
spends @@STARTUP@@ launching Isaac Sim and building the scene, and that time counts.""",
    "standard": """Nothing is handed in, so the task must be completed before the time limit (`## Time limit`) is up (the episode
ends by itself when RoboDojo's check passes: `res.meta["done"]`). The time you wait for the service counts: its first
start in a trial takes ~4-15 min (Client, below).""",
}
# One replay (owner, 2026-10-12; docs/benchmarks/robodojo.md Grading): the Change Log entry of every task. A standard
# task graded by its live episode gets ONE_REPLAY_LIVE instead (plan_instance).
ONE_REPLAY = {
    "privileged": ("2026-10-12: graded by ONE fresh-process replay (two before; owner decision, docs/benchmarks/robodojo.md): "
                   "reward 1 iff that replay ends in RoboDojo's success. Before, both replays had to succeed and end in the same "
                   "state hash; with one replay nothing is compared, so `reward.json` reports `deterministic` = 1 with "
                   "`determinism_checked` = 0 and `replays` = 1, and a replay whose process did not rebuild the frozen layout "
                   "to its recorded hash gives no verdict (`instance_mismatch`, `infra_error`). `[verifier] timeout_sec` 15000 s "
                   "-> 7800 s (one replay of the 15,000 rows a trajectory may have, 7200 s, + 600 s). The scene, the frozen layout, "
                   "RoboDojo's success check and what the agent hands in are unchanged, so the task keeps its name; "
                   "`instruction.md` says one replay. No ranked result exists; a trial graded before this date is re-read from "
                   "its saved `reward.json` (`all_success`, `state_identical`), not rerun: in the first 38 graded trials of the run "
                   "that began on 2026-10-11 the two replays always ended in the same state, and no verdict changes."),
    "standard": ("2026-10-12: graded with ONE fresh-process replay of the recorded episode (two before; owner decision, "
                 "docs/benchmarks/robodojo.md): `success` = `live_success` and `replay_success`, one successful replay is enough. "
                 "Before, two replays had to succeed and end in the same state hash. `deterministic` (= `state_identical` = "
                 "`live_matches_replay`) now says whether the replay ended in the live episode's state; it is reported and no "
                 "longer decides. The collect hook's limit 18000 s -> 10800 s (`[[verifier.collect]] timeout_sec` = "
                 "`finalize.sh`'s `HOOK_BUDGET_S`); inside it the replay has max(1800 s, 1200 s + actions / 2.5) and is run once "
                 "more when it gives no result in that time. The scene, the frozen layout, RoboDojo's success check and the service the "
                 "agent talks to are unchanged, so the task keeps its name. No ranked result exists; a trial graded before "
                 "this date is re-read from its saved `reward.json` (`live_success`, `replay_success`, `state_identical`), not "
                 "rerun: in the first 38 graded trials of the run that began on 2026-10-11 no verdict changes."),
}
ONE_REPLAY_LIVE = ("2026-10-12: the collect hook replays the episode ONCE in a fresh process (twice before; owner decision, "
                   "docs/benchmarks/robodojo.md). The verdict is unchanged, the live episode's (`success` = `live_success`); the "
                   "replay is recorded (`replay_success`; `state_identical`: it ended in the live episode's state; "
                   "`deterministic`: it reached the live episode's verdict) and never decides. The collect hook's limit 18000 s "
                   "-> 10800 s; inside it the replay has max(1800 s, 1200 s + actions / 2.5). No trial needs a rerun.")
CHANGE_LOG_ALL = {   # README Change Log entries of every task (PROTOCOL §2.8), after the task's own (instance_overrides.json)
    "privileged": ["2026-10-11: agent time limit 5400 s -> 3600 s (`[agent] timeout_sec`; owner decision, "
                   "docs/benchmarks/robodojo.md), and `instruction.md` states the cutoff at the top. The scene, the frozen layout, "
                   "RoboDojo's success check and the verifier are unchanged, so the task keeps its name; trials recorded before "
                   "this date ran with 5400 s and are kept apart (no official result was published with it).",
                   ONE_REPLAY["privileged"]],
    "standard": ["2026-10-11: agent time limit 5400 s -> 3600 s (`[agent] timeout_sec`, and the service's "
                 "`RCB_WALL_CLOCK_S`, which only reports it: `spec[\"budget\"]`, `meta[\"time_left_s\"]`; owner decision, "
                 "docs/benchmarks/robodojo.md), and `instruction.md` states the cutoff at the top. The scene, the frozen layout, "
                 "RoboDojo's success check, the collect hook and the verifier are unchanged, so the task keeps its name; trials "
                 "recorded before this date ran with 5400 s and are kept apart (no official result was published with it).",
                 ONE_REPLAY["standard"],
                 "2026-10-13 (owner, boards 0085 and 0087): the sim service's clock "
                 "(`environment/sim/rcb_limited.py`, `environment/sim/server.py`, the docstring of "
                 "`environment/rcb_client.py`). `meta[\"time_s\"]` and `meta[\"time_left_s\"]` count from the agent's "
                 "first request to the service (any endpoint), and a restarted service keeps that moment; before, "
                 "they counted from the service's own start of the episode (when its scene was ready). Where the "
                 "service is ready before the agent's phase begins (the harness is installed in between: a median of "
                 "79 s over the recorded standard trials), that clock ran ahead of the agent's and `time_left_s` "
                 "reached 0 while the agent still had that time. `/spec` says what the clock counts from "
                 "(`budget.clock`), and the instruction's `## Time limit` tells the agent to plan by `time_left_s`. "
                 "The service never ended an episode on this clock: the scene, the frozen instance, the pass rule "
                 "and the grader are unchanged, so the task keeps its name and earlier results stand."],
}
REGISTRY = "ghcr.io/mll-lab-nu"
MODES = ("privileged", "standard")
LAYER = ROOT / "scripts/eai_standard"
CLIENT = dict(l.split("=", 1) for l in (LAYER / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#"))

CONVENTIONS = """- World frame: RoboDojo's env frame, metres; quaternions are **WXYZ**. @@FRAME@@
- Action (14): `[left joint1..6, left gripper, right joint1..6, right gripper]`, RoboDojo's joint action. Joints: absolute
  position targets (rad); RoboDojo's controller moves each arm from where it is to the new target over the action's 10
  physics steps (linear for 8, then holding). Gripper: RoboDojo's normalised command, clipped to 0..1 (@@GRIPPER@@).
  `s.hold_action()` keeps the current targets.
- Control runs at 25 Hz (physics dt 4 ms, 10 physics steps per action). There is no step budget: the time limit
  (`## Time limit`) is your only budget.
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


def agent_timeout(mode: str) -> int:
    """The agent's cutoff of a mode in seconds, from the one table (scripts/task_cutoffs.toml)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import cutoff_sec
    return cutoff_sec("RoboDojo", mode)


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
    # ONE fresh-process replay decides (owner, 2026-10-12): no second replay, so no end-state comparison in privileged mode
    readme_rule = (" (one replay since 2026-10-12, the owner's decision: before, two replays that also had to end in the same "
                   "state hash; `deterministic` is reported as 1 with `determinism_checked` = 0, and a replay that did not "
                   "start from the frozen layout's recorded state hash is `instance_mismatch`, no verdict)")
    common["README_RULE"] = readme_rule
    # A task whose physics does not replay bit for bit (instance.json "determinism": "verdict") has no privileged twin: an
    # open-loop trajectory of it cannot be graded reproducibly. Its standard twin is graded by the live episode the trusted
    # service ran (success = live_success); its one fresh-process replay is recorded and never decides.
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
                              "replay bit for bit; the replay is recorded only)." if live else
                              "the sim service records the episode as a trajectory and grades it.")
    common["STD_VERDICT"] = (f"the live episode succeeded: this task is graded by its live episode, which the trusted service "
                             f"ran (`instance.json` sets `\"determinism\": \"verdict\"` because {I.get('determinism_why')}); "
                             f"the replay is recorded (`replay_success`, `state_identical`, `deterministic`) and never "
                             f"decides" if live else
                             "the live episode succeeded and the replay succeeds (`success` = `live_success` and "
                             "`replay_success`: one successful replay is enough, the owner's decision of 2026-10-12; whether the "
                             "replay ended in the live episode's state is reported as `deterministic` = `state_identical` = "
                             "`live_matches_replay` and does not decide)")
    common["LIVE_NOTE"] = (f"\n- **Graded on your live episode.** This task's physics does not replay bit for bit "
                           f"({I.get('determinism_why')}), so the episode as it happened in the service decides; the service "
                           f"still replays it once for the record." if live else "")
    # Change Log (PROTOCOL §2.8): per-task entries of instance_overrides.json "change_log", the last section of both READMEs
    log = OVERRIDES.get(task, {}).get("change_log") or []
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
    priv = {"GOAL": goal, "INSTRUCTION": I.get("instruction") or "", "OBJECTS_BLOCK": objects,
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
        common["CUTOFF"] = fill(CUTOFF[mode], {"STARTUP": conv["STARTUP"]})
        common["AGENT_TIMEOUT_S"] = str(agent_timeout(mode))
        every = [ONE_REPLAY_LIVE if (live and x is ONE_REPLAY["standard"]) else x for x in CHANGE_LOG_ALL[mode]]
        common["CHANGE_LOG"] = "\n### Change Log\n" + "".join(f"- {x}\n" for x in log + every)
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
