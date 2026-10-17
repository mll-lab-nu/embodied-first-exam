#!/usr/bin/env python3
"""Generate the BiGym 2.0 tasks: tasks/bigym2-<family>-i00-privileged, -standard (eai-standard/2.1) and
-standard-realtime (eai-standard/2.3) for every frozen instance in scripts/bigym2/instances/ (docs/benchmarks/bigym2.md).

    python3 scripts/bigym2/gen_tasks.py render     # (re)write every BiGym 2.0 task dir; `git diff tasks/` stays empty
    python3 scripts/bigym2/gen_tasks.py check      # write nothing; exit 1 if a task dir differs from the generator's
Then `cd tasks && harbor add --scan .` when a digest changed. Needs only Python 3 (no simulator).

Inputs, all in the repository:
  scripts/bigym2/tasks.json                 per family: upstream's task and sentence, the success rule in words, the seed,
                                            a positive example (`evidence`)
  scripts/bigym2/instances/<f>-i00.json     the frozen instance + the numbers the texts quote (make_instances.py)
  scripts/bigym2/shared/                    the tooling (rcb_bigym2.py, grade.py), the sim service (standard/: the BiGym 2.0
                                            adapter server.py on rcb_service.py; realtime/: rcb_realtime.py) and clients
  scripts/bigym2/templates/<mode>/          every other task file; a *.tmpl file is filled with the instance's values (@@KEY@@)
  scripts/eai_standard/client.env           the standard agent image and its pip pins (shared by every standard task)
  scripts/set_agent_egress.py               HOSTS, the agent's allowlist
  images/bigym2/VERSION                     the base image tag
Every task is written to a scratch directory, passed through scripts/task_conventions.py's normalize() and synced into
tasks/: a task dir holds exactly what the generator writes."""

import argparse, json, os, pathlib, re, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "scripts/bigym2"
SHARED = HERE / "shared"
REGISTRY = "ghcr.io/mll-lab-nu"
REVIEW_PR = 123  # the pull request that holds the human review of these tasks (PROTOCOL §2.7)
IMAGE_HW = 84  # the onboard cameras' default image side in standard modes (compose RCB_IMAGE_HW): upstream's, its agents' and policies'
MODES = {"privileged": "privileged", "standard": "standard", "standard-realtime": "realtime"}
# the service modes' default reset budget (RCB_RESET_BUDGET's default; BiGym 2.0's own choice, PROTOCOL §2; author
# 2026-10-16, before it standard 10 from 2026-10-11): 0 in both, the protocol's default: one episode, whose horizon the
# practice and the graded attempt share; standard-realtime has had 0 since 2026-10-08
RESET_BUDGET = {"standard": 0, "standard-realtime": 0}
CLIENT = dict(
    line.split("=", 1)
    for line in (ROOT / "scripts/eai_standard/client.env").read_text().splitlines()
    if "=" in line and not line.startswith("#")
)
MEANING = {
    "vx": "walking velocity command, forward (m/s, the robot's frame)",
    "vy": "walking velocity command, to the left (m/s)",
    "height": "pelvis height command (m)",
    "wz": "turning rate command, + turns left (rad/s)",
    "pitch": "torso lean command, + leans forward (rad)",
    "left_gripper": "0 open .. 1 closed",
    "right_gripper": "0 open .. 1 closed",
}
HELD = ("*Held* means that a finger of the gripper touches the object (BiGym's `is_gripper_holding_object`): an open "
        "gripper still resting against it holds it.")
FALL = ("The robot must not fall at any time: a fall (the pelvis tilted more than about 53 degrees from upright, or lower "
        "than 0.30 m) makes the episode a failure, but does not end it.")
CONTROLLER = (
    "The whole-body controller, as BiGym's own notes for its coding agents describe it: it follows velocity commands "
    "with some lag and wobble, so read the pelvis pose and close the loop rather than dead-reckon; a planar speed command "
    "below 0.055 m/s means standing still (use 0 or at least 0.06); standing still, the base drifts a few centimetres, "
    "and further while the hands push on furniture or the torso leans far (measured here: 0.27 m and 15 degrees with the "
    "hands pressing on a cabinet, 0.11 m and 24 degrees from a 0.8 rad lean); "
    "heights above about 0.8 m lock the knees (the pelvis stays near 0.78 m); squatting (a lower height) is how the hands "
    "reach low objects, and while squatting the controller does not step: walk first, then squat in place. It keeps the "
    "robot balanced but does not stop it from walking into things."
)
SLOWDOWN = '      RCB_SLOWDOWN: "${RCB_SLOWDOWN:-1}"                # 1: real time (official); S: one step every S x control_dt s, reported apart\n'


