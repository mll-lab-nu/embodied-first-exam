#!/usr/bin/env python3
"""Generate self-contained unlimited tasks from harbor_templates/topogym (TopoGym tasks only).
Adapted from robot_coding_bench's scripts/robowits_mk_task.py (fa59c1a6).
usage: scripts/topogym_mk_task.py <family> [--eval-index 0 | --variation seeded --scene-seed N | --instance <instance.json>]
                                  [--difficulty "<paragraph>"] [--python <simulator python>]
  <family>      a key of rcb_topogym.TASKS (the folder slug becomes topogym-<family-with-dashes>-i<NN>)
  --oracle      the human-written reference solution; copied to solution/oracle_<family>.py and recorded by solution/solve.sh.
                Without it solve.sh says there is none and the oracle agent scores 0
  --instance    an existing frozen instance to copy; otherwise one is made with `rcb_topogym.py make-instance` (needs the GPU)
  --python      the interpreter that has topogym + a GPU (default .venv-gs121-nyx/bin/python), for make-instance / describe
Then: run-oracle + replay, `harbor run -a oracle` / `-a nop`, scripts/topogym_mk_limited.py, and `cd tasks && harbor add --scan .`.
Shared files are copied from one tooling generation. New packages record its version;
historical frozen generations keep their pinned bytes (ci_checks/check-tooling-identity.sh).
Private sweeps use --tasks-root, --build-root, --slug, --image and --agent-wall-clock-s (default 21600, at most 36000).
[task].name = "robot-coding-bench/<slug>" and [metadata].difficulty = the variation record's tier (docs/rcb/TAXONOMY.md)."""
import argparse, json, os, pathlib, shutil, subprocess, sys

sys.dont_write_bytecode = True        # importing the task's tooling must not leave __pycache__ in a task directory
root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from topogym.tasks.goal_description import TASK_IDS as GOAL_TASKS, render_goal
from topogym_rules import details_section
from topogym.utils.io import make_asset_tree_readable
from cuda_profiles import image_tag
TEMPLATE = root / "harbor_templates/topogym/unlimited"
TOOL = root / "harbor_templates/topogym/common/rcb_topogym.py"
TOOLING_VERSION = "3"
SHARED = ["environment/Dockerfile", "environment/docker-compose.yaml", "tests/Dockerfile",
          "tests/docker-compose.yaml", "tests/grade.py"]
IMAGE = image_tag(root)
BUDGET_S = 21600
MAX_BUDGET_S = 36000                  # knot_untying's budget (10 h); every other family 21600


def tier_of(inst: dict):
    """[metadata].difficulty (docs/rcb/TAXONOMY.md): the tier of the instance's variation record, None if it has none."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("variation_records", root / "topogym/config/variation_records.py")
    records = importlib.util.module_from_spec(spec); spec.loader.exec_module(records)
    vid = inst.get("resolved_variation_id") or inst["variation_id"]
    return next((r["difficulty"] for r in records.RECORDS if r["task_id"] == inst["topogym_task"]
                 and vid in (r["variation_id"], *r["aliases"])), None)


def startup_instruction(fam: str, *, limited: bool = False) -> str:
    """Shared startup guidance, embedded in each self-contained task instruction."""
    timing = (
        "Recent Cast Coil starts on the benchmark host took about 120 seconds; this is an observation, not a deadline."
        if fam == "cast_coil" else
        "Scene initialization and kernel compilation can take minutes."
    )
    common = f"""## Startup and long-running commands

- {timing} Actual time depends on the task, hardware, and load.
  Quiet logs during initialization do not by themselves mean failure. Use `python -u` for unbuffered script output.
- A command tool's wait/yield interval (for example, `yield_time_ms=30000`) is not the command's lifetime.
  When a command is still running, retain its process/session identifier and continue waiting for that same command.
  With Codex's `exec_command`, expose the complete result, including `session_id` and `exit_code`, rather than only
  `output` (for example, `text(r)` instead of only `text(r.output)`). Continue it with `write_stdin` using the returned
  `session_id` and no input. An outer JavaScript wrapper saying `Script completed` does not prove Python has exited.
  Use the corresponding wait/status operation if another command tool is provided.
