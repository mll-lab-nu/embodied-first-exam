#!/usr/bin/env python3
"""Render the IKEA MuJoCo tasks: tasks/ikea-<task>-i00-privileged (images/ikea-mujoco/README.md).

usage: python3 scripts/ikea_mujoco/mk_tasks.py [--check] [--demos <ikea tree>/demos] [task ...]
  no task   every task in bindings.json
  --check   write nothing; exit 1 if a task directory would change
  --demos   also (re)write solution/trajectory.npz from <demos>/<demo>/actions.npz (needs numpy; <demo> = the task's
            tasks.json "demo", default the task name): the demo's ctrl rows, float64, unchanged, in the task's layout
            (ctrl, substeps, timestep, actuators); a demo recorded at tasks.json "demo_substeps" (a multiple of 4)
            physics steps per row has each row repeated demo_substeps / 4 times

Ends with scripts/task_conventions.normalize, like every generator. Inputs (all in scripts/ikea_mujoco/):
  tasks.json     per task: title, goal, success requirements and mechanism in plain words, robot type
  assets.json    sha256 of every scene file in the image (stage_context.py); each task's runtime_binding.json repeats
                 its scene's files
  bindings.json  per task, what the image's scene builds to (rcb_ikea.py info inside the image): initial-state hash,
                 actuators, timestep; the image reference and id (a task's own "image" overrides the default one: a
                 scene added in a later image version)
  evidence.json  per task, the Harbor oracle / nop checks (scripts/robotangle/harbor_check.py style records) and the
                 measured replay wall time, which sets the verifier's timeout
  shared/        rcb_ikea.py (the agent's tooling and the replay), grade.py (the verifier), copied unchanged (PROTOCOL D9)
"""
from __future__ import annotations
import argparse, filecmp, hashlib, json, pathlib, re, shutil, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASKS = ROOT / "tasks"
SHARED = HERE / "shared"
VERSION = (ROOT / "images/ikea-mujoco/VERSION").read_text().strip()
AGENT_S = 10800                 # 3 h wall clock, both modes (owner 2026-10-16: as RoboARC; PROTOCOL v2.0 H.7)
TEXTS = json.loads((HERE / "tasks.json").read_text())
ASSETS = json.loads((HERE / "assets.json").read_text())
BIND = json.loads((HERE / "bindings.json").read_text())
IMAGE = BIND["image"]["reference"]          # the one image of every task (a task's own bindings "image" would override it)
assert IMAGE == f"ghcr.io/mll-lab-nu/eai-ikea-mujoco:{VERSION}", (IMAGE, VERSION)   # our registry name and version
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as TC  # noqa: E402  the protocol's conventions: every generator ends with normalize(task_dir)
# Work in progress, not shipped (owner 2026-10-16, the YAMLab rule: a task ships only with an oracle): no reference passes
# the arm joint-speed clamp in either mode yet; each needs a new closed-loop reference. Rendered to
# scripts/ikea_mujoco/wip/tasks/ (not tasks/, not in any manifest) so the work stays on the branch.
WIP = {
    # the second batch (2026-10-16): in WIP until its reference passes every acceptance gate on the final physics
    "stenerik": ("no reference passes yet: the closed-loop build seats all six screws, joins both supports and peels the "
                 "four pads on the final physics, but its pad presses stay below the 1 N / 0.3 s bond gate "
                 "(scripts/ikea_mujoco/wip/oracles/stenerik/)"),
    "kyrre": ("no reference passes: the author's demo (within the joint-speed limits) loses screw 2-1 at its hole under "
              "the final physics (4 of 9 welds), and one replay of it takes 12,316 s on a dedicated Quest core (85 % of "
              "the budget); every time-warp of the demo breaks it by the second screw (scripts/ikea_mujoco/wip/oracles/kyrre/)"),
    "uppsta": ("timing: the closed-loop reference passes final_check (scripts/ikea_mujoco/wip/oracles/uppsta/), but one "
               "successful replay takes about 6000 s on a fast host (guide run 5911 / 6139 s on ws2; a demo-length replay "
               "8407 s on a Quest Xeon 6230R core) against the 4320 s bar: the two screw drives cost 22-26 ms per row "
               "(1300-2100 contacts with the helical thread geoms), about 4400 s, and the demo already moves at the limits "
               "where nothing is in contact"),
    "burvik": ("no reference passes under the prism contact rule and the arm joint-speed clamp: the handle is never pushed "
               "through the two top holes (8 variants; not a fit problem: the prism is inscribed in the rod's cylinder, as in "
               "RoboARC, and the seated rods clear the top by >= 4 mm)"),
}
WIP_TASKS = HERE / "wip" / "tasks"
# The agent's egress (PROTOCOL §2.11, H.6): the two lines `scripts/set_agent_egress.py allowlist` writes, with that
# script's HOSTS (read from its text: it acts on import), in both modes.
_HOSTS = re.findall(r'"([^"]+)"', re.search(r"(?ms)^HOSTS = \[(.*?)\]", (ROOT / "scripts/set_agent_egress.py").read_text()).group(1))
EGRESS = ('network_mode = "allowlist"      # model APIs and package registries (scripts/set_agent_egress.py); PROTOCOL §2.11\n'
          "allowed_hosts = [" + ", ".join(f'"{h}"' for h in _HOSTS) + "]\n")