def hosts() -> str:
    src = (ROOT / "scripts/set_agent_egress.py").read_text()
    m = re.search(r"^HOSTS\s*=\s*\[(.*?)\]", src, re.S | re.M)
    if not m:
        raise RuntimeError("scripts/set_agent_egress.py: no HOSTS list")
    return ", ".join(f'"{h}"' for h in re.findall(r"""["']([^"']+)["']""", m.group(1)))


def task_dir(fam: str, mode: str) -> str:
    return f"bigym2-{fam}-i00-{mode}"


def fill(text: str, values: dict) -> str:
    for k, v in values.items():
        text = text.replace(f"@@{k}@@", str(v))
    if "@@" in text:
        raise RuntimeError(f"unfilled placeholder near {text[text.index('@@'):][:40]!r}")
    return text


def layout_table(t0: dict) -> str:
    rows = ["| slot | name | bounds | meaning | at the start |", "|---|---|---|---|---|"]
    joints, notes = t0["robot"]["joints"], []
    for i, (n, lo, hi, h) in enumerate(zip(t0["layout"], t0["lower"], t0["upper"], t0["hold"])):
        meaning = MEANING.get(n, "absolute joint target (rad)")
        rows.append(f"| {i} | `{n}` | [{lo:g}, {hi:g}] | {meaning} | {h:g} |")
        if n in joints and [round(lo, 4), round(hi, 4)] != [round(x, 4) for x in joints[n]["range"]]:
            notes.append(f"`{n}`'s bounds are BiGym's action bounds, not the joint's own range "
                         f"[{joints[n]['range'][0]:g}, {joints[n]['range'][1]:g}]: a command outside them is clipped")
    return "\n".join(rows) + ("\n\n" + "; ".join(notes) + "." if notes else "")


def proprio_text(t0: dict) -> str:
    names = t0["proprio_layout"]
    n = len([x for x in names if x.endswith("_pos")])
    waist = " the 3 waist joints (they show the lean you command)," if any(x.startswith("waist") for x in names) else ""
    return (
        f"the positions (`*_pos`) of{waist} each arm's 7 joints (rad) and its gripper's 2 finger joints (slides, m), and "
        "the pelvis (`pelvis_x_pos`, `pelvis_y_pos`, `pelvis_z_pos` in m and `pelvis_rz_pos`, its heading, in rad: the "
        "room's frame, z up, heading 0 along the room's +x axis and counter-clockwise positive): "
        f"{n} values; then their velocities (`*_vel`, per second) in the same order; then `left_gripper_state` and "
        "`right_gripper_state` (0 open .. 1 closed); then the pelvis pose again as the base controller tracks it "
        "(`pelvis_x`, `pelvis_y`, `pelvis_z`, `pelvis_yaw`). This is BiGym's own low-dimensional observation, the one its "
        "learned policies receive."
    )


def success_par(task: dict) -> str:
    """The instruction's success paragraph, the same in every mode."""
    out = f"The episode succeeds when the following has held for **1 s (50 control steps in a row)**: {task['success']}."
    if "held" in task["success"]:
        out += f" {HELD}"
    if task["fail"]:
        out += f" {task['fail'][0].upper()}{task['fail'][1:]}."
    out += f" {FALL}"
    return out


def episode_text(task: dict, t0: dict, resets: int) -> str:
    fail = f"; {task['fail']}" if task["fail"] else ""
    held = " (held = a finger of the gripper touching the object)" if "held" in task["success"] else ""
    head = "one episode, no reset: it succeeds" if not resets else f"{resets} resets, the last episode graded: an episode succeeds"
    return (
        f"{head} when this has held for 1 s (50 control steps): {task['success']}"
        f"{held}{fail}; a fall (pelvis tilted beyond ~53 degrees or below 0.30 m) fails "
        "it without ending it; it ends at the success, a failure, the pelvis 10 m from the scene's origin, a simulator "
        f"error, or after {t0['horizon_steps']} control steps"
    )


