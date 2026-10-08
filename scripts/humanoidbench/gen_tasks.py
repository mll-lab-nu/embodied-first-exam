#!/usr/bin/env python3
"""Generate the HumanoidBench Harbor task directories from a single source of truth.

Harbor tasks are self-contained by design: each one carries its own copy of the tooling, the verifier and
the frozen scene. Copying by hand is how thirteen tasks end up with eleven slightly different verifiers,
so the copies are made here instead. `subset.toml` holds what a human decided (which tasks, why, how to
describe them), `facts.json` holds what the simulator says (bars, dimensions, floors), `templates/` holds
everything the tasks have in common, `shared/` the one real copy of the tooling and the verifier, and
`oracles/<family>/` a task's reference solution, where it has one. `check` fails if a task directory is not what
`render` writes from these.

    ./gen_tasks.py status                 # what exists, what is verified          (no simulator needed)
    ./gen_tasks.py render [family ...]    # write/refresh task dirs, minus instances and results (no simulator)
    ./gen_tasks.py check                  # tasks/ must be what render writes; no task names another or leaks a reward
    ./gen_tasks.py measure [family ...]   # read bars/dims/floors into facts.json  (needs mujoco)
    ./gen_tasks.py instance [family ...]  # write environment/ + tests/ instance.npz (needs mujoco)
    ./gen_tasks.py verify [family ...]    # re-measure and fail on drift, or if the agent's container
                                          # behaves differently from the verifier's  (needs mujoco)
    ./gen_tasks.py measure-standard [family ...] # check + time the standard twins' sim service (needs a GPU)

Every task with a [task.standard] table is rendered three times, once per mode (docs/PROTOCOL.md D12):
`<base>-privileged`, `<base>-standard` and `<base>-standard-realtime` (the standard-realtime mode, §4b: standard mode on a clock that does
not stop, eai-standard/2.3; templates/realtime/, shared/realtime/).

`render` writes everything in tasks/ but the instances, which only `instance` draws, and the results/ of agent runs;
it is idempotent:
run it after editing a template or a prose field and every task picks the change up at once.

Needs Python 3.11+ (tomllib). The simulator commands need `humanoid_bench` importable -- inside the
base image, or in a venv built the way images/humanoidbench/Dockerfile builds one.
"""
from __future__ import annotations

import argparse
import ast
import filecmp
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
sys.path.insert(0, str(ROOT / "scripts")); from task_conventions import normalize  # noqa: E402   (protocol v1.0 conventions)
SUBSET = HERE / "subset.toml"
FACTS = HERE / "facts.json"
REWARDS = HERE / "rewards.json"   # the scoring formulas, kept out of the image (see shared/rcb_rewards.py)
ORACLES = HERE / "oracles"
IMAGE = ("ghcr.io/mll-lab-nu/eai-humanoidbench:"
         + (ROOT / "images/humanoidbench/VERSION").read_text().strip())
# The agent container and the verifier of every standard-mode task: the one client base (pinned by digest) and the
# shared pip pins, both from scripts/eai_standard/ (PROTOCOL §2.4; ci_checks/check-standard-client.sh).
CLIENT = ROOT / "scripts/eai_standard"
CLIENT_ENV = dict(l.split("=", 1) for l in (CLIENT / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#"))
CLIENT_IMAGE = CLIENT_ENV["CLIENT_IMAGE"].strip()
CLIENT_REQUIREMENTS = CLIENT / CLIENT_ENV.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip()

# robot id -> (how instruction.md names it, task.toml's metadata.robot)
ROBOTS = {
    "h1": ("Unitree H1 humanoid", "unitree-h1"),
    "h1hand": ("Unitree H1 humanoid with two Shadow dexterous hands", "unitree-h1hand"),
}
CATEGORY_LONG = {"loco": "locomotion", "manip": "manipulation"}

# Prose fields that land in the middle of a sentence. They are written across several lines in
# subset.toml for readability, so their line breaks are collapsed before substitution.
INLINE_FIELDS = ("one_liner", "task_statement", "scene_note", "obs_layout", "evidence", "instance_note",
                 "completion_rate", "capability_class")

NO_ORACLE = """None. Requiring one would cap the benchmark at what we can already solve, which systematically
removes the interesting tasks. What replaces it (docs/PROTOCOL.md §2.7): the floor above (doing nothing cannot pass),
the evidence that the task has a solution (`oracle_evidence` in task.toml), and a human reviewer."""


# --------------------------------------------------------------------------- source of truth
def load_subset() -> tuple[dict, dict[str, dict]]:
    d = tomllib.loads(SUBSET.read_text())
    return d["defaults"], {t["family"]: t for t in d["task"]}


def load_rewards() -> dict[str, dict]:
    """The reward source lifted from upstream, per family. Regenerate with extract_rewards.py."""
    return json.loads(REWARDS.read_text())


def load_facts() -> dict[str, dict]:
    return json.loads(FACTS.read_text()) if FACTS.exists() else {}


def agent_hosts() -> list[str]:
    """The model-API hosts every task's agent may reach: scripts/set_agent_egress.py's HOSTS, the repository's one list
    (read, not imported: that script acts on import)."""
    tree = ast.parse((ROOT / "scripts" / "set_agent_egress.py").read_text())
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "HOSTS" for t in n.targets))