def default_tasks() -> list[str]:
    """Every task in bindings.json; the WIP ones only where their render directory exists (not on main)."""
    return sorted(t for t in BIND["tasks"] if t not in WIP or WIP_TASKS.is_dir())


def task_dir(t: str, mode: str = "privileged") -> pathlib.Path:
    return (WIP_TASKS if t in WIP else TASKS) / name(t, mode)


# Closed-loop references (built phase by phase on the final physics with true-state feedback, recorded as the executed
# rows; scripts/ikea_mujoco/oracles/<task>/): the task's one reference for both modes. task -> words for the README.
CLOSED_LOOP = {
    "eket": ("a closed-loop reference built on the final physics by `scripts/ikea_mujoco/oracles/eket/build_ref.py`: the "
             "demo as the phase guide, each held panel servoed onto the unclamped demo's recorded relative-pose track "
             "(damped-least-squares Jacobian IK on the TCP) and paused at each slide until its gate accepts; the rows are "
             "the targets executed after the joint-speed clamp"),
    "ikea365": ("a closed-loop reference built on the final physics by `scripts/ikea_mujoco/oracles/ikea365/build_ref.py`: "
                "the demo through the clamp as the phase guide; the right hand threads the returned screw itself before "
                "releasing it; the screwdriver is centred on the true screw axis, spins with a 5-15 N axial push and goes "
                "torque-free at the seat so the welds engage on an unloaded screw; guide tracks (damped-least-squares IK) "
                "steer the hands onto member B, the turned stand and the bowl; the rows are the targets executed after the "
                "joint-speed clamp"),
    "vesken": ("a closed-loop reference built on the final physics by `scripts/ikea_mujoco/oracles/vesken/vesken_oracle.py`: "
               "the demo as the phase guide, one operation per snap; each grasp approach offset to where the part really is, "
               "each carried part held on its reference pose (near the host: on its connector error) by an integral loop "
               "through damped-least-squares IK, a gentle press until the weld engages, one arm move re-pathed in joint "
               "space to avoid a self-contact; the rows are the targets executed within the joint-speed limits"),
    "uppsta": ("a closed-loop reference built on the final physics by `scripts/ikea_mujoco/wip/oracles/uppsta/search.py` "
               "(`uppsta_oracle.py`): the guide is the author's demo (each 2.5 ms tick reached over its two rows) run in the "
               "scene without the prism rule, where it assembles the block; segment by segment (the arms' releases), each "
               "grasp approach offset to where the part really is, each carried part held on its guide pose (relative to "
               "the board near it) by an integral loop through damped-least-squares IK, the hex key's tip servoed onto the "
               "hole's axis, a screw's spin matched modulo 60 degrees, a part pressed a little deeper before its release "
               "where it would tip over; the rows are the targets executed within the joint-speed limits"),
}


# A task's one reference for both modes that is not a closed-loop build (e.g. the author's speed-limited demo, unchanged,
# or a demo time-dilated to the joint-speed limits), kept at scripts/ikea_mujoco/oracles/<task>/<task>.npz. task -> words.
OWN_REFS: dict = {
    "stegesund": ("the author's speed-limited demo (`stegesund_vlim`), unchanged (`scripts/ikea_mujoco/oracles/stegesund/`): "
                  "every row is within the joint-speed limits (from the keyframe ctrl; the largest step is the limit itself), "
                  "so the clamp never changes a row, and it passes the terminal rules as sent (it ends released and at rest)"),
}


def ref_words(t: str):
    return CLOSED_LOOP.get(t) or OWN_REFS.get(t)