- Do not rerun a command just because its first wait returned partial logs. Confirm the original process has exited
  before starting a replacement; if cancellation is necessary, stop only your own identified process and confirm exit.
- Keep the task's simulator and sensor configuration. Waiting does not extend the actual agent wall-clock budget.
"""
    if limited:
        return common + """- Connect with `Robot()` and let its retry loop wait for the existing service (default connection budget: 600 seconds,
  still subject to the actual agent deadline). Do not try to start or rebuild a simulator yourself.
- Reconnecting a client accesses the same episode; it does not reset the world. While an action request is still
  running, wait for its original command rather than resubmitting the same actions, which could execute them twice.
"""
    return common + """- Keep at most one live simulator process in this trial at a time. A new Python process calling `Session(...)`
  creates another scene and consumes more GPU memory; separate replay/render CLI commands also create scenes.
- Reuse the initialized Session for observations, actions, reset, and replay. Avoid separate initialization-only probes:
  put the first useful actions and trajectory save in the same script that initializes the simulator.
- Initialization consumes the agent budget. Save a real trajectory as soon as practical and keep saving progress.
"""


def run_tool(python, *args, tool=TOOL) -> dict:
    env = dict(os.environ, RCB_SESSION_LOG="", PYTHONPATH=str(root))
    cmd = [python, str(tool), *map(str, args)]
    if os.environ.get("TOPOGYM_TOOL_IMAGE"):
        mount = os.environ["TOPOGYM_RUN_ROOT"]
        cmd = ["docker", "run", "--rm", "--runtime", "nvidia", "--gpus", "device=" + os.environ.get("TOPOGYM_GPU_UUID", "0"),
               "--label", "topogym.difficulty-run=" + os.environ["TOPOGYM_RUN_ID"],
               "-e", "NVIDIA_DRIVER_CAPABILITIES=all", "-e", "RCB_SESSION_LOG=",
               "-e", "NVIDIA_VISIBLE_DEVICES=" + os.environ.get("TOPOGYM_GPU_UUID", "0"),
               "-v", f"{mount}:{mount}", "-w", mount, os.environ["TOPOGYM_TOOL_IMAGE"],
               "python", str(tool), *map(str, args)]
        if os.environ.get("TOPOGYM_RESOURCE_LABELS"):
            from difficulty_delivery import label_args
            cmd[2:2] = label_args(json.loads(os.environ["TOPOGYM_RESOURCE_LABELS"])) + [
                "--user", os.environ["TOPOGYM_HOST_UID"] + ":" + os.environ["TOPOGYM_HOST_GID"], "-e", "HOME=/tmp"]
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
    if p.returncode or not lines:
        err = p.stderr[p.stderr.rfind("Traceback"):] if "Traceback" in p.stderr else p.stderr[-3000:]
        sys.exit(f"rcb_topogym.py {args[0]} failed (rc={p.returncode}):\n{err[-4000:]}")
    return json.loads(lines[-1])


def robot_words(d: dict) -> str:
    return d["robot_spec"]["description"].split(" (TopoGym")[0]


def layout_words(d: dict) -> str:
    parts = []
    for arm in d["arms"]:
        n = sum(1 for x in d["action_layout"] if not x.endswith("_gripper") and x in d["kinematics"]["joint_names"]
                and any(j["name"] == x and j["group"] == f"arm_{arm}" for j in d["robot_spec"]["joints"]))
        lo, hi = d["limits"][d["action_layout"].index(f"{arm}_gripper")]
        parts.append(f"arm `{arm}`: {n} joint targets (rad), then `{arm}_gripper` = opening width (m, {lo:g} closed .. {hi:g} open)")
    return "; ".join(parts)


def objects_words(d: dict) -> str:
    out = []
    for n, o in d["objects"].items():
        if o.get("material") in ("particle", "fem"):
            out.append(f"`{n}` (deformable, {o['material']})")
        else:
            out.append(f"`{n}`" + (" (fixed)" if o.get("fixed") else ""))
    return ", ".join(out) or "see `s.objects()`"


def conventions(d: dict, fam: str) -> str:
    rs = d["robot_spec"]; arm = d["arms"][0]; tcp = rs["tcp"][d["kinematics"]["tcp_frames"][0]]
    base = ", ".join(f"{v:.3f}" for v in rs["base"]["pose"][:3])
    table = f", table top at z = {d['table_z']:.3f}" if d.get("table_z") else ""
    return f"""## Conventions