def oracle_fields(t: dict, defaults: dict, mode: str) -> dict:
    """oracle / oracle_evidence (docs/PROTOCOL.md §2.7) and what the README says: an oracle where oracles/<family>/<mode>/
    has one, else none, with the evidence subset.toml names and the human review."""
    review = f"PR #{defaults['review_pr']}" if defaults.get("review_pr") else "this benchmark's pull request"
    if (ORACLES / t["family"] / mode).is_dir():
        return {"oracle_lines": 'oracle = "full"',
                "oracle_note": "The oracle (`solution/solve.sh`) scores 1; `nop` scores 0."}
    evidence = " ".join(t["oracle_evidence"].split()) + f"; human review in {review}"
    return {"oracle_lines": f'oracle = "none"\noracle_evidence = {json.dumps(evidence, ensure_ascii=False)}',
            "oracle_note": f"No oracle; human review in {review}. `nop` scores 0."}


def clear(out: Path) -> None:
    """Everything render writes goes; results/ (agent runs) and the drawn instances (`instance` writes them) stay."""
    for f in sorted(out.rglob("*"), reverse=True) if out.is_dir() else []:
        if "results" in f.relative_to(out).parts or f.name == "instance.npz":
            continue
        if f.is_file():
            f.unlink()
        elif not any(f.iterdir()):
            f.rmdir()


def copy_oracle(t: dict, mode: str, out: Path) -> None:
    """solution/: the files of oracles/<family>/<mode>/, plus those directly under oracles/<family>/ (both modes')."""
    fam = ORACLES / t["family"]
    if (fam / mode).is_dir():
        (out / "solution").mkdir(parents=True, exist_ok=True)
        for f in sorted([*(fam / mode).iterdir(), *(p for p in fam.iterdir() if p.is_file())]):
            shutil.copy2(f, out / "solution" / f.name)


def task_dir_name(t: dict, instance_tag: str) -> str:
    return base_dir_name(t, instance_tag) + "-privileged"


def base_dir_name(t: dict, instance_tag: str) -> str:
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


CONSTANT_ACTION = ("A constant action commands joint *targets*, not a pose: whether the robot stays there depends "
                   "on whether that pose is stable under gravity and contact.")


def actuator_order(names: list[str]) -> str:
    """Describe the action vector from the model's own actuator names.

    Written from the model rather than by hand because the naive description is wrong: h1hand does not
    put all 19 body actuators first, it inserts a wrist yaw into each arm before the fingers begin.
    """
    hand_at = next((i for i, n in enumerate(names) if n.startswith(("lh_", "rh_"))), len(names))
    body, hands = names[:hand_at], names[hand_at:]
    listed = ", ".join(f"`{n}`" for n in body)
    if hands:
        per = len(hands) // 2
        wrist = [n[3:] for n in hands[:per] if "WRJ" in n]      # each hand opens with its wrist, e.g. A_WRJ2, A_WRJ1
        coupled = [n[3:] for n in hands[:per] if n.endswith("J0")]   # Shadow's J0 = one tendon over two joints
        text = (f"The {len(names)} actuators are position servos. The first {len(body)} are the body, in "
                f"this order: {listed}. The remaining {len(hands)} are the two Shadow hands, {per} each — "
                f"`lh_A_*` then `rh_A_*`; each hand's first {len(wrist)} are its wrist "
                f"({', '.join(f'`*_{w}`' for w in wrist)}) and the other {per - len(wrist)} its fingers, where each "
                f"of the {len(coupled)} `*J0` ones ({', '.join(f'`*_{c}`' for c in coupled)}) drives a tendon that "
                f"moves two finger joints together.")
    else:
        text = f"The {len(names)} actuators are position servos, in this order: {listed}."
    return text


