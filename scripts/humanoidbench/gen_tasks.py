#!/usr/bin/env python3
"""Generate the HumanoidBench Harbor task directories from a single source of truth.

Harbor tasks are self-contained by design: each one carries its own copy of the tooling, the verifier and
the frozen scene. Copying by hand is how thirteen tasks end up with eleven slightly different verifiers,
so the copies are made here instead. `subset.toml` holds what a human decided (which tasks, why, how to
describe them), `facts.json` holds what the simulator says (bars, dimensions, floors), `templates/` holds
everything the tasks have in common, and `shared/` holds the one real copy of `rcb_hb.py` and `grade.py`.
`ci_checks/check-tooling-sync.sh` fails the build if a task directory drifts from any of it.

    ./gen_tasks.py status                 # what exists, what is verified          (no simulator needed)
    ./gen_tasks.py render [family ...]    # write/refresh task dirs, minus instances (no simulator)
    ./gen_tasks.py measure [family ...]   # read bars/dims/floors into facts.json  (needs mujoco)
    ./gen_tasks.py instance [family ...]  # write environment/ + tests/ instance.npz (needs mujoco)
    ./gen_tasks.py verify [family ...]    # re-measure and fail on drift           (needs mujoco)
    ./gen_tasks.py measure-limited [family ...]  # check + time the limited twins' sim service (needs a GPU)

`render` is deliberately the only command that writes into tasks/, and it is idempotent: run it after
editing a template or a prose field and every task picks the change up at once.

Needs Python 3.11+ (tomllib). The simulator commands need `humanoid_bench` importable -- inside the
base image, or in a venv built the way images/humanoidbench/Dockerfile builds one.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import textwrap
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent                       # repo root
TASKS_DIR = ROOT / "tasks"
SUBSET = HERE / "subset.toml"
FACTS = HERE / "facts.json"
REWARDS = HERE / "rewards.json"   # the scoring formulas, kept out of the image (see shared/rcb_rewards.py)

# robot id -> (how instruction.md names it, task.toml's metadata.robot)
ROBOTS = {
    "h1": ("Unitree H1 humanoid", "unitree-h1"),
    "h1hand": ("Unitree H1 humanoid with two Shadow dexterous hands", "unitree-h1hand"),
}
CATEGORY_LONG = {"loco": "locomotion", "manip": "manipulation"}

# Prose fields that land in the middle of a sentence. They are written across several lines in
# subset.toml for readability, so their line breaks are collapsed before substitution.
INLINE_FIELDS = ("one_liner", "task_statement", "scene_note", "scoring_note", "obs_layout", "evidence",
                 "instance_note", "completion_rate", "capability_class")

NO_ORACLE = """No reference solution, on purpose. Requiring one would cap the benchmark at what we can
already solve, which systematically removes the interesting tasks — see `local_docs/plan/01-design.md`
§D. `solution/solve.sh` exists because the Harbor task contract requires it and exits non-zero with that
explanation. What replaces an oracle is the floor above: the task is known to be unreachable by doing
nothing, and known to be solvable by *something*."""


# --------------------------------------------------------------------------- source of truth
def load_subset() -> tuple[dict, dict[str, dict]]:
    d = tomllib.loads(SUBSET.read_text())
    return d["defaults"], {t["family"]: t for t in d["task"]}


def load_rewards() -> dict[str, dict]:
    """The reward source lifted from upstream, per family. Regenerate with extract_rewards.py."""
    return json.loads(REWARDS.read_text())


def load_facts() -> dict[str, dict]:
    return json.loads(FACTS.read_text()) if FACTS.exists() else {}


def image_tag() -> str:
    return (ROOT / "images" / "VERSION").read_text().strip()


def task_dir_name(t: dict, instance_tag: str) -> str:
    return f"humanoidbench-{t['paper_category']}-{t['family'].replace('_', '-')}-i{instance_tag}"


def instance_path(t: dict, defaults: dict) -> Path:
    return TASKS_DIR / task_dir_name(t, defaults["instance_tag"]) / "environment" / "instance.npz"


def select(families: list[str], tasks: dict[str, dict]) -> list[dict]:
    if not families:
        return list(tasks.values())
    unknown = [f for f in families if f not in tasks]
    if unknown:
        sys.exit(f"unknown families: {unknown}; known: {sorted(tasks)}")
    return [tasks[f] for f in families]


# --------------------------------------------------------------------------- rendering
def fill(template: str, ctx: dict) -> str:
    """Replace every {{key}} with ctx[key]. Unknown keys are an error, not an empty string: a silently
    dropped placeholder is exactly the kind of drift this file exists to prevent."""
    missing: list[str] = []

    def one(m: re.Match) -> str:
        key = m.group(1)
        if key not in ctx:
            missing.append(key)
            return m.group(0)
        return str(ctx[key])

    out = re.sub(r"\{\{(\w+)\}\}", one, template)
    if missing:
        raise KeyError(f"template placeholders with no value: {sorted(set(missing))}")
    return out


def actuator_layout(names: list[str]) -> str:
    """Describe the action vector from the model's own actuator names.

    Written from the model rather than by hand because the naive description is wrong: h1hand does not
    put all 19 body actuators first, it inserts a wrist yaw into each arm before the fingers begin.
    """
    hand_at = next((i for i, n in enumerate(names) if n.startswith(("lh_", "rh_"))), len(names))
    body, hands = names[:hand_at], names[hand_at:]
    listed = ", ".join(f"`{n}`" for n in body)
    if hands:
        text = (f"The {len(names)} actuators are position servos. The first {len(body)} are the body, in "
                f"this order: {listed}. The remaining {len(hands)} are the fingers, {len(hands) // 2} per "
                f"Shadow hand — `lh_A_*` then `rh_A_*`.")
    else:
        text = f"The {len(names)} actuators are position servos, in this order: {listed}."
    return text + (" A constant action commands joint *targets*, not a pose: whether the robot stays "
                   "there depends on whether that pose is stable under gravity and contact.")


def rewrap(md: str, width: int = 100, items: bool = False) -> str:
    """Re-flow ordinary prose paragraphs to a fixed width.

    Prose arrives here from several fields of different shapes, so without this the generated markdown is
    ragged in a way that makes real diffs hard to see. Only plain paragraphs are touched: fenced code,
    tables, headings, lists and block quotes are emitted exactly as written. `items=True` (the limited-mode
    templates, whose rules are a list with per-task clauses) also re-flows each `- ` list item, and never
    breaks a line inside `inline code`.
    """
    STRUCTURAL = re.compile(r"\s*([-*+]\s|\d+\.\s|\||>|```)")

    def fill(text: str, indent: str = "") -> str:
        text = " ".join(text.split())
        if items:   # keep `reason = "success"` on one line
            text = re.sub(r"`[^`]*`", lambda m: m.group(0).replace(" ", "\0"), text)
        return textwrap.fill(text, width, subsequent_indent=indent, break_long_words=False,
                             break_on_hyphens=False).replace("\0", " ")

    def fill_items(lines: list[str]) -> str:
        out, item = [], None
        for ln in lines + [""]:
            if item is not None and ln.startswith("  "):
                item += " " + ln
                continue
            if item is not None:
                out.append(fill(item, "  "))
                item = None
            if ln.startswith("- "):
                item = ln
            elif ln:
                out.append(ln)
        return "\n".join(out)

    out, fenced = [], False
    for block in md.split("\n\n"):
        if fenced or block.startswith("```"):
            fenced = fenced != (block.count("```") % 2 == 1)
            out.append(block)
            continue
        lines = block.split("\n")
        if items and any(ln.startswith("- ") for ln in lines) and not any(ln.startswith(("|", "```")) for ln in lines):
            out.append(fill_items(lines))
            continue
        if any(STRUCTURAL.match(ln) or ln.startswith(("    ", "\t")) for ln in lines):
            out.append(block)                       # tables and lists have layout we must not reflow
            continue
        head = [ln for ln in lines if ln.startswith("#")]   # a heading glued to its paragraph
        body = " ".join(lines[len(head):])
        out.append("\n".join(head + ([fill(body)] if body.strip() else [])))
    return "\n\n".join(out)


def context(t: dict, defaults: dict, facts: dict) -> dict:
    robot_label, robot_slug = ROBOTS[t["robot"]]
    tag = defaults["instance_tag"]
    keywords = defaults["keywords"] + [t["robot"], CATEGORY_LONG[t["paper_category"]], t["family"]]
    difficulty = t["difficulty"]
    if t.get("caveat"):
        difficulty += "\n\n" + t["caveat"]
    if t.get("retire_when"):
        difficulty += "\n\n⏳ **Scheduled for removal.** " + t["retire_when"]
    nop_note = ""
    if facts["nop_steps"] < facts["max_steps"]:
        nop_note = f" (the episode terminates at step {facts['nop_steps']} of {facts['max_steps']})"
    if t.get("instance_note"):
        nop_note += f". {t['instance_note'][0].upper()}{t['instance_note'][1:]}"
    ctx = {
        **{k: (" ".join(v.split()) if k in INLINE_FIELDS and isinstance(v, str) else v)
           for k, v in t.items() if isinstance(v, (str, int, float))},
        **facts,
        "task_dir": task_dir_name(t, tag),
        "instance_tag": tag,
        "seed": defaults["seed"],
        "agent_timeout": t.get("agent_timeout", defaults["agent_timeout"]),
        # instruction.md states the wall-clock budget, because the first real agent run spent its whole
        # hour searching and timed out with nothing under /app/output/ -- a zero that measures our task
        # description, not the task.
        "agent_timeout_hours": f"{float(t.get('agent_timeout', defaults['agent_timeout'])) / 3600:g}",
        "verifier_timeout": t.get("verifier_timeout", defaults["verifier_timeout"]),
        "robot_label": robot_label,
        "robot_slug": robot_slug,
        "paper_category_long": CATEGORY_LONG[t["paper_category"]],
        "image_tag": image_tag(),
        "keywords": ", ".join(f'"{k}"' for k in keywords),
        "actuator_layout": actuator_layout(facts["actuator_names"]),
        "difficulty": difficulty,
        "nop_note": nop_note,
        "oracle_file": t.get("oracle", ""),
        "reference_solution": t.get("reference_solution", NO_ORACLE),
        "success_bar": f"{facts['success_bar']:g}",
        "nop_return": f"{facts['nop_return']:.2f}",
        "hold_rate": f"{facts['hold_return'] / facts['success_bar']:.1%}",
        "episode_seconds": f"{facts['episode_seconds']:g}",
    }
    return ctx


def render(t: dict, defaults: dict, facts: dict) -> Path:
    ctx = context(t, defaults, facts)
    out = TASKS_DIR / ctx["task_dir"]
    (out / "environment").mkdir(parents=True, exist_ok=True)
    (out / "tests").mkdir(parents=True, exist_ok=True)
    (out / "solution").mkdir(parents=True, exist_ok=True)

    for name, rel in [("task.toml", "task.toml"), ("instruction.md", "instruction.md"),
                      ("README.md", "README.md"), ("Dockerfile", "environment/Dockerfile"),
                      ("gpu.docker-compose.yaml", "environment/gpu.docker-compose.yaml"),
                      ("test.sh", "tests/test.sh")]:
        text = fill((HERE / "templates" / name).read_text(), ctx)
        (out / rel).write_text((rewrap(text) if rel.endswith(".md") else text).rstrip("\n") + "\n")

    solve = "solve.oracle.sh" if t.get("oracle") else "solve.none.sh"
    (out / "solution" / "solve.sh").write_text(fill((HERE / "templates" / solve).read_text(), ctx))

    for src, rel in [("rcb_hb.py", "environment/rcb_hb.py"), ("rcb_hb.py", "tests/rcb_hb.py"),
                     ("grade.py", "tests/grade.py"), ("rcb_rewards.py", "tests/rcb_rewards.py")]:
        shutil.copyfile(HERE / "shared" / src, out / rel)

    # This task's scoring formula, and only this task's. It goes to tests/ alone -- Harbor copies that in
    # after the agent is done -- so the image the agent works in has no reward function at all
    # (images/humanoidbench/scrub_oracles.py). One family per file also means no task ever ships another
    # task's formula, which is what check-no-cross-task-leak.sh checks.
    (out / "tests" / "rewards.json").write_text(
        json.dumps(load_rewards()[t["family"]], indent=1, sort_keys=True) + "\n")

    for rel in ("tests/test.sh", "solution/solve.sh"):
        (out / rel).chmod(0o755)
    return out


# --------------------------------------------------------------------------- limited mode
# The limited-mode twin (docs/LIMITED_MODE_1_1.md): same instance, same success rule, but the simulator runs
# in a `sim` sidecar and the agent only has an HTTP client. Rendered for every task with a [task.limited]
# table; its measured numbers (facts.json "limited") come from `measure-limited`, which needs a GPU.
LIMITED_TEMPLATES = HERE / "templates" / "limited"
LIMITED_SHARED = HERE / "shared" / "limited"


def limited_dir_name(t: dict, instance_tag: str) -> str:
    return task_dir_name(t, instance_tag) + "-limited"


def write_sim_dir(t: dict, defaults: dict, dest: Path) -> Path:
    """What the sidecar mounts at /srv: the adapter, the tooling, this family's reward (the one place under
    environment/ it may live -- the agent's image never sees this directory) and the unlimited twin's
    instance, byte for byte."""
    dest.mkdir(parents=True, exist_ok=True)
    for src in ("server.py", "rcb_service.py"):
        shutil.copyfile(LIMITED_SHARED / src, dest / src)
    for src in ("rcb_hb.py", "rcb_rewards.py"):
        shutil.copyfile(HERE / "shared" / src, dest / src)
    (dest / "rewards.json").write_text(json.dumps(load_rewards()[t["family"]], indent=1, sort_keys=True) + "\n")
    shutil.copyfile(instance_path(t, defaults), dest / "instance.npz")
    return dest


def limited_actuator_layout(names: list[str], joints: list[str]) -> str:
    """actuator_layout(), plus where the agent reads the order and how obs["proprio"] lines up with it: on h1
    the joints are the actuators; on h1hand some finger actuators drive two coupled joints."""
    head, tail = actuator_layout(names).split(" A constant action", 1)
    if joints == names:
        ref = ' (`spec()["qpos"]["layout"]`; `obs["proprio"]` measures the same joints in the same order).'
    else:
        ref = (f' (`spec()["qpos"]["layout"]`). `obs["proprio"]` measures joints, not actuators: {len(joints)} '
               f'of them, in `spec()["proprio"]["joints"]` order.')
    return head.rstrip(".") + ref + " A constant action" + tail


def compose_line(name: str, value: str, comment: str) -> str:
    """One sim env line with its comment in the file's comment column (empty value: no line at all)."""
    if not value:
        return ""
    lines = textwrap.wrap(" ".join(comment.split()), 54)
    first = f'      {name}: "{value}"'.ljust(55)
    return "\n".join([f"{first}# {lines[0]}"] + [f"{'':55}# {ln}" for ln in lines[1:]]) + "\n"