- World frame: robot base at ({base}){table}, +z up. Quaternions are **WXYZ**.
- Action ({len(d['action_layout'])}): {layout_words(d)}; absolute position targets tracked by PD controllers, out-of-limit
  values clipped. `s.hold_action()` is the no-op.
- Control runs at {d['control_hz']:g} Hz ({d['physics_substeps']} physics step(s) per control step). There is no step budget; your
  wall-clock budget is {BUDGET_S // 60} min ({BUDGET_S} s). One control step takes about {d['sec_per_step']:.1f} s of wall clock here (the
  simulator keeps a full checkpoint of every physics step), so budget your experiments.
- Grippers: {d['grasp_rules']}.
- Tool frame (TCP, the ee pose and IK frame): {tcp['definition'].split(': ', 1)[1] if ': ' in tcp['definition'] else tcp['definition']}
  `p["top_down_quat"](yaw)` builds a vertical approach whose fingers close along `yaw`; `p["gripper_quat"](yaw, approach)` any other.
- The task succeeds once its predicate has held continuously for {d['stable_duration_s']:g} s; that, or one of its failure predicates,
  ends the simulated episode: later steps are recorded but no longer move the scene (`s.status()["episode_end"]`), and
  `s.reset()` starts over.
- One `Session` per process (Genesis initialises once). Do not call `s.close()` before writing every output.
"""


def goal_words(fam: str, fallback: str, d: dict) -> tuple[str, str]:
    """Use the simulator's instance-specific goal; never guess from a family label."""
    goal = d.get("public_goal")
    if goal is None:
        if fam in GOAL_TASKS:
            raise ValueError("describe.json lacks public_goal; run describe with the updated simulator before generating instructions")
        return fallback, f"Keep the goal satisfied continuously for {d['stable_duration_s']:g} s."
    if goal["task_id"] != fam or goal["stable_duration_s"] != d["stable_duration_s"]:
        raise ValueError("Public goal task or confirmation duration differs from describe.json")
    return goal["summary"], render_goal(goal)


def validate_goal_instance(fam: str, d: dict, instance: dict) -> None:
    from topogym.simulator.config import SimulatorConfig
    frozen_assist = SimulatorConfig(grasp_assist=instance.get("simulator", {}).get("grasp_assist", {"model": "none"})).grasp_assist
    described_assist = SimulatorConfig(grasp_assist=d.get("grasp_assist") or {"model": "none"}).grasp_assist
    if described_assist != frozen_assist:
        raise ValueError("Grasp assistance differs from the frozen instance; regenerate describe.json for this instance")
    goal_words(fam, "", d)
    if fam in GOAL_TASKS:
        goal = d["public_goal"]
        variation = instance.get("resolved_variation_id", instance["variation_id"])
        if (goal["variation_id"], goal["seed"]) != (variation, instance["seed"]):
            raise ValueError("Public goal describes a different variation/seed; regenerate describe.json for this instance")
        frozen_goal = instance.get("public_goal")
        if frozen_goal is not None and frozen_goal != goal:
            raise ValueError("Public goal requirements differ from the frozen instance; regenerate the instance and describe.json together")


def success_rule_of(inst: dict) -> str:
    """The instance's success-rule provenance (rcb_topogym make-instance); older instances only record evaluability."""
    if inst.get("success_rule"):
        return inst["success_rule"]
    return "his (goal_complete)" if inst.get("evaluable_for_task_success", True) else "not evaluable (goal_complete False)"