def rewrap(md: str, width: int = 100, items: bool = False) -> str:
    """Re-flow ordinary prose paragraphs to a fixed width.

    Prose arrives here from several fields of different shapes, so without this the generated markdown is
    ragged in a way that makes real diffs hard to see. Only plain paragraphs are touched: fenced code,
    tables, headings, lists and block quotes are emitted exactly as written. `items=True` (the standard-mode
    templates, whose rules are a list with per-task clauses) also re-flows each `- ` list item, and never
    breaks a line inside `inline code`.
    """
    STRUCTURAL = re.compile(r"\s*([-*+]\s|\d+\.\s|\||>|```)")

    def wrap(text: str, indent: str = "") -> str:
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
                out.append(wrap(item, "  "))
                item = None
            if ln.startswith("- "):
                item = ln
            elif ln:
                out.append(ln)
        return "\n".join(out)

    out, fenced = [], False
    for block in md.split("\n\n"):
        lines = block.split("\n")
        if fenced or block.startswith("```"):
            out.append(block)                       # inside a code fence, or opening one
        elif items and any(ln.startswith("- ") for ln in lines) and not any(ln.startswith(("|", "```")) for ln in lines):
            out.append(fill_items(lines))
        elif any(STRUCTURAL.match(ln) or ln.startswith(("    ", "\t")) for ln in lines):
            out.append(block)                       # tables, lists and fences have layout we must not reflow
        else:
            head = [ln for ln in lines if ln.startswith("#")]   # a heading glued to its paragraph
            body = " ".join(lines[len(head):])
            out.append("\n".join(head + ([wrap(body)] if body.strip() else [])))
        fenced = fenced != (block.count("```") % 2 == 1)   # a fence may open mid-block, under a heading
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
        # How the episode ends early closes the scoring prose in privileged mode; standard mode lists
        # [task.standard] ends in its Rules instead, so its scoring prose leaves this out rather than say it twice.
        "scoring_note": " ".join((t["scoring_note"] + " " + t.get("ends_note", "")).split()),
        "task_dir": task_dir_name(t, tag),
        "instance_tag": tag,
        "seed": defaults["seed"],
        "agent_timeout": t.get("agent_timeout", defaults["agent_timeout"]),
        # instruction.md states the wall-clock budget, because the first real agent run spent its whole
        # hour searching and timed out with nothing under /app/output/ -- a zero that measures our task
        # description, not the task.
        "agent_timeout_hours": f"{float(t.get('agent_timeout', defaults['agent_timeout'])) / 3600:g}",
        "cpus": defaults["cpus"],
        "allowed_hosts": ", ".join(f'"{h}"' for h in agent_hosts()),
        "verifier_timeout": t.get("verifier_timeout", defaults["verifier_timeout"]),
        "robot_label": robot_label,
        "robot_slug": robot_slug,
        "paper_category_long": CATEGORY_LONG[t["paper_category"]],
        "image": IMAGE,
        "client_image": CLIENT_IMAGE,
        "keywords": ", ".join(f'"{k}"' for k in keywords),
        "actuator_layout": f"{actuator_order(facts['actuator_names'])} {CONSTANT_ACTION}",
        # the step() comment points to the task notes only where they say this container differs ("in this
        # container ...": state only the scoring code advances); notes that only add facts are no exception
        "step_caveat": ", except where noted below" if "in this container" in " ".join(t.get("task_notes", "").split()) else "",
        "difficulty": difficulty,
        "nop_note": nop_note,
        "reference_solution": t.get("reference_solution", NO_ORACLE),
        "success_bar": f"{facts['success_bar']:g}",
        "nop_return": f"{facts['nop_return']:.2f}",
        "hold_rate": f"{facts['hold_return'] / facts['success_bar']:.1%}",
        "episode_seconds": f"{facts['episode_seconds']:g}",
        **oracle_fields(t, defaults, "privileged"),
    }
    return ctx


def stated(path: Path, text: str, ctx: dict) -> None:
    """instruction.md is the agent's only account of the pass mark (the verifier reads upstream's own), so a
    template that stops stating it must not render."""
    if path.name == "instruction.md" and f"**{ctx['success_bar']}**" not in text:
        sys.exit(f"{path.relative_to(ROOT)} must state the pass mark, **{ctx['success_bar']}**")


def write_templates(out: Path, templates: Path, pairs: list[tuple[str, str]], ctx: dict, md_width: int = 100,
                    items: bool = False) -> None:
    """Fill each template into its place in the task dir (markdown re-flowed; scripts made executable)."""
    for name, rel in pairs:
        text = fill((templates / name).read_text(), ctx)
        stated(out / rel, text, ctx)
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text((rewrap(text, md_width, items) if rel.endswith(".md") else text).rstrip("\n") + "\n")
        if rel.endswith(".sh"):
            (out / rel).chmod(0o755)


def write_rewards(family: str, path: Path) -> None:
    """This task's scoring formula (its methods, plus the module-level constants the scrub took from its module,
    which other families of that module may share): one family per file means no task ever ships another task's
    methods (`check`)."""
    path.write_text(json.dumps(load_rewards()[family], indent=1, sort_keys=True) + "\n")


def render(t: dict, defaults: dict, facts: dict, tasks_dir: Path = TASKS_DIR) -> Path:
    ctx = context(t, defaults, facts)
    out = tasks_dir / ctx["task_dir"]
    clear(out)
    write_templates(out, HERE / "templates", [
        ("task.toml", "task.toml"), ("instruction.md", "instruction.md"), ("README.md", "README.md"),
        ("Dockerfile", "environment/Dockerfile"), ("gpu.docker-compose.yaml", "environment/gpu.docker-compose.yaml"),
        ("test.sh", "tests/test.sh")], ctx)
    for src, rel in [("rcb_hb.py", "environment/rcb_hb.py"), ("rcb_hb.py", "tests/rcb_hb.py"),
                     ("grade.py", "tests/grade.py"), ("rcb_rewards.py", "tests/rcb_rewards.py")]:
        shutil.copyfile(HERE / "shared" / src, out / rel)
    # The formula goes to tests/ alone, which the verifier's own container is built from: the image the agent
    # works in has no reward function at all (images/humanoidbench/scrub_oracles.py).
    write_rewards(t["family"], out / "tests" / "rewards.json")
    copy_oracle(t, "privileged", out)               # the reference solution: solution/ only, never the image
    # The verifier's image copies all of tests/ (the instance there comes from `instance`, not from here).
    ctx["tests_files"] = " ".join(sorted(p.name for p in (out / "tests").iterdir() if p.name != "Dockerfile"))
    write_templates(out, HERE / "templates", [("tests.Dockerfile", "tests/Dockerfile")], ctx)
    normalize(out)
    return out