def limited_context(t: dict, defaults: dict, facts: dict) -> dict:
    L, lf = t["limited"], facts["limited"]
    one = lambda s: " ".join(s.split())
    stmt = one(L.get("task_statement", t["task_statement"]))
    ms = lf["step_ms"]
    return context(t, defaults, facts) | {
        "robot": t["robot"],
        "limited_task_statement": stmt,
        "limited_task_text": stmt[0].upper() + stmt[1:],
        "limited_ends": f", {one(L['ends'])}" if L.get("ends") else "",
        "limited_hidden": one(L["hidden"]),
        "limited_tier": one(L["tier"]),
        "limited_scoring_note": one(L.get("scoring_note", t["scoring_note"])),
        "limited_camera_note": one(L["camera_note"]),
        "limited_expert_hours": 2 * t["expert_hours"],   # the unlimited estimate, doubled: no search, no state
        "limited_actuator_layout": limited_actuator_layout(facts["actuator_names"], lf["joints"]),
        "room_camera_pose_line": compose_line("RCB_ROOM_CAMERA_POSE", L.get("room_camera_pose", ""),
                                              L.get("room_camera_comment", "")),
        "image_hw": "×".join(map(str, lf["image_hw"])),
        "control_hz": lf["control_hz"],
        "robot_seconds": f"{facts['max_steps'] / lf['control_hz']:g}",
        "ms_single": f"{ms['single']:.1f}", "ms_images": f"{ms['images']:.1f}", "ms_batch": f"{ms['batch']:.1f}",
    }