def grasp_words(inst: dict) -> str:
    """[metadata].grasp: how this instance grasps, from its frozen simulator.grasp_assist (his configuration: the family's
    recommended_grasp_assist() or the tooling's explicit TASKS entry). Names the parts only, never a region centre."""
    ga = (inst.get("simulator") or {}).get("grasp_assist") or {}
    if ga.get("model", "none") == "none":
        return "physical (no assisted grasping)"
    parts = ", ".join(sorted({t["entity"] for t in ga.get("targets", [])}))
    if ga.get("initial_intent") == "close":
        return f"assisted (his {ga['model']} pre-weld: the grippers start closed on {parts})"
    return f"assisted (his {ga['model']} grasp regions on {parts})"


def instruction(fam: str, text: str, d: dict, inst: dict | None = None) -> str:
    arm, cam = d["arms"][0], list(d["cameras"])[0]
    W, H = d["cameras"][cam]["image_size"]
    pred = d["predicate"] or "# (source not available)"
    text, requirements = goal_words(fam, text, d)
    return f"""# TopoGym · {fam} — frozen instance

You control a simulated robot (**{robot_words(d)}**; TopoGym on Genesis 1.2.1 physics, Nyx rendering) via Python.
**Task:** {text}

{requirements}
{details_section(fam, inst, limited=False) if inst is not None else ""}
The scene objects are the task's entities (`s.objects()`: {objects_words(d)}).
Implementation reference: `{d['task_class']}.evaluate_state` (module `{d['task_module']}`).
This is a partial implementation excerpt; delegated helpers, passage history and the shared release/confirmation
checks also apply. The complete public goal requirements are stated above.
```python
{pred.rstrip()}
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed at the end of the replay, else 0. Also leave the script that produced it at `/app/output/gen.py`.

{startup_instruction(fam).rstrip()}

## Tooling (already installed; run `python` from any directory)
```python
from rcb_topogym import Session
s = Session("{fam}", instance="/app/instance.json")   # builds the frozen scene (instance.json) and compiles kernels
s.reset()                          # back to the frozen initial state (unlimited; a restore of the first recorded state)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # objects: name -> position, orientation_wxyz, euler_xyz, bounds, size, velocity
p["move_ee"]("{arm}", pos, quat_wxyz, linear=3)   # IK on the robot's model to a TCP pose, then joint interpolation
p["move_joints"]("{arm}", q_arm); p["set_gripper"]("{arm}", 0.0); p["open_gripper"]("{arm}"); p["hold"](10)
s.ee_pose("{arm}"); s.joint_positions(); s.ik("{arm}", pos, quat_wxyz)    # kinematics helpers (arms: {d['arms']})
s.render_frame("{cam}")         # RGB uint8 ({H}, {W}, 3) from one camera (s.VIDEO_CAMERAS); s.render_grid()
s.render_depth("{cam}")         # float32 ({H}, {W}) z-depth in metres (0 = no reading), pixel-aligned with render_frame
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl, mount
s.robot_spec()                     # joints (limits), grippers (the grasping rule), PD gains, tool frames {d['kinematics']['tcp_frames']}
s.kinematics({{"op": "fk", "q": q}})   # stateless FK / IK on the robot's model; {{"op": "ik", "targets": {{"{d['kinematics']['tcp_frames'][0]}": pose7}}, "seed": q}}
s.joint_velocities(); s.joint_efforts(); s.gripper_width("{arm}")   # measured state in action layout (efforts: the PD drives')
s.object_pose(name); s.object_bounds(name); s.state_sha()          # one object's pose / AABB; the state hash that replays compare
p["object_in_hand"]("{arm}"); p["set_joint_targets"](row, steps=1); p["gripper_quat"](yaw, approach)   # help(p[...])
s.step(action)                     # one low-level action ({len(d['action_layout'])} entries, below) = one control step (1/{d['control_hz']:g} s)
s.record_start(); ...; actions = s.record_stop()   # (T, {len(d['action_layout'])}) actions, one row per control step
s.status()                         # {{'success', 'progress', 'sim_steps', 'resets', 'state_sha', 'episode_end'}}
s.replay(actions)                  # resets, replays open-loop, returns status  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state and writes a tiled camera video
```
The primitives are deliberately thin (IK moves, joint moves, gripper, hold): grasping, placing and every other skill
are yours to build from them.

CLI equivalent of the grader:
`python /opt/tools/rcb_topogym.py replay --task {fam} --instance /app/instance.json --traj /app/output/trajectory.npz`

{conventions(d, fam)}"""