# --------------------------------------------------------------------------- standard mode
# The standard-mode twin (docs/PROTOCOL.md §4, eai-standard/2.1): same instance, same success rule, but the simulator
# runs in a `sim` sidecar and the agent only has a client. Rendered for every task with a [task.standard] table; its
# measured numbers (facts.json "standard") come from `measure-standard`, which needs a GPU.
STANDARD_TEMPLATES = HERE / "templates" / "standard"
STANDARD = HERE / "shared" / "standard"            # the sidecar's service and adapter, the client, the verifier


def standard_dir_name(t: dict, instance_tag: str) -> str:
    return base_dir_name(t, instance_tag) + "-standard"


def write_sim_dir(t: dict, defaults: dict, dest: Path) -> Path:
    """What the sidecar mounts at /srv: the service and its adapter, the tooling, this family's reward (the one place
    under environment/ it may live -- the agent's image never sees this directory) and the privileged twin's
    instance, byte for byte."""
    dest.mkdir(parents=True, exist_ok=True)
    for src in ("server.py", "rcb_service.py", "rcb1.py"):
        shutil.copyfile(STANDARD / src, dest / src)
    for src in ("rcb_hb.py", "rcb_rewards.py"):
        shutil.copyfile(HERE / "shared" / src, dest / src)
    write_rewards(t["family"], dest / "rewards.json")
    shutil.copyfile(instance_path(t, defaults), dest / "instance.npz")
    return dest


def standard_actuator_layout(names: list[str], joints: list[str]) -> str:
    """The actuator order, plus where the agent reads it and the servo ranges, and how the proprioception lines up
    with it: on h1 the joints are the actuators; on h1hand some finger actuators drive two coupled joints."""
    where = 'spec()["action_types"]["joint_position"]'
    if joints == names:
        ref = f' (`{where}["layout"]`; the proprioception measures the same joints in the same order).'
    else:
        ref = (f' (`{where}["layout"]`). The proprioception measures joints, not actuators: {len(joints)} of them, '
               'in `spec()["proprio"]["joints"]` order.')
    scale = (f" A target of −1 or +1 commands one end of that servo's range, `{where}[\"range_rad\"]` in radians, "
             "and the scale is linear, so 0 is mid-range, not 0 rad.")
    return actuator_order(names).rstrip(".") + ref + scale + " " + CONSTANT_ACTION


def yaml_str(value: str) -> str:
    """A compose value, quoted: a JSON string is a YAML one, and `$$` keeps compose from interpolating `$`."""
    return json.dumps(value, ensure_ascii=False).replace("$", "$$")


def compose_line(name: str, value: str, comment: str) -> str:
    """One sim env line with its comment in the file's comment column (empty value: no line at all)."""
    if not value:
        return ""
    lines = textwrap.wrap(" ".join(comment.split()), 54) or [""]
    first = f"      {name}: {yaml_str(value)}"
    col = max(55, len(first) + 2)                     # a long value pushes the comment out, never into it
    first = first.ljust(col)
    return "\n".join([f"{first}# {lines[0]}"] + [f"{'':{col}}# {ln}" for ln in lines[1:]]) + "\n"