def render_limited(t: dict, defaults: dict, facts: dict) -> Path:
    ctx = limited_context(t, defaults, facts)
    out = TASKS_DIR / limited_dir_name(t, defaults["instance_tag"])
    for sub in ("environment", "tests", "solution"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    for name, rel in [("instruction.md", "instruction.md"), ("README.md", "README.md"), ("task.toml", "task.toml"),
                      ("docker-compose.yaml", "environment/docker-compose.yaml"),
                      ("Dockerfile", "environment/Dockerfile"), ("tests.Dockerfile", "tests/Dockerfile"),
                      ("test.sh", "tests/test.sh"), ("solve.sh", "solution/solve.sh")]:
        text = fill((LIMITED_TEMPLATES / name).read_text(), ctx)
        (out / rel).write_text((rewrap(text, 110, items=True) if rel.endswith(".md") else text).rstrip("\n") + "\n")
    write_sim_dir(t, defaults, out / "environment" / "sim")
    shutil.copyfile(LIMITED_SHARED / "rcb_client.py", out / "environment" / "rcb_client.py")
    shutil.copyfile(LIMITED_SHARED / "grade.py", out / "tests" / "grade.py")
    for rel in ("tests/test.sh", "solution/solve.sh"):
        (out / rel).chmod(0o755)
    return out


# --------------------------------------------------------------------------- simulator-backed commands
def _small(extra: dict | None) -> dict:
    """The frozen task state, minus the two whole-model arrays -- those are kilobytes of mostly zeros
    and are already covered by instance_sha."""
    import json as _json
    return {} if extra is None else _json.loads(extra["task_state"])


def measure_one(family: str, env_id: str, instance: Path | None = None, seed: int = 0) -> dict:
    """Everything about a task that the simulator, not a human, is the authority on.

    Measured against the committed instance when there is one, because that -- not a fresh draw -- is
    the scene the agent and the verifier actually see. Tasks whose goal is drawn at reset would
    otherwise report a floor for a scene nobody ever runs.
    """
    import time

    import mujoco
    import numpy as np

    sys.path.insert(0, str(HERE / "shared"))
    # facts.json records what doing nothing scores, so measuring needs the formula the image does not
    # have. Same restore the verifier does, from the same table -- a floor measured any other way would
    # not be the number the verifier will produce.
    from rcb_rewards import restore
    restore(load_rewards()[family])
    from measure_baselines import hold_action      # one definition of "stand still", shared
    from rcb_hb import Session

    if instance is not None and instance.exists():
        s = Session(family, instance=instance)
    else:
        s = Session(family, env_id=env_id)
        s.make_instance(seed)
    names = [mujoco.mj_id2name(s.model, mujoco.mjtObj.mjOBJ_ACTUATOR, i) for i in range(s.model.nu)]
    facts = {"env_id": s.env_id, "nu": s.nu, "obs_dim": int(s.obs().shape[0]), "nq": int(s.model.nq),
             "nv": int(s.model.nv), "success_bar": s.success_bar, "max_steps": s.max_steps,
             "instance_sha": s.instance_sha(), "actuator_names": names,
             # The part of the scene that is NOT in (qpos, qvel): goals drawn at reset, subtask
             # pointers, counters. Recorded so that a change to it shows up as drift like anything else.
             "task_state": _small(s.instance_extra)}

    # Two floors every task must clear to be worth scoring, measured on the frozen instance because that
    # is the episode the agent and the verifier see.
    #   nop   all-zero action -- every joint commanded to the MIDPOINT of its range, which is not "still"
    #   hold  the action that holds the instance's own joint angles -- what standing to attention scores
    # hold is the one that decides whether a task is too easy (06-task-selection.md §B1): it is what a
    # competent agent collects before writing a controller, and it is not always the lower of the two.
    nop = np.zeros((s.max_steps, s.nu))
    first = s.replay(nop)
    t0 = time.perf_counter(); second = s.replay(nop); elapsed = time.perf_counter() - t0
    # reset() FIRST: hold_action reads the current joint angles, and after a replay those are wherever
    # the robot fell over, not the pose the instance starts in.
    s.reset()
    hold = s.replay(np.tile(hold_action(s.low), (s.max_steps, 1)))
    facts |= {"nop_return": round(first["episode_return"], 2), "nop_steps": first["sim_steps"],
              "nop_passes": bool(first["success"]),
              "hold_return": round(hold["episode_return"], 2), "hold_steps": hold["sim_steps"],
              "hold_passes": bool(hold["success"]),
              "deterministic": first["state_sha"] == second["state_sha"],
              "episode_seconds": round(elapsed * s.max_steps / max(first["sim_steps"], 1), 2)}
    s.close()
    return facts


def write_instance(t: dict, defaults: dict, force: bool = False) -> str | None:
    """Draw and freeze this task's scene. Returns None if one already exists and force is not set.

    Overwriting is guarded because an instance is an identity, not a cache: it is what the dataset
    digest covers, what the README's measured floors describe, and what any recorded trajectory was
    solved against. Regenerating with the same seed does reproduce it byte for byte (see
    Session.make_instance), so the guard costs nothing and catches the accidental case.
    """
    sys.path.insert(0, str(HERE / "shared"))
    from rcb_hb import Session

    out = TASKS_DIR / task_dir_name(t, defaults["instance_tag"])
    env_npz = out / "environment" / "instance.npz"
    if env_npz.exists() and not force:
        return None
    env_npz.parent.mkdir(parents=True, exist_ok=True)
    s = Session(t["family"], env_id=t["env_id"])
    s.make_instance(defaults["seed"])
    s.save_instance(env_npz, defaults["seed"])
    sha = s.instance_sha()
    s.close()
    # The verifier gets a byte copy, never a regenerated one: a second make_instance() would be a second
    # draw of the task-level randomness, and the two halves of the task would stop being the same scene.
    (out / "tests").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(env_npz, out / "tests" / "instance.npz")
    return sha


# --------------------------------------------------------------------------- commands
def cmd_status(args) -> int:
    defaults, tasks = load_subset()
    facts = load_facts()
    head = ("class", "family", "robot", "role", "status", "inst", "nop / bar", "SOTA")
    rows = []
    for t in tasks.values():
        d = TASKS_DIR / task_dir_name(t, defaults["instance_tag"])
        f = facts.get(t["family"], {})
        rows.append((t["capability_class"], t["family"], t["robot"], t["role"], t["status"],
                     "yes" if (d / "environment" / "instance.npz").exists() else "NO",
                     f"{f['nop_return']:g} / {f['success_bar']:g}" if f else "not measured",
                     t["completion_rate"]))
    w = [max(len(str(r[i])) for r in [head] + rows) for i in range(len(head))]
    fmt = "  ".join(f"{{:<{x}}}" for x in w)
    print(fmt.format(*head))
    for r in sorted(rows):
        print(fmt.format(*map(str, r)))
    for t in tasks.values():
        if t.get("retire_when"):
            print(f"\nretire {t['family']}: {' '.join(t['retire_when'].split())}")
    return 0


def cmd_render(args) -> int:
    defaults, tasks = load_subset()
    facts = load_facts()
    missing = [t["family"] for t in select(args.families, tasks) if t["family"] not in facts]
    if missing:
        sys.exit(f"no measurements for {missing}; run `gen_tasks.py measure` first (needs mujoco)")
    for t in select(args.families, tasks):
        print("rendered", render(t, defaults, facts[t["family"]]).relative_to(ROOT))
        if "limited" not in t:
            continue
        if "limited" not in facts[t["family"]]:
            sys.exit(f"no limited-mode measurements for {t['family']}; run `gen_tasks.py measure-limited` first (needs a GPU)")
        print("rendered", render_limited(t, defaults, facts[t["family"]]).relative_to(ROOT))
    return 0


def cmd_measure_limited(args) -> int:
    """Start each limited twin's sim service from a scratch copy of its sidecar directory and run
    limited_probe.py against it: contract checks (spec, images, proprio, the all-zero episode's return equals
    facts.json's nop_return, reset, batching, the success path through finalize), the images at t=0 (into
    --images), and the per-step cost through the real HTTP client. Records facts.json "limited"."""
    import subprocess
    import tempfile
    defaults, tasks = load_subset()
    facts = load_facts()
    rc = 0
    for t in select(args.families, tasks):
        if "limited" not in t:
            continue
        fam = t["family"]
        with tempfile.TemporaryDirectory() as tmp:
            sim = write_sim_dir(t, defaults, Path(tmp) / "sim")
            env = {**os.environ, "RCB_TASK": fam, "RCB_INSTANCE": str(sim / "instance.npz"),
                   "RCB_ROOM_CAMERA_POSE": t["limited"].get("room_camera_pose", ""), "RCB_DATA": f"{tmp}/data",
                   "RCB_FACTS": json.dumps(facts[fam]), "RCB_IMAGES": str(Path(args.images) / fam)}
            p = subprocess.run([sys.executable, str(HERE / "limited_probe.py"), str(sim)], env=env,
                               capture_output=True, text=True)
        print(p.stderr[-4000:] if p.returncode else "", end="")
        lines = [ln for ln in p.stdout.splitlines() if ln.startswith("{")]
        if p.returncode or not lines:
            print(f"FAIL {fam}: probe exited {p.returncode}\n{p.stdout[-3000:]}"); rc = 1; continue
        res = json.loads(lines[-1])
        print("\n".join(ln for ln in p.stdout.splitlines() if ln.startswith(("PASS", "FAIL"))))
        if res["failed"]:
            print(f"FAIL {fam}: {res['failed']}"); rc = 1; continue
        facts[fam]["limited"] = res["facts"]
        print(f"ok   {fam}: {json.dumps(res['facts'], default=str)[:200]}")
    FACTS.write_text(json.dumps(dict(sorted(facts.items())), indent=1, sort_keys=True) + "\n")
    return rc


def cmd_measure(args) -> int:
    defaults, tasks = load_subset()
    facts = load_facts()
    for t in select(args.families, tasks):
        facts[t["family"]] = measure_one(t["family"], t["env_id"], instance_path(t, defaults),
                                         defaults["seed"])
        print(json.dumps({t["family"]: facts[t["family"]]}, default=str)[:160])
    FACTS.write_text(json.dumps(dict(sorted(facts.items())), indent=1, sort_keys=True) + "\n")
    print("wrote", FACTS.relative_to(ROOT))
    return 0


def cmd_instance(args) -> int:
    defaults, tasks = load_subset()
    facts = load_facts()
    rc = 0
    for t in select(args.families, tasks):
        sha = write_instance(t, defaults, force=args.force)
        if sha is None:
            print(f"{t['family']:<16} kept (already exists; --force to redraw)")
            continue
        known = facts.get(t["family"], {}).get("instance_sha")
        flag = "" if known in (None, sha) else f"  !! facts.json says {known}, re-run measure"
        rc |= bool(flag)
        print(f"{t['family']:<16} instance sha {sha}{flag}")
    return rc


def cmd_verify(args) -> int:
    """Re-measure and diff. This is what makes facts.json trustworthy rather than decorative."""
    defaults, tasks = load_subset()
    facts = load_facts()
    rc = 0
    for t in select(args.families, tasks):
        fam = t["family"]
        fresh = measure_one(fam, t["env_id"], instance_path(t, defaults), defaults["seed"])
        old = facts.get(fam)
        if old is None:
            print(f"FAIL {fam}: never measured"); rc = 1; continue
        # episode_seconds is wall clock: it differs between machines and between runs on one machine, so
        # it is refreshed rather than asserted. Everything else is a property of the task and must hold.
        drift = {k: (old.get(k), v) for k, v in fresh.items()
                 if k != "episode_seconds" and old.get(k) != v}
        if drift:
            print(f"FAIL {fam}: facts.json is stale: {drift}"); rc = 1
        if fresh["nop_passes"]:
            print(f"FAIL {fam}: an all-zero trajectory reaches the bar"); rc = 1
        if fresh["hold_passes"]:
            print(f"FAIL {fam}: holding the starting pose reaches the bar"); rc = 1
        # 06-task-selection.md §B1: a task that gives away 40% of its bar for standing still cannot
        # separate a good agent from a lazy one. Two exceptions, both explicit: `spoon` carries a higher
        # `hold_threshold` in subset.toml with the reason written next to it, and a `fixture` is exempt
        # because being too easy is the whole reason it is kept.
        give_away = fresh["hold_return"] / fresh["success_bar"]
        limit = float(t.get("hold_threshold", 0.40)) if t["role"] == "scored" else float("inf")
        if give_away > limit:
            print(f"FAIL {fam}: holding the starting pose gives away {give_away:.1%} of the bar "
                  f"(limit {limit:.0%})"); rc = 1
        if not fresh["deterministic"]:
            print(f"FAIL {fam}: replaying the same actions twice gave different final states"); rc = 1
        # obs_layout is the only prose the agent relies on numerically, so check it adds up. It cannot be
        # checked against nq/nv: several tasks expose only the robot's slice of them (push has nq=33 and
        # publishes qpos(26)), so the invariant is that the parts it names sum to the real width.
        parts = sum(int(n) for n in re.findall(r"\((\d+)\)", t["obs_layout"]))
        if parts != fresh["obs_dim"]:
            print(f"FAIL {fam}: obs_layout sums to {parts}, observation is {fresh['obs_dim']}"); rc = 1
        if (not drift and not fresh["nop_passes"] and not fresh["hold_passes"] and give_away <= limit
                and fresh["deterministic"] and parts == fresh["obs_dim"]):
            print(f"ok   {fam}: nop {fresh['nop_return']}/{fresh['success_bar']:g}, "
                  f"hold {give_away:.1%} of bar, deterministic, obs {fresh['obs_dim']}")
    return rc


def main() -> int:
    p = argparse.ArgumentParser(prog="gen_tasks.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in [("status", cmd_status), ("render", cmd_render), ("measure", cmd_measure),
                     ("instance", cmd_instance), ("verify", cmd_verify), ("measure-limited", cmd_measure_limited)]:
        q = sub.add_parser(name)
        q.add_argument("families", nargs="*", help="default: every task in subset.toml")
        if name == "instance":
            q.add_argument("--force", action="store_true", help="redraw an instance that already exists")
        if name == "measure-limited":
            q.add_argument("--images", default="/tmp/rcb-limited-images", help="where the t=0 camera images go")
        q.set_defaults(fn=fn)
    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
