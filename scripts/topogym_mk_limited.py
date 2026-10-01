#!/usr/bin/env python3
"""Generate a limited twin from an unlimited task and harbor_templates/topogym/limited.
Adapted from robot_coding_bench's scripts/robowits_mk_limited.py (fa59c1a6).
usage: scripts/topogym_mk_limited.py <family> <oracle_traj.npz | -> ["<goal in words>"] ["<objects paragraph>"] [--eval-index 0] [--K 1]
  <oracle_traj.npz>  the unlimited oracle's trajectory (its solution/solve.sh output); the limited oracle streams its rows ("-": none)
  "<goal in words>"  the unlimited task's success conditions stated in words (default: the family's task text): the limited
                     agent never sees the predicate
  "<objects ...>"    what the cameras show, one short paragraph starting "Objects here:" (names, colours, sizes; never where
                     things are: no positions, no table height). Default: the task's object names
The limited oracle replays the unlimited oracle's joint targets (every K control steps, default 1 = exact) as
`joint_position` actions. Reads runs/task_build/<unlimited slug>/describe.json (written by topogym_mk_task.py)."""
import argparse, json, os, pathlib, re, shutil, sys
import numpy as np

sys.dont_write_bytecode = True        # importing the task's tooling must not leave __pycache__ in a task directory
from topogym_mk_task import MAX_BUDGET_S, startup_instruction, goal_words, validate_goal_instance
from topogym_rules import details_section, limited_timing

root = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = root / "harbor_templates/topogym/limited"
SHARED = ["environment/Dockerfile", "environment/rcb_client.py", "environment/rcb1.py", "environment/sim/rcb1.py",
          "environment/sim/rcb_limited.py", "environment/sim/server.py", "tests/Dockerfile", "tests/grade.py", "tests/test.sh"]
ORACLE_FILES = ["solution/solve.sh", "solution/oracle_replay.py"]
BUDGET_S = 21600