def standard_context(t: dict, defaults: dict, facts: dict) -> dict:
    S, sf = t["standard"], facts["standard"]
    one = lambda s: " ".join(s.split())
    stmt = one(S.get("task_statement", t["task_statement"]))
    ends = one(S["ends"]) if S.get("ends") else ""
    episode = (f"Ends when the summed reward reaches the pass mark (success){', ' + ends if ends else ''}, after "
               f"{facts['max_steps']} control steps, when your time is up (timeout), or on a simulator error.")
    ms = sf["step_ms"]
    return context(t, defaults, facts) | {
        "standard_task_statement": stmt,
        "standard_task_text": yaml_str(stmt[0].upper() + stmt[1:]),
        "standard_episode_text": yaml_str(episode),
        "standard_ends": f", {ends}" if ends else "",
        "standard_hidden": one(S["hidden"]),
        "standard_tier": one(S["tier"]),
        "standard_scoring_note": one(t["scoring_note"]),
        "standard_camera_note": one(S["camera_note"]),
        "standard_expert_hours": 2 * t["expert_hours"],   # the privileged estimate, doubled: no search, no state
        "standard_actuator_layout": standard_actuator_layout(facts["actuator_names"], sf["joints"]),
        "reset_budget": int(defaults["standard_reset_budget"]),   # the compose default: spec()["budget"]["reset"]
        "room_camera_pose_line": compose_line("RCB_ROOM_CAMERA_POSE", S.get("room_camera_pose", ""),
                                              S.get("room_camera_comment", "")),
        "image_hw_line": compose_line("RCB_IMAGE_HW", str(S.get("image_hw", "")), S.get("image_hw_comment", "")),
        "image_hw": "×".join(map(str, sf["image_hw"])),
        "control_hz": sf["control_hz"],
        "control_dt": f"{1 / sf['control_hz']:g}",
        "robot_seconds": f"{facts['max_steps'] / sf['control_hz']:g}",
        "ms_single": f"{ms['single']:.1f}", "ms_images": f"{ms['images']:.1f}", "ms_batch": f"{ms['batch']:.1f}",
        "reference_solution": t.get("standard_reference_solution", NO_ORACLE),
        **oracle_fields(t, defaults, "standard"),
    }


def render_standard(t: dict, defaults: dict, facts: dict, tasks_dir: Path = TASKS_DIR) -> Path:
    ctx = standard_context(t, defaults, facts)
    out = tasks_dir / standard_dir_name(t, defaults["instance_tag"])
    clear(out)
    write_templates(out, STANDARD_TEMPLATES, [
        ("instruction.md", "instruction.md"), ("README.md", "README.md"), ("task.toml", "task.toml"),
        ("docker-compose.yaml", "environment/docker-compose.yaml"), ("Dockerfile", "environment/Dockerfile"),
        ("tests.Dockerfile", "tests/Dockerfile"), ("test.sh", "tests/test.sh")], ctx, md_width=110, items=True)
    write_sim_dir(t, defaults, out / "environment" / "sim")
    for src, rel in [("rcb_client.py", "environment/rcb_client.py"), ("rcb1.py", "environment/rcb1.py"),
                     ("grade.py", "tests/grade.py")]:
        shutil.copyfile(STANDARD / src, out / rel)
    shutil.copyfile(CLIENT_REQUIREMENTS, out / "environment/client-requirements.txt")
    copy_oracle(t, "standard", out)
    normalize(out)
    return out


# --------------------------------------------------------------------------- standard-realtime mode
# The standard-realtime task (`<base>-standard-realtime`, mode = "standard-realtime", eai-standard/2.3; docs/PROTOCOL.md §4b): the standard twin's
# sidecar, client and verifier, except that the service runs the episode on a clock that does not stop
# (shared/realtime/rcb_realtime.py, which extends rcb_service.py unchanged) and the agent gets the realtime client
# (`submit(..., at=)`, `cameras=[]`). Same instance, same success rule; reset budget `realtime_reset_budget` (50,
# HumanoidBench's exception to the mode's default of 0, PROTOCOL §4.5); the instruction tells the agent to drive the
# robot with a controller program.
REALTIME_TEMPLATES = HERE / "templates" / "realtime"
REALTIME = HERE / "shared" / "realtime"


def realtime_dir_name(t: dict, instance_tag: str) -> str:
    return base_dir_name(t, instance_tag) + "-standard-realtime"


# A recorded episode (a trajectory) is solvability evidence here too: planned from step 0 (`at`), its rows run at the
# same control steps.
REALTIME_EVIDENCE = ("; in realtime, the same rows planned into the episode from step 0 (submit's `at`) run at the "
                     "same control steps and are graded the same")


def realtime_context(t: dict, defaults: dict, facts: dict) -> dict:
    ctx = standard_context(t, defaults, facts)
    ev = t.get("oracle_evidence", "")
    ev += REALTIME_EVIDENCE if "trajectory" in ev else ""      # a recorded episode, not "none known" or an RL score
    # the realtime tasks' own human review: the pull request that added them (realtime_review_pr; 0: not opened yet)
    review = {**defaults, "review_pr": defaults.get("realtime_review_pr", 0)}
    oracle = oracle_fields({**t, "oracle_evidence": ev}, review, "standard-realtime")
    return ctx | {
        "base_dir": base_dir_name(t, defaults["instance_tag"]),
        "control_ms": f"{1000 / facts['standard']['control_hz']:g}",
        "reset_budget": int(defaults["realtime_reset_budget"]),   # the compose default: spec()["budget"]["reset"]
        "reference_solution": t.get("realtime_reference_solution", NO_ORACLE),
        **oracle,
    }