def reset_vals(n: int, horizon: int) -> dict:
    """The standard texts that depend on the reset budget n: with n = 0 the service has no POST /reset (and no episode
    counters), so the texts describe one episode and no reset."""
    if not n:
        return {
            "RESET_DESC": "One episode, no reset",
            "RESET_README": "gets one episode, no reset",
            "RESET_RULE": "**One episode, no reset.** The episode starts when the service comes up, from a fixed starting "
            "state; what ends it is under Success below. `spec()[\"budget\"][\"reset\"]` is authoritative: it is 0 here, "
            "so the one episode is the run. Once it has ended, the run is over and `submit` raises `EpisodeOver`.",
            "RECORDED": "records the episode, replays it",
            "STATUS_EXTRA": "",
            "RESET_ROW": "",
            "RESET_LEFT": "",
        }
    return {
        "RESET_DESC": f"{n} resets (the last episode graded)",
        "RESET_README": f"gets {n} resets (only the last episode is graded)",
        "RESET_RULE": f"**Episodes and resets.** The episode starts when the service comes up, from a fixed starting state; "
        f"what ends it is under Success below. You have **{n} resets** (`spec()[\"budget\"][\"reset\"]`, which is "
        "authoritative: if it says 0, there is no reset and the one episode is the run). `r.reset()` puts the robot and "
        f"the scene back on the same starting state and starts a new episode with its own {horizon} control steps, "
        "either abandoning the running episode or after one has ended; it takes no robot time and returns the start's "
        "frames. Once an episode has ended, `submit` raises `EpisodeOver` (its message gives `resets_left`) until you "
        "reset. **Only the last episode is graded**: a success ends the run at once, and when your time is up the "
        "episode then running is the one graded; `meta[\"episode\"]` and `meta[\"resets_left\"]` count the episodes.",
        "RECORDED": "records every episode, replays the last one",
        "STATUS_EXTRA": ", and `episode`, `resets_left`, `control_steps_total` (all episodes)",
        "RESET_ROW": "| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the starting state "
        f"(at most {n} in all); returns the start's frames |\n",
        "RESET_LEFT": ", or a reset is left",
    }


def yaml(s: str) -> str:
    return json.dumps(s).replace("$", "$$")   # a double-quoted YAML scalar; compose interpolates $


def values(fam: str, task: dict, inst: dict, version: str) -> dict:
    t0 = inst["t0"]
    pitch = "pitch" in t0["layout"]
    fail = task["fail"]
    sentence = task["sentence"]
    return {
        "FAMILY": fam,
        "TASK": task["upstream_task"],
        "SEED": inst["seed"],
        "GROUP": task["group"],
        "SENTENCE": sentence,
        "SENTENCE_TOML": sentence.replace("\\", "\\\\").replace('"', '\\"'),
        "SUCCESS": task["success"],
        "FAIL_SENTENCE": (fail[0].upper() + fail[1:] + ". ") if fail else "",
        "SCENE": inst["scene"],
        "SUCCESS_PAR": success_par(task),
        "CONTROLLER": CONTROLLER,
        "ENDS_FAIL": ", on the failure above" if fail else "",
        "DIFFICULTY": task["difficulty"],
        "HORIZON_STEPS": t0["horizon_steps"],
        "HORIZON_S": f"{t0['horizon_steps'] * t0['control_dt']:g}",
        "DIM": t0["action_dim"],
        "LAYOUT_TABLE": layout_table(t0),
        "PROPRIO_TEXT": proprio_text(t0),
        "PITCH_PHRASE": ", how far its torso leans forward" if pitch else "",
        "PRIV": task_dir(fam, "privileged"),
        "STD": task_dir(fam, "standard"),
        "RT": task_dir(fam, "standard-realtime"),
        "SHA": t0["state_sha"],
        "IMAGE": f"{REGISTRY}/eai-bigym2:{version}",
        "CLIENT_IMAGE": CLIENT["CLIENT_IMAGE"].strip(),
        "HOSTS": hosts(),
        "IMAGE_HW": IMAGE_HW,
        "ORACLE_EVIDENCE": "no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' "
        "programs stay off the agent's network); "
        + (f"positive example graded 1 by the separate verifier: {task['evidence']}; " if task["evidence"] else
           "no positive example yet; ")
        + f"human review in PR #{REVIEW_PR}",
        "REVIEW": f"No oracle; human review in PR #{REVIEW_PR} (PROTOCOL §2.7).",
        "TASK_TEXT_YAML": yaml(sentence),
    }