def readme(slug: str, fam: str, text: str, d: dict, ei: int, variation: str, seed: int, difficulty: str, oracle: bool,
           success_rule: str = "", inst: dict | None = None) -> str:
    text, requirements = goal_words(fam, text, d)
    ref = (f"`solution/oracle_{fam}.py`, written for this instance with the tooling's primitives; `solution/solve.sh` records it into a\n"
           f"trajectory." if oracle else
           "None yet: `solution/solve.sh` says so and exits 1 (the oracle agent scores 0). A reference solution must be\n"
           "written for this instance (assisted grasping, if the family enables it, is the same for the oracle and the agent).")
    return f"""# {slug}

| | |
|---|---|
| Simulator / robot | TopoGym (Genesis 1.2.1 on CUDA, Nyx RGB) / {d['robot_spec']['name']} ({robot_words(d)}) |
| Family / instance | `{fam}` / variation `{variation}`, seed {seed} (eval index {ei}), frozen in `environment/instance.json` |
| Task type / tier | trajectory / privileged |
| Base image | `{IMAGE}` (built locally with `scripts/build_images.sh topogym`; needs an NVIDIA GPU: `environment/docker-compose.yaml`) |
| Grasping | {d['grasp_rules'].split(':')[0]} |
| Success rule | {success_rule} |
| Agent budget | {BUDGET_S} s |

## Goal
{text}

{requirements}
{details_section(fam, inst, limited=False) if inst is not None else ""}
## Difficulty
{difficulty}

## Reference solution
{ref}

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`), plus `/logs/verifier/replay.mp4`. The physics runs on the
GPU, which is not bit-deterministic: the final-state hashes (`deterministic`) and the rebuilt frozen scene
(`instance_ok`) are reported, not required (robot_coding_bench's GPU-backend rule).
"""


def task_toml(slug: str, fam: str, text: str, d: dict, ei: int, variation: str, seed: int, hours: float, level=None,
              inst: dict | None = None) -> str:
    # The verifier replays the trajectory 3 times (2 checks + the video) at the simulator's speed: at most the agent's
    # budget each, since the agent's own run took at least that long.
    vt = 3 * BUDGET_S + 900
    level = f'difficulty = "{level}"               # the variation\'s tier (docs/rcb/TAXONOMY.md)\n' if level else ""
    if inst is not None:   # provenance of the grasp mode, the success rule and a re-prepared initial state (instance.json)
        level += (f"grasp = {json.dumps(grasp_words(inst))}\n"
                  f"success_rule = {json.dumps(success_rule_of(inst))}\n")
        if inst.get("initial_state_provenance"):
            level += f"initial_state = {json.dumps(inst['initial_state_provenance'])}\n"
    return f"""schema_version = "1.3"
artifacts = ["/app/output/"]

[task]
name = "robot-coding-bench/{slug}"
description = {json.dumps(f"TopoGym {fam} ({d['robot_spec']['name']}, Genesis): produce one replayable trajectory. {text} Frozen scene instance (variation {variation}, seed {seed}).")}
authors = [{{ name = "jianwen" }}]
keywords = ["robotics", "topogym", "genesis", "{d['robot_spec']['name']}", "code-as-policy", "trajectory", "{fam}"]

[metadata]
author_name = "jianwen"
tooling_version = "{TOOLING_VERSION}"
task_type = "trajectory"          # trajectory | policy   (see docs/rcb/PROTOCOL.md)
simulator = "topogym"             # TopoGym on Genesis 1.2.1 (CUDA physics, Nyx RGB)
robot = "{d['robot_spec']['name']}"
family = "{fam}"
tier = "privileged"               # privileged (state-based perception) | perception (RGB-D models)
{level}instance_seed = {seed}                 # scene = environment/instance.json (variation {variation}, eval index {ei}); identity = dataset.toml digest
expert_time_estimate_hours = {hours}

[verifier]
timeout_sec = {float(vt)}
environment_mode = "separate"     # verifier runs in its own sandbox (tests/Dockerfile); the agent container is gone by then

[agent]
timeout_sec = {float(BUDGET_S)}             # Agent wall-clock budget; verifier has its own budget
# egress: Harbor default (public). `scripts/set_agent_egress.py allowlist` closes it to the model APIs.

[environment]
build_timeout_sec = 3600.0
cpus = 4
memory_mb = 16384

[verifier.environment]
build_timeout_sec = 1800.0
"""