def render_realtime(t: dict, defaults: dict, facts: dict, tasks_dir: Path = TASKS_DIR) -> Path:
    ctx = realtime_context(t, defaults, facts)
    out = tasks_dir / realtime_dir_name(t, defaults["instance_tag"])
    clear(out)
    write_templates(out, REALTIME_TEMPLATES, [
        ("instruction.md", "instruction.md"), ("README.md", "README.md"), ("task.toml", "task.toml"),
        ("docker-compose.yaml", "environment/docker-compose.yaml")], ctx, md_width=110, items=True)
    write_templates(out, STANDARD_TEMPLATES, [
        ("Dockerfile", "environment/Dockerfile"), ("tests.Dockerfile", "tests/Dockerfile"),
        ("test.sh", "tests/test.sh")], ctx, md_width=110, items=True)
    sim = write_sim_dir(t, defaults, out / "environment" / "sim")
    shutil.copyfile(REALTIME / "rcb_realtime.py", sim / "rcb_realtime.py")
    for src, rel in [(REALTIME / "rcb_client.py", "environment/rcb_client.py"),
                     (STANDARD / "rcb1.py", "environment/rcb1.py"), (STANDARD / "grade.py", "tests/grade.py")]:
        shutil.copyfile(src, out / rel)
    shutil.copyfile(CLIENT_REQUIREMENTS, out / "environment/client-requirements.txt")
    copy_oracle(t, "standard-realtime", out)
    normalize(out)
    return out


# --------------------------------------------------------------------------- simulator-backed commands
def unresolved_calls(family: str) -> list[str]:
    """What the restored formula calls on self that the task class does not have. The all-zero episode cannot find
    these: truck's formula calls `upon_table()` only once a package has been lifted."""
    import ast
    import importlib
    rec = load_rewards()[family]
    mod, cls = rec["task_class"].rsplit(".", 1)
    klass = getattr(importlib.import_module(mod), cls)
    called = {n.func.attr for m in rec["methods"] for n in ast.walk(ast.parse(m["source"]))
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"}
    return sorted(n for n in called if not hasattr(klass, n))


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
    if missing := unresolved_calls(family):
        raise RuntimeError(f"{family}: the restored formula calls {missing} on self, which neither the image nor "
                           f"rewards.json provides")
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
             # The part of the scene that is NOT in (qpos, qvel): goals drawn at reset, subtask pointers,
             # counters. Recorded so that a change to it shows up as drift like anything else (the two
             # whole-model arrays are left out: kilobytes of mostly zeros, already covered by instance_sha).
             "task_state": json.loads(s.instance_extra["task_state"])}

    # Two floors every task must clear to be worth scoring, measured on the frozen instance because that
    # is the episode the agent and the verifier see.
    #   nop   all-zero action -- every joint commanded to the MIDPOINT of its range, which is not "still"
    #   hold  the action that holds the instance's own joint angles -- what standing to attention scores
    # hold is the one that decides whether a task is too easy (the give-away limit `verify` enforces): it is
    # what a competent agent collects before writing a controller, and it is not always the lower of the two.
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


# One process per side, because restore() patches the classes for the whole process. The same random actions go in;
# out comes a hash of every observation and termination until the episode ends or 150 steps pass.
VIEW_PROBE = """
import hashlib, json, sys
import numpy as np
sys.path.insert(0, sys.argv[1])
if sys.argv[4] == "verifier":
    from rcb_rewards import restore
    restore(json.load(open(sys.argv[5])))
from rcb_hb import Session
s, h, rng = Session(sys.argv[2], instance=sys.argv[3]), hashlib.sha1(), np.random.default_rng(0)
for _ in range(150):
    obs, _, done = s.step(rng.uniform(-0.3, 0.3, s.nu))
    h.update(np.asarray(obs, dtype=np.float64).tobytes() + bytes([done]))
    if done:
        break
print(h.hexdigest())
"""


def views_agree(family: str, instance: Path) -> bool:
    """The agent's container has no reward function and the verifier's has one; nothing else may differ. Upstream
    advances some task state inside the reward function, which is what rcb_hb._unscored_bookkeeping() is for."""
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
        json.dump(load_rewards()[family], f)
        f.flush()
        return len({subprocess.run([sys.executable, "-c", VIEW_PROBE, str(HERE / "shared"), family, str(instance), side,
                                    f.name], capture_output=True, text=True, check=True).stdout
                    for side in ("agent", "verifier")}) == 1


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
    chosen = select(args.families, tasks)
    if missing := [t["family"] for t in chosen if t["family"] not in facts]:
        sys.exit(f"no measurements for {missing}; run `gen_tasks.py measure` first (needs mujoco)")
    if missing := [t["family"] for t in chosen if "standard" in t and "standard" not in facts[t["family"]]]:
        sys.exit(f"no standard-mode measurements for {missing}; run `gen_tasks.py measure-standard` first (needs a GPU)")
    for t in chosen:
        print("rendered", render(t, defaults, facts[t["family"]]).relative_to(ROOT))
        if "standard" in t:
            print("rendered", render_standard(t, defaults, facts[t["family"]]).relative_to(ROOT))
            print("rendered", render_realtime(t, defaults, facts[t["family"]]).relative_to(ROOT))
    return 0