def files_of(tdir: pathlib.Path, vals: dict) -> dict[str, tuple[bytes, int]]:
    out = {}
    for p in sorted(tdir.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(tdir).as_posix()
        if rel.endswith(".tmpl"):
            rel, data = rel[:-5], fill(p.read_text(), vals).encode()
        else:
            data = p.read_bytes()
        out[rel] = (data, 0o755 if rel.endswith(".sh") else 0o644)
    return out


def plan(fam: str, task: dict, version: str) -> dict[str, dict[str, tuple[bytes, int]]]:
    """{task dir name: {relative path: (content, mode)}} for the three modes of one instance."""
    path = HERE / "instances" / f"{fam}-i00.json"
    raw = path.read_bytes()
    inst = json.loads(raw)
    if inst["family"] != fam or inst["task"] != task["upstream_task"] or inst["seed"] != task["seed"]:
        raise RuntimeError(f"{path.name} does not match tasks.json (family, upstream task, seed)")
    vals = values(fam, task, inst, version)
    tool = (SHARED / "rcb_bigym2.py").read_bytes()
    std = SHARED / "standard"
    out = {}
    for mode, tmpl in MODES.items():
        vals["SIM_COMMAND"] = "python /srv/rcb_realtime.py" if mode == "standard-realtime" else "python /srv/server.py"
        vals["SLOWDOWN_LINE"] = SLOWDOWN if mode == "standard-realtime" else ""
        vals["RESET_BUDGET"] = RESET_BUDGET.get(mode, 0)
        vals["RESET_COMMENT"] = (f"BiGym2 standard: {vals['RESET_BUDGET']} resets (docs/benchmarks/bigym2.md); 0: one episode"
                                 if vals["RESET_BUDGET"] else "0: one episode (the protocol's default)")
        vals["EPISODE_TEXT_YAML"] = yaml(episode_text(task, inst["t0"], vals["RESET_BUDGET"]))
        vals.update(reset_vals(vals["RESET_BUDGET"], inst["t0"]["horizon_steps"]))
        if mode == "privileged":
            files = files_of(HERE / "templates/privileged", vals)
            for rel in ("environment/rcb_bigym2.py", "tests/rcb_bigym2.py"):
                files[rel] = (tool, 0o644)
            for rel in ("environment/instance.json", "tests/instance.json"):
                files[rel] = (raw, 0o644)
            files["tests/grade.py"] = ((SHARED / "grade.py").read_bytes(), 0o644)
        else:
            files = files_of(HERE / "templates/standard", vals)
            if mode == "standard-realtime":  # its own task.toml, instruction, README and compose; the rest is standard's
                files.update(files_of(HERE / "templates/realtime", vals))
            client = SHARED / ("realtime" if mode == "standard-realtime" else "standard") / "rcb_client.py"
            files["environment/rcb_client.py"] = (client.read_bytes(), 0o644)
            files["environment/rcb1.py"] = ((std / "rcb1.py").read_bytes(), 0o644)
            req = CLIENT["CLIENT_REQUIREMENTS"].strip()
            files["environment/client-requirements.txt"] = ((ROOT / "scripts/eai_standard" / req).read_bytes(), 0o644)
            for name in ("server.py", "rcb_service.py", "rcb1.py"):
                files[f"environment/sim/{name}"] = ((std / name).read_bytes(), 0o644)
            if mode == "standard-realtime":
                files["environment/sim/rcb_realtime.py"] = ((SHARED / "realtime/rcb_realtime.py").read_bytes(), 0o644)
            files["environment/sim/rcb_bigym2.py"] = (tool, 0o644)
            files["environment/sim/instance.json"] = (raw, 0o644)
            files["tests/grade.py"] = ((std / "grade.py").read_bytes(), 0o644)
        out[task_dir(fam, mode)] = files
    return out


def normalized(planned: dict, normalize) -> dict:
    """Write the tasks to a scratch tasks/ dir, run task_conventions.normalize() on each and read them back."""
    out = {}
    with tempfile.TemporaryDirectory(prefix="bigym2_gen_") as td:
        for name, files in planned.items():
            for rel, (data, mode) in files.items():
                p = pathlib.Path(td) / name / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                os.chmod(p, 0o755 if mode & 0o100 else 0o644)
        for name in planned:
            normalize(pathlib.Path(td) / name)
        for name in planned:
            t = pathlib.Path(td) / name
            out[name] = {
                p.relative_to(t).as_posix(): (p.read_bytes(), 0o755 if p.stat().st_mode & 0o100 else 0o644)
                for p in sorted(t.rglob("*"))
                if p.is_file() and "__pycache__" not in p.parts
            }
    return out


def sync(task: pathlib.Path, files: dict, check: bool) -> list[str]:
    """Make `task` hold exactly `files`. Returns the differences (written unless check)."""
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
                os.chmod(p, 0o755 if mode & 0o100 else 0o644)
    if not check and task.exists():
        for d in sorted((p for p in task.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
            if not any(d.iterdir()):
                d.rmdir()
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("render", "check"))
    a = ap.parse_args()
    check = a.cmd == "check"
    tasks = json.loads((HERE / "tasks.json").read_text())["tasks"]
    version = (ROOT / "images/bigym2/VERSION").read_text().strip()
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize

    diffs, made = [], set()
    for fam, task in tasks.items():
        for name, files in normalized(plan(fam, task, version), normalize).items():
            made.add(name)
            diffs += sync(ROOT / "tasks" / name, files, check)
    for t in sorted((ROOT / "tasks").glob("bigym2-*")):
        if t.is_dir() and t.name not in made:
            diffs.append(f"stale  {t.name} (no instance for it: remove it)")
    for d in diffs:
        print(d)
    print(f"{'checked' if check else 'generated'} {len(made)} BiGym 2.0 task dirs ({len(tasks)} instances): {len(diffs)} difference(s)")
    return 1 if (check and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