def main() -> None:
    global BUDGET_S
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("family"); ap.add_argument("traj"); ap.add_argument("goal", nargs="?"); ap.add_argument("objects", nargs="?")
    ap.add_argument("--eval-index", type=int, default=0); ap.add_argument("--K", type=int, default=1)
    ap.add_argument("--tasks-root", type=pathlib.Path, default=root / "tasks")
    ap.add_argument("--build-root", type=pathlib.Path, default=root / "runs/task_build")
    ap.add_argument("--unlimited-task", type=pathlib.Path)
    ap.add_argument("--agent-wall-clock-s", type=int, default=BUDGET_S)
    a = ap.parse_args()
    fam = a.family
    slug = f"topogym-{fam.replace('_', '-')}-i{a.eval_index:02d}"
    if not 0 < a.agent_wall_clock_s <= MAX_BUDGET_S:
        ap.error(f"--agent-wall-clock-s must be in 1..{MAX_BUDGET_S}")
    BUDGET_S = a.agent_wall_clock_s
    unl = a.unlimited_task.resolve() if a.unlimited_task else a.tasks_root.resolve() / slug
    slug = unl.name
    dst = a.tasks_root.resolve() / f"{slug}-limited"
    assert unl.is_dir(), unl
    d = json.loads((a.build_root / slug / "describe.json").read_text())
    sys.path.insert(0, str(unl / "environment"))
    import rcb_topogym as M
    validate_goal_instance(fam, d, json.loads((unl/'environment/instance.json').read_text()))
    goal, requirements = goal_words(fam, M.TASKS[fam]["text"], d)
    if a.goal:
        goal += " " + a.goal  # Additional context cannot replace the actual terminal requirements.
    for sub in ("environment/sim", "tests", "solution"):
        (dst / sub).mkdir(parents=True, exist_ok=True)
    if dst != TEMPLATE:
        for f in SHARED:
            shutil.copy(TEMPLATE / f, dst / f)
        for f in dst.glob("solution/*"):
            f.unlink()
    (dst / "tests/test.sh").chmod(0o755)
    if os.environ.get("TOPOGYM_CLIENT_IMAGE"):
        for rel in ("environment/Dockerfile", "tests/Dockerfile"):
            path = dst / rel
            text = re.sub(r"^FROM .*", "FROM " + os.environ["TOPOGYM_CLIENT_IMAGE"], path.read_text(), flags=re.M)
            # The pinned client base contains these dependencies already.
            text = re.sub(r"^RUN pip install .*\n", "", text, flags=re.M)
            path.write_text(text)
    # sim sidecar gets this task's instance + the unlimited task's tooling copy
    shutil.copy(unl / "environment/instance.json", dst / "environment/sim/instance.json")
    assets = unl / "environment/instance_assets"
    if assets.is_dir():
        shutil.copytree(assets, dst / "environment/sim/instance_assets", dirs_exist_ok=True)
    import tomllib
    if tomllib.loads((unl / "task.toml").read_text())["agent"]["timeout_sec"] != BUDGET_S:
        raise ValueError("limited/unlimited wall-clock budgets must match")
    shutil.copy(unl / "environment/rcb_topogym.py", dst / "environment/sim/rcb_topogym.py")
    img = os.environ.get("TOPOGYM_TOOL_IMAGE") or re.search(r"^FROM\s+(\S+)", (unl / "tests/Dockerfile").read_text(), re.M).group(1)
    compose = (TEMPLATE / "environment/docker-compose.yaml").read_text()
    compose = re.sub(r"RCB_TASK: \S+", f"RCB_TASK: {fam}", compose)
    compose = re.sub(r"image: \S+", f"image: {img}", compose)
    compose = re.sub(r'RCB_WALL_CLOCK_S: "\d+"', f'RCB_WALL_CLOCK_S: "{BUDGET_S}"', compose)
    (dst / "environment/docker-compose.yaml").write_text(compose)
    oracle = a.traj != "-"
    if oracle:
        for f in ORACLE_FILES:
            if dst != TEMPLATE:
                shutil.copy(TEMPLATE / f, dst / f)
        acts = np.load(a.traj, allow_pickle=False)["actions"].astype(np.float32)
        np.save(dst / "solution/oracle_qpos.npy", acts[::a.K])
        (dst / "solution/oracle_meta.json").write_text(json.dumps({"K": a.K, "interpolate": "hold", "rows": int(len(acts[::a.K])),
                                                                   "source": f"{slug} solution/solve.sh (run-oracle)"}, indent=1))
        (dst / "solution/solve.sh").chmod(0o755)
    else:
        (dst / "solution/solve.sh").write_text(f"#!/bin/bash\n# No reference solution for this family yet: the oracle agent scores 0.\n"
                                               f"echo 'no reference solution for {fam}' >&2\nexit 1\n")
        (dst / "solution/solve.sh").chmod(0o755)
    inst = json.loads((unl / "environment/instance.json").read_text())
    cams = list(d["cameras"]); cam0 = cams[0]; W, H = d["cameras"][cam0]["image_size"]
    arms = d["arms"]; dim = len(d["action_layout"]); tcp0 = d["kinematics"]["tcp_frames"][0]; nq = len(d["kinematics"]["joint_names"])
    nprop = 4 * dim + 8 * len(arms)
    rs = d["robot_spec"]; base = ", ".join(f"{v:.3f}" for v in rs["base"]["pose"][:3])
    robot = rs["description"].split(" (TopoGym")[0]
    mount = {c: ("static" if d["cameras"][c]["mount"]["type"] == "static" else f"on the robot link `{d['cameras'][c]['mount']['parent_link']}`; it moves, so use the pose that comes with each frame")
             for c in cams}
    grip = {arm: d["limits"][d["action_layout"].index(f"{arm}_gripper")] for arm in arms}
    layout = ", ".join(f"`{x}`" for x in d["action_layout"])
    names = [n for n in d["objects"]]
    objects = a.objects or ("Objects here: " + ", ".join(f"`{n}`" for n in names) + "." if names else "")
    fail_words = "or when the task's own failure predicate fires (then `meta[\"reason\"]` is `task_failed`)"
    ins = f"""# TopoGym · {fam} — LIMITED MODE (robot as a service, rcb-limited/2.2)

You control a robot (**{robot}**) **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode. **Task:** {goal}

{requirements}
{details_section(fam, inst, limited=True)}
## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success (all final conditions satisfied for
  {d['stable_duration_s']:g} s), when your time is up, on a simulator error, {fail_words}. Knocked-over objects stay
  knocked over.
- **No privileged state.** You see what the cameras see (RGB, and depth when you ask for it) plus the robot's own state:
  joint positions, velocities and drive efforts, gripper openings, end-effector poses. Nothing tells you where the
  objects are (no object poses or positions). The success implementation and internal measurements are not exposed;
  the task requirements above still apply in full.
- **Your wall-clock budget is {BUDGET_S // 60} min ({BUDGET_S} s)** (`meta["time_left_s"]` counts it down); steps are unlimited. Actions and
  simulated time are reported as cost. One control step takes about {d['sec_per_step']:.1f} s of wall clock here (the simulator keeps
  a full checkpoint of every physics step).
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script
  at `/app/output/gen.py` for the record.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

{startup_instruction(fam, limited=True).rstrip()}

{limited_timing(d['sec_per_step'], d['control_hz']).rstrip()}

## Client (`/opt/tools/rcb_client.py`, protocol `rcb-limited/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects to the existing service; retries until ready (default timeout 600 s)
spec = r.spec()                               # actions, cameras (intrinsics, mounting), robot_spec, world, kinematics, budget

obs = r.get_obs()                             # current frames from {len(cams)} cameras: obs.last[cam] -> uint8 ({H},{W},3)
obs.meta["proprio"]                           # {{"layout": [{nprop} names], "now": [...]}}: groups in spec["proprio_groups"]
obs.meta["cameras"]                           # per camera: intrinsic_cv, extrinsic_cv, cam2world_gl of the LAST frame
obs = r.get_obs(depth=True)                   # + obs.last_depth[cam]: float32 ({H},{W}) z-depth in metres, 0 = no reading
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.1)   # A: (T, {dim}) rows dt seconds apart; streamed at {d['control_hz']:g} Hz with linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, {8 * len(arms)}) tool-frame targets; inverse kinematics per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["{cam0}"]                          # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["{cam0}"]                         # uint8 (N,{H},{W},3) at video_fps if requested
res.last["{cams[-1]}"]; res.proprio              # last frame per camera; float32 (N, {nprop}) proprio, one row per frame
res.frame_step, res.frame_time_s              # per frame: control steps since the episode start, simulated time (s)
res.extrinsic_cv["{cams[-1]}"]                    # (N,3,4) world -> camera at every frame
res = r.submit("joint_position", A, dt=0.1, depth="frames")   # + res.depth[cam]: (N,{H},{W}) z-depth per frame (1 mm steps)
res.group("tcp_pose"); res.group("joint_effort", now=True)   # proprio columns by group name
r.fk(q)["poses"]["{tcp0}"]                   # forward kinematics of the {nq} arm joints (spec["kinematics"]); moves nothing
r.ik({{"{tcp0}": pose}}, seed=q)             # inverse kinematics -> {{"ok", "q", "error"}}; moves nothing
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, last/, frames/, proprio.npy, depth, frame_meta.npz
```
Cameras: {"; ".join(f"`{c}` ({mount[c]})" for c in cams)}. Resolution {W}×{H}. `spec["cameras"][cam]` gives the
intrinsics and the mounting: a static pose, or the parent link and the fixed offset (world_T_cam = FK(link) · `link_T_cam_cv`).
A point (X, Y, Z) in a camera's OpenCV frame (x right, y down, z forward) appears at u = fx·X/Z + cx, v = fy·Y/Z + cy;
depth is that Z. `spec["robot_spec"]` lists the joints with their position, velocity and effort limits, the grippers,
the PD gains and the tool frames; `spec["world"]` the frame conventions.

### Action types
- `joint_position` ({dim}): {layout}; radians, gripper = opening width in metres
  ({"; ".join(f"{arm}: {g[0]:g} = closed .. {g[1]:g} = open" for arm, g in grip.items())}). Absolute targets tracked by PD controllers.
  Rows are `dt` apart (`1/{d['control_hz']:g} ≤ dt ≤ 0.5` s, a multiple of the control period); a chunk may cover at most 10 s;
  out-of-limit values are clipped and listed in `meta["clipped"]` (limits in the spec). The gripper switches at the
  row. Use `obs.meta["proprio"]["now"][:{dim}]` as the starting row to move smoothly.
- `ee_pose` ({8 * len(arms)}): per arm (in the order {arms}) `x y z qw qx qy qz gripper`; world frame (robot base at ({base}),
  +z up); quaternions wxyz. Each row is solved by inverse kinematics (no collision checking) and driven to in joint
  space; an arm whose IK fails holds and is reported in `meta["plan"]`. The pose is each gripper's **tool frame** (TCP;
  its approach and finger-closing axes are in `spec["robot_spec"]["tcp"]`), the same convention as the proprio TCP
  poses, so an observed pose is a valid target. At most 50 rows per submit.

Grasping: {d['grasp_rules']}.

{objects}
"""
    (dst / "instruction.md").write_text(ins)
    ref = ("`solution/`: streams the unlimited oracle's joint targets (one row per control step, `hold`) as `joint_position` chunks"
           if oracle else "none yet: `solution/solve.sh` says so and exits 1")
    (dst / "README.md").write_text(f"""# {slug}-limited

Limited-mode twin of `{slug}` (same frozen instance): the agent gets only the `rcb-limited/2.2` client
(docs/rcb/LIMITED_MODE_PROTOCOL.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene, records the episode as a (T, {dim}) trajectory, replays it for success, and renders the
video. The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against the
unlimited task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Goal

{goal}

{requirements}
{details_section(fam, inst, limited=True)}
| | |
|---|---|
| tier / mode | perception / limited (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `rcb-limited/2.2`: `submit` chunks of `joint_position` ({dim}, streamed at the {d['control_hz']:g} Hz control rate with the agent's `dt`) or `ee_pose` ({8 * len(arms)}, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | {ref} |
| verification | `success` = live success ∧ replay success, computed inside the sidecar (GPU physics: the state hashes are reported, not required); `/logs/verifier/replay.mp4` |
""")
    unl_toml = (unl / "task.toml").read_text()
    hours = float(re.search(r"expert_time_estimate_hours = ([0-9.]+)", unl_toml).group(1)) * 1.5
    level = tomllib.loads(unl_toml)["metadata"].get("difficulty")   # the unlimited twin's tier (docs/rcb/TAXONOMY.md)
    level = f'difficulty = "{level}"\n' if level else ""
    um = tomllib.loads(unl_toml)["metadata"]       # the unlimited twin's grasp mode and success-rule provenance
    level += "".join(f"{k} = {json.dumps(um[k])}\n" for k in ("grasp", "success_rule", "initial_state") if k in um)
    # collect: the service replays the episode once for the grading record, then once more for the video; each replay takes
    # at most as long as the agent's own episode (the budget), so wait up to that long for each.
    polls = (BUDGET_S + 601) // 2
    collect = ("for i in $(seq 1 300); do [ -f /data/server.pid ] && break; sleep 2; done; kill -USR1 $(cat /data/server.pid); "
               f"for i in $(seq 1 {polls}); do grep -q '\\\"finalized\\\": true' /data/final.json 2>/dev/null && break; sleep 2; done; "
               f"for i in $(seq 1 {polls}); do grep -q '\\\"video_done\\\": true' /data/final.json 2>/dev/null && break; sleep 2; done; cat /data/final.json")
    desc = (f"LIMITED MODE (robot as a service, rcb-limited/2.2): TopoGym {fam} on the same frozen instance as the unlimited task. "
            f"{goal} The agent only gets a client: get_obs (RGB, optional depth, proprioception, calibrated cameras), submit "
            "(joint_position or ee_pose chunks), stateless kinematics. No reset, no privileged state; the sim service records the "
            "episode as a trajectory and grades it.")
    seed = json.loads((unl / "environment/instance.json").read_text())["seed"]
    (dst / "task.toml").write_text(f"""schema_version = "1.3"
artifacts = [
  {{ source = "/data/final.json", service = "sim" }},
  {{ source = "/data/episode.jsonl", service = "sim" }},
  {{ source = "/data/trajectory.npz", service = "sim" }},
  {{ source = "/data/replay.mp4", service = "sim" }},
  {{ source = "/data/replay.last.png", service = "sim" }},
  "/app/output/",
]

[task]
name = "robot-coding-bench/{slug}-limited"
description = {json.dumps(desc)}
authors = [{{ name = "jianwen" }}]
keywords = ["robotics", "topogym", "genesis", "{rs['name']}", "limited-mode", "trajectory", "{fam}"]

[metadata]
author_name = "jianwen"
task_type = "trajectory"
simulator = "topogym"
robot = "{rs['name']}"
family = "{fam}"
tier = "perception"                # RGB + proprioception only; no object poses, no success predicate, no reset
{level}mode = "limited"
protocol = "rcb-limited/2.2"
instance_seed = {seed}
expert_time_estimate_hours = {hours:g}

[verifier]
timeout_sec = 1200.0
environment_mode = "separate"
network_mode = "no-network"

[[verifier.collect]]
service = "sim"
command = "{collect}"
timeout_sec = {600 + 2 * 2 * polls}                # service up (<= 10 min), replay (grading record), then the video: each at most one episode

[agent]
timeout_sec = {float(BUDGET_S)}             # Agent wall-clock budget
# egress: Harbor default (public). `scripts/set_agent_egress.py allowlist` closes it to the model APIs.

[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 16384
""")
    print("generated", dst.name, "oracle rows:", len(np.load(dst / "solution/oracle_qpos.npy")) if oracle else "none")


if __name__ == "__main__":
    main()