# What a task ships to the agent must not carry a scoring formula (images/humanoidbench/scrub_oracles.py deletes it
# from the image): no tolerance parameters, no get_reward. And no task names another (identifier-shaped: "walk",
# 'walk', h1-walk-v0, --family walk; the English word "walk" is fine).
FORMULA = re.compile(r"\b(?:bounds|margin|value_at_margin)\s*=|\brewards\.tolerance\s*\(|\bdef\s+get_reward")


def leaks(task: Path, families: set[str]) -> list[str]:
    toml = tomllib.loads((task / "task.toml").read_text())
    # standard and standard-realtime tasks score in the sim sidecar (environment/sim/), privileged ones in tests/
    own, standard = toml["metadata"]["family"], toml["metadata"]["mode"] in ("standard", "standard-realtime")
    home = task / ("environment/sim" if standard else "tests")               # where the formula has to be
    agent_side = [f for f in sorted((task / "environment").rglob("*"))
                  if f.is_file() and not (standard and home in f.parents)]
    bad = [f"{home.relative_to(task)} lacks {n}" for n in ("rewards.json", "rcb_rewards.py") if not (home / n).is_file()]
    bad += [f"{f.relative_to(task)} would ship the scoring formula to the agent" for f in agent_side
            if f.name in ("rewards.json", "rcb_rewards.py")]
    bad += [f"{f.relative_to(task)} quotes the reward formula" for f in [task / "instruction.md", *agent_side]
            if f.suffix in (".py", ".md", ".txt", ".yaml") and FORMULA.search(f.read_text(errors="ignore"))]
    if standard and re.search(r"^\s*(COPY|ADD)\s+(\S+\s+)*\.?/?sim\b", (task / "environment/Dockerfile").read_text(), re.M):
        bad.append("environment/Dockerfile copies the sidecar's files into the agent image")
    if toml["agent"].get("network_mode") != "allowlist":
        bad.append("the agent's egress is not an allowlist: it could fetch upstream's get_reward() back")
    for sub in ("environment", "tests", "solution"):
        for f in sorted((task / sub).rglob("*")) if (task / sub).is_dir() else []:
            if f.is_file() and f.suffix not in (".npz", ".npy", ".pyc"):
                text = f.read_text(errors="ignore")
                bad += [f"{f.relative_to(task)} names {o}" for o in sorted(families - {own})
                        if re.search(rf"""["']{re.escape(o)}["']|\b\w+-{re.escape(o)}-v\d|--(?:task|family)\s+{re.escape(o)}\b""", text)]
    return bad


def cmd_check(args) -> int:
    """tasks/ must be what render writes from today's sources (results/ aside), with no stale humanoidbench-* directory;
    no task may leak a scoring formula to the agent or name another task."""
    import tempfile
    defaults, tasks = load_subset()
    facts = load_facts()
    failed: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for d in TASKS_DIR.glob("humanoidbench-*"):      # the drawn instances come along; render keeps them
            shutil.copytree(d, Path(tmp) / d.name, ignore=shutil.ignore_patterns("results"))
        rendered = set()
        for t in tasks.values():
            rendered.add(render(t, defaults, facts[t["family"]], Path(tmp)).name)
            if "standard" in t:
                rendered.add(render_standard(t, defaults, facts[t["family"]], Path(tmp)).name)
                rendered.add(render_realtime(t, defaults, facts[t["family"]], Path(tmp)).name)
        for name in sorted(rendered):
            failed += _diff(filecmp.dircmp(TASKS_DIR / name, Path(tmp) / name, ignore=["results", "__pycache__"]), name)
    failed += [f"tasks/{p.name}: no longer rendered" for p in sorted(TASKS_DIR.glob("humanoidbench-*"))
               if p.name not in rendered]
    for name in sorted(rendered):
        failed += [f"tasks/{name}: {b}" for b in leaks(TASKS_DIR / name, set(tasks))]
    print("\n".join(f"FAIL {x}" for x in failed) or f"check: {len(rendered)} task dirs are what render writes")
    return 1 if failed else 0


def _diff(c: filecmp.dircmp, prefix: str) -> list[str]:
    out = [f"tasks/{prefix}/{x}: differs from its render" for x in c.diff_files]
    out += [f"tasks/{prefix}/{x}: not rendered" for x in c.left_only] + [f"tasks/{prefix}/{x}: missing" for x in c.right_only]
    for sub, sc in c.subdirs.items():
        out += _diff(sc, f"{prefix}/{sub}")
    return out