def closed_loop_ref(t: str):
    """The task's own reference file (CLOSED_LOOP or OWN_REFS), None if it has none."""
    for d in (HERE / "oracles" / t, HERE / "wip" / "oracles" / t):      # a WIP task's reference lives under wip/oracles/
      for f in (d / f"{t}_ref.npz", d / f"{t}.npz"):
        if ref_words(t) and f.is_file():
            return f
    return None


TAILS = {  # task -> what its reference's release tail (scripts/ikea_mujoco/tails/<task>.npy) does; the demo ended holding a part
    "variera": "both grippers open and the arms hold for 0.6 s (240 rows): the demo ended with the left hand still closed on "
               "the screwdriver, which the terminal rules' release check refuses",
}
EVID = json.loads((HERE / "evidence.json").read_text()) if (HERE / "evidence.json").is_file() else {}


def image(t: str) -> dict:
    return BIND["tasks"][t].get("image", BIND["image"])


def robot_text(t: str) -> dict:
    """the robot's texts (tasks.json robots), with the task's own "robot_text" entries (e.g. actuator names) on top"""
    x = TEXTS["tasks"][t]
    return {**TEXTS["robots"][x["robot"]], **x.get("robot_text", {})}


def demo(t: str) -> str:
    return TEXTS["tasks"][t].get("demo", t)


def keyframe(t: str) -> str:
    return TEXTS["tasks"][t].get("keyframe", "home")


def demo_repeat(t: str) -> int:
    n = int(TEXTS["tasks"][t].get("demo_substeps", 4))
    assert n % 4 == 0, t
    return n // 4


def name(t: str, mode: str = "privileged") -> str:
    return f"ikea-{t}-i00-{mode}"


def _base_timeout(t: str) -> int:
    wall = EVID.get(t, {}).get("replay_wall_s")
    return int(max(3600, 3 * wall + 600)) if wall else 7200