def main() -> None:
    global BUDGET_S, IMAGE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("family"); ap.add_argument("--eval-index", type=int); ap.add_argument("--oracle", default=None)
    ap.add_argument("--variation"); ap.add_argument("--scene-seed", type=int); ap.add_argument("--task-parameters")
    ap.add_argument("--tasks-root", type=pathlib.Path, default=root / "tasks")
    ap.add_argument("--build-root", type=pathlib.Path, default=root / "runs/task_build")
    ap.add_argument("--slug"); ap.add_argument("--image", default=IMAGE)
    ap.add_argument("--agent-wall-clock-s", type=int, default=BUDGET_S)
    ap.add_argument("--instance", default=None); ap.add_argument("--difficulty", default=None)
    ap.add_argument("--hours", type=float, default=None, help="expert_time_estimate_hours")
    ap.add_argument("--python", default=str(root / ".venv-gs121-nyx/bin/python"))
    ap.add_argument("--reuse-describe", action="store_true", help="re-render the texts from runs/task_build/<slug>/describe.json (no GPU)")
    a = ap.parse_args()
    if not 0 < a.agent_wall_clock_s <= MAX_BUDGET_S:
        ap.error(f"--agent-wall-clock-s must be in 1..{MAX_BUDGET_S}")
    if a.variation is not None or a.scene_seed is not None:
        if a.variation is None or a.scene_seed is None or a.eval_index is not None or a.instance:
            ap.error("--variation and --scene-seed must be paired, without --eval-index/--instance")
    elif not a.instance and a.eval_index is None:
        a.eval_index = 0  # old invocations retain i00 behavior
    BUDGET_S, IMAGE = a.agent_wall_clock_s, a.image
    sys.path.insert(0, str(TOOL.parent))
    import rcb_topogym as M                 # the registry only (no simulator import)
    fam = a.family; spec = M.TASKS[fam]
    slug = a.slug or f"topogym-{fam.replace('_', '-')}-i{a.eval_index or 0:02d}"
    import re
    if not re.fullmatch(r"topogym-[a-z0-9-]+", slug):
        ap.error("invalid task slug")
    dst = a.tasks_root.resolve() / slug
    for d in ("environment", "tests", "solution"):
        (dst / d).mkdir(parents=True, exist_ok=True)
    if dst != TEMPLATE:
        for f in SHARED:
            shutil.copy(TEMPLATE / f, dst / f)
        for f in dst.glob("solution/oracle_*.py"):
            f.unlink()
    tool = dst / "environment/rcb_topogym.py"
    shutil.copy(TOOL, tool)
    for rel in ("environment/Dockerfile", "tests/Dockerfile"):
        p = dst / rel
        base = os.environ.get("TOPOGYM_AGENT_IMAGE", IMAGE) if rel.startswith("environment/") else IMAGE
        p.write_text(re.sub(r"^FROM .*", f"FROM {base}", p.read_text(), flags=re.M))
    shutil.copy(dst / "environment/rcb_topogym.py", dst / "tests/rcb_topogym.py")
    inst_path = dst / "environment/instance.json"
    if a.instance:
        if pathlib.Path(a.instance).resolve() != inst_path.resolve():
            shutil.copy(a.instance, inst_path)
        assets = pathlib.Path(a.instance).parent / "instance_assets"
        if assets.is_dir() and assets.resolve() != (dst / "environment/instance_assets").resolve():
            shutil.copytree(assets, dst / "environment/instance_assets", dirs_exist_ok=True)
    else:
        selection = ["--variation", a.variation, "--scene-seed", a.scene_seed] if a.variation else ["--eval-index", a.eval_index]
        if a.task_parameters:
            selection += ["--task-parameters", a.task_parameters]
        run_tool(a.python, "make-instance", "--task", fam, *selection, "--out", inst_path, tool=tool)
    assets = dst / "environment/instance_assets"
    assets.mkdir(exist_ok=True)
    (assets / ".gitkeep").touch()   # git keeps no empty directory, and both Dockerfiles COPY instance_assets/
    make_asset_tree_readable(assets)
    shutil.copytree(assets, dst / "tests/instance_assets", dirs_exist_ok=True)
    make_asset_tree_readable(dst / "tests/instance_assets")
    shutil.copy(inst_path, dst / "tests/instance.json")
    inst = json.loads(inst_path.read_text())
    if inst["task"] != fam or (a.eval_index is not None and inst["eval_index"] != a.eval_index):
        raise ValueError("frozen instance task/eval-index mismatch")
    a.eval_index = inst["eval_index"]
    build = a.build_root.resolve() / slug; build.mkdir(parents=True, exist_ok=True)
    if a.reuse_describe:
        d = json.loads((build / "describe.json").read_text())
    else:
        d = run_tool(a.python, "describe", "--task", fam, "--instance", inst_path, tool=tool)
        (build / "describe.json").write_text(json.dumps(d, indent=1))
    validate_goal_instance(fam, d, inst)
    if a.oracle:
        if pathlib.Path(a.oracle).resolve() != (dst / f"solution/oracle_{fam}.py").resolve():
            shutil.copy(a.oracle, dst / f"solution/oracle_{fam}.py")
        solve = ("#!/bin/bash\n# Oracle: run the human-written reference solution (kept in solution/, never in the agent image) and record it.\n"
                 "set -e\nmkdir -p /app/output\n"
                 f"python /opt/tools/rcb_topogym.py run-oracle --task {fam} --instance /app/instance.json --code /solution/oracle_{fam}.py --out /app/output/trajectory.npz\n"
                 f"cp /solution/oracle_{fam}.py /app/output/gen.py\n")
    else:   # no reference solution: the oracle agent says so and scores 0
        solve = (f"#!/bin/bash\n# No reference solution for this family yet: the oracle agent scores 0.\necho 'no reference solution for {fam}' >&2\nexit 1\n")
    (dst / "solution/solve.sh").write_text(solve); (dst / "solution/solve.sh").chmod(0o755)
    (dst / "tests/test.sh").write_text(
        "#!/bin/bash\n# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) in a fresh process.\n"
        "# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/rcb/PROTOCOL.md).\nmkdir -p /logs/verifier\n"
        "# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent\n"
        "# left there (a planted reward, a symlink) can count. rm never follows symlinks.\n"
        "find /logs/verifier -mindepth 1 -maxdepth 1 ! -name test-stdout.txt -exec rm -rf {} +\n"
        f"python /tests/grade.py --family {fam} --instance /tests/instance.json --traj /app/output/trajectory.npz --repeat 2 \\\n"
        "  2> /logs/verifier/grade.log\n")
    (dst / "tests/test.sh").chmod(0o755)
    difficulty = a.difficulty or (f"{robot_words(d).capitalize()} with a {len(d['action_layout'])}-D joint-target action space at {d['control_hz']:g} Hz; "
                                  f"success needs the task's predicate (above) held for {d['stable_duration_s']:g} s. Grasping: "
                                  f"{d['grasp_rules'].split(':')[0]}.")
    hours = a.hours if a.hours is not None else (0.5 if spec.get("fixture") else 2.0)
    goal_text, _ = goal_words(fam, spec["text"], d)
    (dst / "instruction.md").write_text(instruction(fam, goal_text, d, inst))
    (dst / "README.md").write_text(readme(slug, fam, goal_text, d, a.eval_index, inst["variation_id"], inst["seed"], difficulty, bool(a.oracle),
                                          success_rule_of(inst), inst))
    (dst / "task.toml").write_text(task_toml(slug, fam, goal_text, d, a.eval_index, inst["variation_id"], inst["seed"], hours, tier_of(inst), inst))
    print("generated", slug, "oracle:", "yes" if a.oracle else "none", "state_sha:", inst["state_sha"], "sec/step:", d["sec_per_step"])


if __name__ == "__main__":
    main()