def cmd_measure_standard(args) -> int:
    """Start each standard twin's sim service from a scratch copy of its sidecar directory and run standard_probe.py
    against it: contract checks (spec, images, proprio, the all-zero episode's return equals facts.json's nop_return,
    the reset capability, chunks, a crash it must survive, the success path through finalize), the images at t=0 (into
    --images), and the per-step cost through the real client. Records facts.json "standard"."""
    import subprocess
    import tempfile
    defaults, tasks = load_subset()
    facts = load_facts()
    rc = 0
    for t in select(args.families, tasks):
        if "standard" not in t:
            continue
        fam = t["family"]
        with tempfile.TemporaryDirectory() as tmp:
            sim = write_sim_dir(t, defaults, Path(tmp) / "sim")
            env = {**os.environ, "RCB_TASK": fam, "RCB_INSTANCE": str(sim / "instance.npz"),
                   "RCB_ROOM_CAMERA_POSE": t["standard"].get("room_camera_pose", ""),
                   "RCB_IMAGE_HW": str(t["standard"].get("image_hw", "")), "RCB_DATA": f"{tmp}/data",
                   "RCB_FACTS": json.dumps(facts[fam]), "RCB_IMAGES": str(Path(args.images) / fam)}
            p = subprocess.run([sys.executable, str(HERE / "standard_probe.py"), str(sim)], env=env,
                               capture_output=True, text=True)
        print(p.stderr[-4000:] if p.returncode else "", end="")
        lines = [ln for ln in p.stdout.splitlines() if ln.startswith("{")]
        if p.returncode or not lines:
            print(f"FAIL {fam}: probe exited {p.returncode}\n{p.stdout[-3000:]}"); rc = 1; continue
        res = json.loads(lines[-1])
        print("\n".join(ln for ln in p.stdout.splitlines() if ln.startswith(("PASS", "FAIL"))))
        if res["failed"]:
            print(f"FAIL {fam}: {res['failed']}"); rc = 1; continue
        facts[fam]["standard"] = res["facts"]
        print(f"ok   {fam}: {json.dumps(res['facts'], default=str)[:200]}")
        FACTS.write_text(json.dumps(dict(sorted(facts.items())), indent=1, sort_keys=True) + "\n")
    return rc


def cmd_measure(args) -> int:
    defaults, tasks = load_subset()
    facts = load_facts()
    for t in select(args.families, tasks):
        # a merge, not a replacement: "standard" comes from measure-standard, which needs a GPU
        facts[t["family"]] = facts.get(t["family"], {}) | measure_one(t["family"], t["env_id"],
                                                                      instance_path(t, defaults), defaults["seed"])
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
        old = facts.get(fam)
        if old is None:
            print(f"FAIL {fam}: never measured"); rc = 1; continue
        fresh = measure_one(fam, t["env_id"], instance_path(t, defaults), defaults["seed"])
        # episode_seconds is wall clock: it differs between machines and between runs on one machine, so
        # it is not asserted. Everything else is a property of the task and must hold.
        drift = {k: (old.get(k), v) for k, v in fresh.items() if k != "episode_seconds" and old.get(k) != v}
        # A task that gives away 40% of its bar for standing still cannot separate a good agent from a
        # lazy one. Two exceptions, both explicit: `spoon` carries a higher `hold_threshold` in subset.toml
        # with the reason written next to it, and a `fixture` is exempt because being too easy is the whole
        # reason it is kept.
        give_away = fresh["hold_return"] / fresh["success_bar"]
        limit = float(t.get("hold_threshold", 0.40)) if t["role"] == "scored" else float("inf")
        # obs_layout is the only prose the agent relies on numerically, so check it adds up. It cannot be
        # checked against nq/nv: several tasks expose only the robot's slice of them (push has nq=33 and
        # publishes qpos(26)), so the invariant is that the parts it names sum to the real width.
        parts = sum(int(n) for n in re.findall(r"\((\d+)\)", t["obs_layout"]))
        failures = [msg for bad, msg in [
            (drift, f"facts.json is stale: {drift}"),
            (fresh["nop_passes"], "an all-zero trajectory reaches the bar"),
            (fresh["hold_passes"], "holding the starting pose reaches the bar"),
            (give_away > limit, f"holding the starting pose gives away {give_away:.1%} of the bar (limit {limit:.0%})"),
            (not fresh["deterministic"], "replaying the same actions twice gave different final states"),
            (parts != fresh["obs_dim"], f"obs_layout sums to {parts}, observation is {fresh['obs_dim']}"),
            (not views_agree(fam, instance_path(t, defaults)),
             "the same actions give the agent different observations or terminations than the verifier")] if bad]
        for msg in failures:
            print(f"FAIL {fam}: {msg}")
        if failures:
            rc = 1
        else:
            print(f"ok   {fam}: nop {fresh['nop_return']}/{fresh['success_bar']:g}, "
                  f"hold {give_away:.1%} of bar, deterministic, obs {fresh['obs_dim']}, agent sees what the verifier sees")
    return rc


def main() -> int:
    p = argparse.ArgumentParser(prog="gen_tasks.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in [("status", cmd_status), ("render", cmd_render), ("check", cmd_check), ("measure", cmd_measure),
                     ("instance", cmd_instance), ("verify", cmd_verify), ("measure-standard", cmd_measure_standard)]:
        q = sub.add_parser(name)
        if name != "check":
            q.add_argument("families", nargs="*", help="default: every task in subset.toml")
        if name == "instance":
            q.add_argument("--force", action="store_true", help="redraw an instance that already exists")
        if name == "measure-standard":
            q.add_argument("--images", default="/tmp/rcb-standard-images", help="where the t=0 camera images go")
        q.set_defaults(fn=fn)
    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