def verifier_timeout(t: str) -> int:
    """The verifier's time limit: room for the reference's replays on the Harbor host (3 x its wall + 600 s, at least
    3600 s) and for a trajectory of row_cap(t) rows on a slow trial-class CPU (evidence.json `slow_replay_wall_s`: one
    unobserved reference replay on a dedicated Xeon Gold 6230R core, the CPU-only pool hosts' class) with a 1.5x margin and
    600 s to spare. A verifier that times out writes no verdict (an infrastructure failure), so the limit must cover the
    longest trajectory the grader accepts on every host it runs on."""
    e = EVID.get(t, {})
    base, cap = _base_timeout(t), row_cap(t)
    if cap and e.get("slow_replay_wall_s"):
        base = max(base, int(1.5 * cap * e["slow_replay_wall_s"] / e["rows"] + 600) // 60 * 60 + 60)
    return base


def row_cap(t: str) -> int | None:
    """The most rows a trajectory may have: what the verifier's two replays (measured on the reference, at the same time,
    plus the video replay) fit in the Harbor host's timeout with a 1.5x margin and 600 s to spare. None without a
    measurement (WIP). verifier_timeout() then also covers this many rows on a slow host."""
    e = EVID.get(t, {})
    if not (e.get("replay_wall_s") and e.get("rows")):
        return None
    per_row = e["replay_wall_s"] / e["rows"]
    return int((_base_timeout(t) - 600) / (1.5 * per_row)) // 1000 * 1000


def cap_text(t: str) -> str:
    n = row_cap(t)
    if n is None:
        return "There is no step budget."
    b = BIND["tasks"][t]
    return (f"At most {n} rows ({n * 4 * b['timestep']:g} s of simulated time): the grader refuses a longer trajectory "
            "(`bad_trajectory`), because its replays must fit the verifier's time limit.")


def speed_text(t: str, dt: float) -> str:
    """The joint-speed clamp of rcb_ikea.Session.applied(), in words (the standard twin's rule, the same table)."""
    if TEXTS["tasks"][t]["robot"] == "panda":
        lim = (f"at most {2.175 * dt:g} rad per control tick on joints 1-4 (`actuator1`..`actuator4`: 2.175 rad/s) and "
               f"{2.61 * dt:g} rad on joints 5-7 (`actuator5`..`actuator7`: 2.61 rad/s), the Franka Panda's joint velocity limits,")
    else:
        lim = f"at most {3.14159 * dt:g} rad per control tick on every arm joint (3.14159 rad/s, the ViperX 300 s joint velocity limit),"
    return ("Speed rule (the robot's real limits; clamp, not fail; `rcb_ikea.JOINT_SPEED_LIMITS_RAD_S`): each arm joint "
            f"target moves {lim} from the target applied on the previous tick; a target that asks for more is moved by "
            "the limit only (`Session.applied()`, in `s.step` and in the grader's replay alike), so a fast row is spread over "
            "the ticks after it. A row within the limit (+1e-9) is applied unchanged. The gripper command is not limited.")


def tick_ms(t: str) -> str:
    e = EVID.get(t, {})
    if e.get("replay_wall_s") and e.get("rows"):
        return f"{1e3 * e['replay_wall_s'] / e['rows']:.1f} ms"
    return "a few ms"


def task_toml(t: str) -> str:
    x, r, b = TEXTS["tasks"][t], robot_text(t), BIND["tasks"][t]
    return f'''schema_version = "1.3"
artifacts = ["/app/output/"]

[task]
name = "robot-coding-bench/{name(t)}"
description = "IKEA MuJoCo {x['title']} ({r['short']}, MuJoCo 3.14.0 CPU): produce one replayable trajectory. {x['goal']} Frozen scene (the scene's keyframe '{keyframe(t)}'); physical grasps, no assist."
authors = [{{ name = "Xiaoyu" }}]
keywords = ["robotics", "ikea", "furniture-assembly", "mujoco", "{TEXTS['tasks'][t]['robot']}", "bimanual", "code-as-policy", "trajectory"]

[metadata]
author_name = "Xiaoyu"
task_type = "trajectory"          # trajectory | policy   (see docs/PROTOCOL.md)
simulator = "mujoco"              # plain MuJoCo 3.14.0, CPU float64, the scene's own runtime and mechanism
robot = "{r['robot']}"            # both arms (docs/TAXONOMY.md)
family = "ikea_{t}"
mode = "privileged"               # privileged (state-based tooling, resets) | standard (robot as a service)
dynamics = "static"               # scene dynamics (docs/PROTOCOL.md §2): only the robot and gravity do work; springs, latches and threads are passive
oracle = "full"
grasp = "physical (finger friction; no assisted grasp, no welds to a gripper)"
success_rule = "the scene's success.py (port of the source assembly grader) + the terminal rules (released, at rest, no breakdown), after the last row and after a 1.0 s hold"
instance_seed = 0                 # one frozen scene: images/ikea-mujoco scene {t}, digest {ASSETS['tasks'][t]['digest'][:12]}
expert_time_estimate_hours = {x['hours']}

[verifier]
timeout_sec = {verifier_timeout(t)}.0
environment_mode = "separate"     # verifier runs in its own sandbox (tests/Dockerfile); the agent container is gone by then
network_mode = "no-network"

[agent]
timeout_sec = {AGENT_S}.0             # Agent wall-clock budget; verifier has its own budget
{EGRESS}
[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192

[verifier.environment]
build_timeout_sec = 1800.0
cpus = 4                          # two replays at once (+ the video replay, privileged): the timeouts assume a core each
memory_mb = 8192
'''


def bullets(items) -> str:
    return "\n".join(f"- {s}" for s in items)


def instruction(t: str) -> str:
    x, r, b = TEXTS["tasks"][t], robot_text(t), BIND["tasks"][t]
    dt_ms = 1e3 * b["timestep"]
    return f'''# IKEA MuJoCo · {x['title']} — frozen scene

You control a simulated robot (**{r['words']}**; plain MuJoCo 3.14.0 on the CPU, float64) via Python.
**Task:** {x['goal']}

## Success requirements

{bullets(x['requirements'])}

{TEXTS['terminal']}

The requirements are the scene's own `success.py` (`/opt/ikea/scenes/{t}/success.py`); the terminal rules are the
tooling's (`rcb_ikea.py`, `Session.final_check()`). `s.status()` checks all of it on the current state
(`"goal"` = success.py, `"released"`, `"at_rest"`, `"breakdown"`, `"report"` = success.py's details);
`s.final_check()` is the grader's verdict on your rows (the current state, then the 1.0 s hold).

## Physics and mechanism

- Parts move only through contact with the robot, gravity and the scene's own mechanism. {x['mechanism']}
- Grasps are physical: friction from the finger contacts. Nothing attaches a part to a gripper, and there is no assist.
- The scene (model, solver settings, mechanism) is frozen. The grader builds its own copy; changing the model or the
  scene files in your container has no effect on the grade.

This is a *fixed scene*: the parts and the robot start in the same state at every reset (the scene's keyframe `{keyframe(t)}`).
You may reset and retry as many times as you want, read any simulator state, and save and restore states. Your
deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process, twice, and scored 1 if both replays pass
`final_check()` (the requirements and the terminal rules at the end of your rows and after the 1.0 s hold) and end in
the same state, else 0. Also leave the script that
produced it at `/app/output/gen.py`. Save a real trajectory as soon as practical and keep saving progress; do not stop
early.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_ikea import Session
s = Session("{t}")                   # builds the frozen scene /opt/ikea/scenes/{t} (scene.py load())
s.model, s.data                       # the MuJoCo MjModel / MjData (privileged: read anything; mujoco is importable)
s.S                                   # the scene object: s.S.mech (mechanism state), s.S.success(), s.S.task (task.json)
s.actuators                           # the {b['nu']} actuator names, in action order
s.step(row)                           # one control tick: data.ctrl[:] = s.applied(row) (ctrlrange + speed rule), 4 physics steps (+ the mechanism)
s.run(rows)                           # several ticks
s.hold_action()                       # the current ctrl row (repeating it holds the targets)
s.status()                            # {{'success', 'goal', 'released', 'at_rest', 'breakdown', 'rows', 'state_sha', 'report', ...}}
s.final_check()                       # the grader's verdict: status() now and after holding the last row 1.0 s (state restored)
st = s.get_state(); s.set_state(st)   # save / restore: physics, mechanism and monitor state, and the rows recorded so far
s.reset()                             # a fresh build of the scene: exactly the grader's initial state; clears the rows
s.replay(rows)                        # reset, replay open-loop, return final_check()  -> use this to self-check
s.save_trajectory(path="/app/output/trajectory.npz")   # the rows recorded since the last reset (or pass rows)
```
Scene details: `/opt/ikea/scenes/{t}/` (scene.py, task.json, layout.json, success.py, the mechanism modules, scene.xml).
There is no planner or skill library: inverse kinematics, grasping, screwing and every other skill are yours to build
(MuJoCo's Jacobians, `mujoco.mj_jacSite`, and saved states make that practical).

CLI equivalent of the grader's replay (one replay):
`python /opt/tools/rcb_ikea.py replay --task {t} --traj /app/output/trajectory.npz`

## Conventions
- Action: one row of {b['nu']} actuator controls per control tick, float64: {r['action']}. Out-of-range values are
  clamped to each actuator's ctrlrange. {speed_text(t, 4 * b['timestep'])} The arms are position servos; the actuators'
  gains and force limits are in the model.
- Trajectory file: `ctrl` (N, {b['nu']}) float64, `substeps` = 4, `timestep` = {b['timestep']} (what `save_trajectory`
  writes). Each row is applied for 4 physics steps of {dt_ms:g} ms: a {4 * dt_ms:g} ms control tick ({1e3 / (4 * dt_ms):.0f} Hz).
  {cap_text(t)} One control tick takes about {tick_ms(t)} of wall clock here: budget your experiments against the
  time limit (`## Time limit`).
- World frame: MuJoCo's, +z up, metres; quaternions are MuJoCo's **WXYZ**. Tool frames (sites): {r['tcp']}.
- The episode does not end on success: the grader checks once, after your last row and again after the 1.0 s hold.
  End your rows with the parts released, the arms clear of them and everything at rest.
- One `Session` per process (the scene's modules are imported once).

## External material
{EXTERNAL_TEXT}

## Time limit
You have {AGENT_S} seconds ({AGENT_S // 60} min) to complete this task. This is wall-clock time from the start of your
session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in
`/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have
a better one.
'''


def shared_ref(t: str):
    """The standard twin's reference (solution/oracle_actions.npz, the demo time-dilated to the joint-speed limits by
    scripts/ikea_mujoco/standard/std_reference.py), which is the privileged reference too: the original demos command
    joint targets faster than the robots' real limits and fail under the joint-speed clamp. None for a WIP task."""
    if t in WIP:
        return None
    f = TASKS / name(t, "standard") / "solution/oracle_actions.npz"
    return f if f.is_file() else None


def tail_text(t: str) -> str:
    if t not in TAILS:
        return ""
    return (f", then a release tail of our own appended (`scripts/ikea_mujoco/tails/{t}.npy`): {TAILS[t]}")


def ref_text(t: str, sha: str) -> str:
    head = f"`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `{sha}…`) to `/app/output/`: "
    if closed_loop_ref(t) is not None:
        return (head + f"the task's one reference, shared with the standard twin (its `solution/oracle_actions.npz`, the "
                f"same rows): {ref_words(t)}. It never trips the joint-speed clamp.")
    if shared_ref(t) is not None:
        return (head + f"the task's one reference, shared with the standard twin (its `solution/oracle_actions.npz`, the "
                f"same rows): the robot demo of the IKEA MuJoCo tree (`demos/{demo(t)}/actions.npz`){tail_text(t)}, time-dilated "
                "to the robots' real joint-speed limits by `scripts/ikea_mujoco/standard/std_reference.py`, so the joint-speed "
                "clamp never changes a row. The demo itself commands faster than the limits and fails under the clamp.")
    return (head + f"the robot demo of the IKEA MuJoCo tree (`demos/{demo(t)}/actions.npz`, ctrl rows replayed open-loop from "
            "the keyframe to success.py true), converted to this layout without changing a value "
            f"(`scripts/ikea_mujoco/mk_tasks.py --demos`){tail_text(t)}{repeat_note(t)}.")


def repeat_note(t: str) -> str:
    k = demo_repeat(t)
    return (f"; the demo's rows are {4 * k} physics steps each (the scene's tick), so each is {k} rows here" if k > 1
            else "")


def readme(t: str, traj: pathlib.Path) -> str:
    x, r, b = TEXTS["tasks"][t], robot_text(t), BIND["tasks"][t]
    e = EVID.get(t, {})
    sha = hashlib.sha256(traj.read_bytes()).hexdigest()[:16] if traj.is_file() else "?"
    checks = e.get("checks")
    ver = (f"Harbor checks ({e['date']}, {e['host']}, image `{image(t)['reference']}` id `{image(t)['id'][7:19]}`): "
           + "; ".join(f"`{c['agent']}` scored {c['reward']}" + (f" (two replays, {c['replay_wall_s']} s wall)"
                                                                if c.get("replay_wall_s") else "") for c in checks)
           + ".") if checks else "Harbor oracle / nop checks: pending."
    tm = e.get("timing")
    if tm and "text" in tm:
        ver += f" Reference timing against the {AGENT_S} s budget: {tm['text']}"
    elif tm:
        ver += (f" Reference timing against the {AGENT_S} s budget, by host: one unobserved replay "
                f"{tm['laptop_i9_14900HX_quiet_s']:.0f} s ({100 * tm['laptop_i9_14900HX_quiet_s'] / AGENT_S:.1f} %) on a quiet "
                f"i9-14900HX laptop; the standard twin's live episode {tm['ws2_loaded_standard_live_s']:.0f} s "
                f"({100 * tm['ws2_loaded_standard_live_s'] / AGENT_S:.1f} %) on ws2, a shared and loaded Ryzen 9 7950X (load 25-85 over the day; an earlier run on the same host took 4567 s / 5689 s for gladom / variera).")
    return f'''# {name(t)}

| | |
|---|---|
| Benchmark | IKEA MuJoCo |
| Mode | privileged |
| Twin | `{name(t, 'standard')}` |
| Simulator / robot | `mujoco` / `{r['robot']}` |
| Family / instance | `ikea_{t}` / seed 0 |
| Oracle | `full` |
| Agent time budget | {AGENT_S} s; tokens: protocol default (PROTOCOL §5) |
| Base image | `{image(t)['reference']}` |

## Task
{x['manual']} in plain MuJoCo 3.14.0 (CPU, float64) with {r['words']}: produce one replayable trajectory. {x['goal']}

## Difficulty
Bimanual furniture assembly with physical grasps (no assist), {b['nu']}-D actuator action at {1 / (4 * b['timestep']):.0f} Hz
(4 physics steps of {1e3 * b['timestep']:g} ms per row); the reference needs {e.get('rows', '?')} rows
({e.get('sim_time_s', '?')} s of simulated time).

## Reference solution
{ref_text(t, sha)}

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the scene's initial state in two fresh processes at the same time
(`tests/grade.py`, `tests/rcb_ikea.py replay`: per row `data.ctrl[:] = row; S.step(4)` with the scene's mechanism, then
`final_check()`: `success.py`, released, at rest and no breakdown at the end of the rows and again after a 1.0 s hold of
the last row). Pass iff both replays pass and end in the same state hashes (`deterministic`). The
scene in the verifier image must match `tests/runtime_binding.json` file by file (`instance_exact`) and build to its
initial-state hash (`instance_ok`). Replay video (evidence only, never the verdict): a third process replays the same rows and renders `/logs/verifier/replay.mp4` (CPU OSMesa, 512 x 288, at most 750 frames over the episode and the 1.0 s hold; `video_rendered`).

{ver}

## Details
| | |
|---|---|
| Grasping | physical (finger friction), no assist |
| Success rule | the scene's `success.py` + the terminal rules (released, at rest, no breakdown), at the end of the rows and after a 1.0 s hold |
| Scene | `/opt/ikea/scenes/{t}/` in the image; digest `{ASSETS['tasks'][t]['digest'][:16]}…` (scripts/ikea_mujoco/assets.json) |
| Initial state | sha256 `{b['initial_state_sha256'][:16]}…` of the mjSTATE_INTEGRATION vector |

### Goal
{x['goal']}

### Success requirements
{bullets(x['requirements'])}

### Mechanism
{x['mechanism']}

### Provenance
- Scene and demo: the IKEA MuJoCo tree (`scenes/{t}/`, `demos/{demo(t)}/actions.npz`), MuJoCo 3.14.0, RoboARC rigid settings
  (timestep {1e3 * b['timestep']:g} ms, Newton, 100 iterations, elliptic cones).
- The scene files are not in this repository: the image carries them (`images/ikea-mujoco/README.md`, build context from
  `scripts/ikea_mujoco/stage_context.py`, pinned by `scripts/ikea_mujoco/assets.json`).
'''


SOLVE = '''#!/bin/bash
# Reference solution (privileged): the IKEA MuJoCo robot demo's ctrl rows (README.md, Reference solution).
set -euo pipefail
mkdir -p /app/output
cp /solution/trajectory.npz /app/output/trajectory.npz
'''

ENV_DOCKERFILE = '''# Base image = plain MuJoCo 3.14.0 and the IKEA scenes (images/ikea-mujoco/). Everything task-specific is copied here.
FROM {image}
COPY rcb_ikea.py /opt/tools/rcb_ikea.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
'''

TESTS_DOCKERFILE = '''# Separate verifier sandbox (PROTOCOL §4): the same image with the verifier's own copies of the tooling and the scene's
# binding. Harbor uploads only the declared artifacts (/app/output/), so nothing the agent changed in its container
# reaches the verdict.
FROM {image}
# Replay video (PROTOCOL §4, board 0136; evidence only): MuJoCo's renderer on CPU software OpenGL (OSMesa) and ffmpeg.
# --no-deps: the physics packages (mujoco, numpy) stay the base image's, unchanged (the grader checks the runtime binding).
RUN apt-get update && apt-get install -y --no-install-recommends libosmesa6=25.0.7-2+deb13u1 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir --no-deps PyOpenGL==3.1.10 imageio==2.37.0 imageio-ffmpeg==0.6.0 pillow==12.3.0
ENV MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
COPY grade.py rcb_ikea.py render_video.py video_view.json test.sh runtime_binding.json /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
'''


# PROTOCOL §2.11's honour rule, word for word (main's task_conventions.EXTERNAL_TEXT).
EXTERNAL_TEXT = (
    "You may install packages you need (pip, apt), and you may read anything installed in your container, the "
    "simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web "
    "for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, "
    "or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and "
    "the package registries (PyPI, Debian / Ubuntu archives) only.")


def max_rows_arg(t: str) -> str:
    n = row_cap(t)
    return f" --max-rows {n}" if n else ""


def test_sh(t: str) -> str:
    return f'''#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the scene's initial state in two fresh processes.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/rcb/PROTOCOL.md).
# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent
# left there (a planted reward, a symlink) can count. rm never follows symlinks.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/rcb/PROTOCOL.md §2.6)
# The agent's files are untrusted input (PROTOCOL v2.0 H.1): no link out of /app/output, no FIFO, socket or device.
find /app/output -mindepth 1 \\( -type l -o -type p -o -type s -o -type b -o -type c \\) -delete 2>/dev/null || true
mkdir -p /logs/verifier
python /tests/grade.py --task {t} --binding /tests/runtime_binding.json --traj /app/output/trajectory.npz --repeat 2{max_rows_arg(t)} --budget-s {verifier_timeout(t)} \\
  2> /logs/verifier/grade.log
chmod 0644 /logs/verifier/reward.txt /logs/verifier/reward.json
'''


def binding(t: str) -> str:
    b = BIND["tasks"][t]
    return json.dumps({"schema_version": 1, "task": t, "image": image(t), "runtime": BIND["runtime"],
                       "scene_digest": ASSETS["tasks"][t]["digest"], "scene_files": ASSETS["tasks"][t]["files"],
                       "initial_state_sha256": b["initial_state_sha256"], "nu": b["nu"], "timestep": b["timestep"],
                       "substeps": 4, "actuators": b["actuators"]}, indent=1, sort_keys=True) + "\n"


def video_view(t: str) -> str:
    """The replay video's view (verifier only): the standard twin's camera-rig centre, front and scale."""
    v = json.loads((HERE / "standard/rigs.json").read_text())["tasks"][t]
    return json.dumps({k: v[k] for k in ("center", "front", "scale")}, indent=1) + "\n"


def render(t: str, out: pathlib.Path, demos: pathlib.Path | None) -> None:
    files = {"task.toml": task_toml(t), "instruction.md": instruction(t),
             "environment/Dockerfile": ENV_DOCKERFILE.format(image=image(t)["reference"]),
             "tests/Dockerfile": TESTS_DOCKERFILE.format(image=image(t)["reference"]), "tests/test.sh": test_sh(t),
             "tests/runtime_binding.json": binding(t), "tests/video_view.json": video_view(t), "solution/solve.sh": SOLVE}
    for rel, s in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(s)
        if rel.endswith(".sh"):
            p.chmod(0o755)
    for rel, src in {"environment/rcb_ikea.py": "rcb_ikea.py", "tests/rcb_ikea.py": "rcb_ikea.py",
                     "tests/grade.py": "grade.py", "tests/render_video.py": "render_video.py"}.items():
        shutil.copyfile(SHARED / src, out / rel)
    traj = out / "solution/trajectory.npz"
    shared = closed_loop_ref(t) or shared_ref(t)
    if shared is not None:          # one reference for both modes: the standard twin's, within the joint-speed limits
        shutil.copyfile(shared, traj)
    elif demos is not None:
        import numpy as np
        z = np.load(demos / demo(t) / "actions.npz")
        b = BIND["tasks"][t]
        ctrl = np.ascontiguousarray(z["ctrl"], dtype=np.float64)
        k = demo_repeat(t)
        assert ctrl.shape[1] == b["nu"] and int(z["substeps"]) == 4 * k and float(z["timestep"]) == b["timestep"], t
        assert np.array_equal(ctrl, z["ctrl"]), t
        ctrl = np.repeat(ctrl, k, axis=0)
        tail = HERE / "tails" / f"{t}.npy"          # a release tail appended for the terminal rules (README, TAILS)
        if tail.is_file():
            ctrl = np.concatenate([ctrl, np.load(tail).astype(np.float64)])
        np.savez_compressed(traj, ctrl=ctrl, substeps=np.int64(4), timestep=np.float64(b["timestep"]),
                            actuators=np.array(b["actuators"]))
    else:
        old = task_dir(t) / "solution/trajectory.npz"
        if not old.is_file():
            old = TASKS / name(t) / "solution/trajectory.npz"
        if old.is_file() and old.resolve() != traj.resolve():
            shutil.copyfile(old, traj)
    (out / "README.md").write_text(readme(t, traj))
    TC.normalize(out)


def same(a: pathlib.Path, b: pathlib.Path) -> bool:
    fa = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    fb = sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    return fa == fb and all(filecmp.cmp(a / f, b / f, shallow=False) for f in fa)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tasks", nargs="*")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--demos", type=pathlib.Path, default=None)
    a = ap.parse_args()
    tasks = a.tasks or default_tasks()
    changed = []
    for t in tasks:
        dst = task_dir(t)
        for mode in ("privileged", "standard"):        # a task promoted out of WIP leaves scripts/ikea_mujoco/wip/
            old_wip = WIP_TASKS / name(t, mode)
            if t not in WIP and old_wip.is_dir():
                changed.append(f"{old_wip.name} (removed from {WIP_TASKS.relative_to(ROOT)})")
                if not a.check:
                    shutil.rmtree(old_wip)
        stale = TASKS / name(t)
        if t in WIP and stale.is_dir():        # a WIP task leaves tasks/ (its render lives under scripts/ikea_mujoco/wip/)
            changed.append(f"{name(t)} (moved to {WIP_TASKS.relative_to(ROOT)})")
            if not a.check:
                WIP_TASKS.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    shutil.move(str(stale), str(dst))
                else:
                    shutil.rmtree(stale)
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / name(t)
            twin = task_dir(t, "standard")
            if twin.is_dir():           # normalize reads the twin for the README's key table
                (pathlib.Path(tmp) / twin.name).symlink_to(twin)
            render(t, out, a.demos)
            if dst.is_dir() and same(out, dst):
                continue
            changed.append(name(t))
            if not a.check:
                shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(out, dst)
    print(("would change: " if a.check else "wrote: ") + (", ".join(changed) or "nothing"))
    return 1 if a.check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
