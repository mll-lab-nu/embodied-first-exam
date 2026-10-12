"""Generate tasks/robotwin_2_0_<task>-privileged/ from the stack_blocks_two template (RoboTwin 2.0 tasks only).
usage: scripts/robotwin_mk_task.py <task> <seed> "<goal text>" "<difficulty paragraph>"
Then, in the GPU container (docker run --gpus all -v $PWD/tasks:/tasks ghcr.io/mll-lab-nu/eai-robotwin:0.1.1):
  make-instance --task <task> --seed <seed> --out /tasks/robotwin_2_0_<task>-privileged/environment/instance.json (copy to tests/),
  run-oracle + replay, then harbor run -a oracle / -a nop, then cd tasks && harbor add --scan .
Pick the seed with scripts/robotwin_expert_sweep.py (expert must pass on it; avoid the public dataset seeds).
The oracle is RoboTwin's upstream expert (every task-class method except setup_demo/load_actors/check_success),
copied verbatim from third_party/RoboTwin/envs/<task>.py and bound onto `env` at run time."""
import ast, json, pathlib, re, shutil, sys, textwrap
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); from task_conventions import normalize  # noqa: E402
root = pathlib.Path(__file__).resolve().parents[1]
task, seed, goal, difficulty = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
src_dir = root / "tasks/robotwin_2_0_stack_blocks_two-privileged"; dst = root / f"tasks/robotwin_2_0_{task}-privileged"
up = (root / f"third_party/RoboTwin/envs/{task}.py").read_text(); tree = ast.parse(up)
cls = [n for n in tree.body if isinstance(n, ast.ClassDef)][0]
keep = {"setup_demo", "load_actors", "check_success"}
expert = [f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name not in keep]
la = ast.get_source_segment(up, [f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name == "load_actors"][0])
cs = ast.get_source_segment(up, [f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name == "check_success"][0])
attrs = sorted(set(re.findall(r"self\.(\w+)\s*=\s*(?:create_|rand_create|self\.get_cluttered|\[)", la)) | set(re.findall(r"self\.(\w+)\s*=", la)) - {"prohibited_area", "size_dict"})
step_lim = __import__("yaml").safe_load(open(root / "third_party/RoboTwin/env_cfg/task_config/_eval_step_limit.yml")).get(task, "?")

# regenerate everything; results/ does not belong in the repository (PROTOCOL D3) and normalize() removes it
if dst.exists():
    for c in dst.iterdir():
        if c.name != "results": shutil.rmtree(c) if c.is_dir() else c.unlink()
shutil.copytree(src_dir, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "results", "instance.json"))
(dst / "solution/oracle_stack_blocks_two.py").unlink()

def sub(path, pairs):
    p = dst / path; s = p.read_text()
    for a, b in pairs:
        assert a in s, (path, a); s = s.replace(a, b)
    p.write_text(s)

# oracle: verbatim upstream methods, dedented to module level, bound to env
fn_src = "\n\n".join(textwrap.dedent(ast.get_source_segment(up, f)) for f in expert)
names = [f.name for f in expert]
oracle = f'''# Reference solution for robotwin_2_0_{task}: RoboTwin 2.0's expert methods from envs/{task}.py upstream
# ({", ".join(names)}), copied verbatim and bound onto the task env. These methods are scrubbed from the agent image.
# Runs with `env` (RoboTwin task env) in scope (rcb_traj.Session.exec_code).
import types
import numpy as np
import sapien
from envs.utils import *
from envs._GLOBAL_CONFIGS import *


{fn_src}


for _f in ({", ".join(names)},):
    setattr(env, _f.__name__, types.MethodType(_f, env))
env.play_once()
assert env.plan_success, "a planning step failed"
'''
(dst / f"solution/oracle_{task}.py").write_text(oracle)
sub("solution/solve.sh", [("stack_blocks_two", task)])  # also renames oracle_stack_blocks_two.py
sub("tests/test.sh", [("--family stack_blocks_two", f"--family {task}")])
for f in ("environment/rcb_traj.py", "tests/rcb_traj.py"):
    sub(f, [('    "stack_blocks_two": dict(\n        text="Stack the green block on top of the red block (either arm may be used), then open both grippers.",\n    ),\n',
             f'    "stack_blocks_two": dict(\n        text="Stack the green block on top of the red block (either arm may be used), then open both grippers.",\n    ),\n    {task!r}: dict(text={goal!r}),\n')])
    sub(f, [('q = sub.add_parser("selftest"); q.add_argument("--task", default="stack_blocks_two")', f'q = sub.add_parser("selftest"); q.add_argument("--task", default={task!r})')])
sub("task.toml", [
    ('name = "robot-coding-bench/robotwin_2_0_stack_blocks_two-privileged"', f'name = "robot-coding-bench/robotwin_2_0_{task}-privileged"'),
    ('description = "RoboTwin 2.0 stack_blocks_two (ALOHA-AgileX dual arm, SAPIEN): produce one replayable trajectory that stacks the green block on the red block, frozen scene instance (RoboTwin seed 60417)."',
     f'description = "RoboTwin 2.0 {task} (ALOHA-AgileX dual arm, SAPIEN): produce one replayable trajectory. {goal} Frozen scene instance (RoboTwin seed {seed})."'),
    ('"trajectory", "stack_blocks_two"]', f'"trajectory", "{task}"]'),
    ('family = "stack_blocks_two"', f'family = "{task}"'),
    ("instance_seed = 60417", f"instance_seed = {seed}"),
])
# the agent's egress is the template's: the one allowlist of scripts/set_agent_egress.py (model APIs and package registries)
assert '\nnetwork_mode = "allowlist"' in (dst / "task.toml").read_text(), "template task.toml: [agent] is not on the egress allowlist"
instr = f'''# RoboTwin 2.0 · {task} — frozen instance

You control a simulated dual-arm **ALOHA-AgileX** robot (RoboTwin 2.0 on SAPIEN 3 / PhysX, CuRobo motion
planning) via Python. **Task:** {goal}

The scene objects are attributes of the task env (`env.{'`, `env.'.join(attrs)}`; see `load_actors` in
`/opt/RoboTwin/envs/{task}.py`). RoboTwin's success predicate is `check_success` in that file:
```python
{cs}
```

This is a *fixed scene instance*: object poses never change between resets. You may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed at the end of the replay, else 0. Also leave the script that produced it at `/app/output/gen.py`.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_traj import Session
s = Session("{task}", instance="/app/instance.json")   # rebuilds the scene, loads the CuRobo planner (~1 min first time)
s.reset()                          # back to the frozen initial state (unlimited; each reset rebuilds the scene, a few seconds)
env = s.env                        # the RoboTwin task env (envs/{task}.py + envs/_base_task.py under /opt/RoboTwin)
env.robot                          # Robot: get_left_tcp_pose(), get_left_arm_jointState(), left_plan_path(pose), ...
s.record_start(); ...; actions = s.record_stop()   # actions: (T, 34) rows, one per physics step (1/250 s); at most 200,000 rows are graded
s.status()                         # {{'success': bool, 'sim_steps': int, 'resets': int, 'state_sha': str}}
s.replay(actions)                  # resets, replays open-loop, returns status  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
RoboTwin's planning primitives on `env` (see `envs/_base_task.py`; read the docstrings):
`env.move(actions1, actions2=None)` executes action lists built by `env.grasp_actor(actor, arm_tag, pre_grasp_dis, grasp_dis, contact_point_id, ...)`,
`env.place_actor(actor, arm_tag, target_pose, functional_point_id, pre_dis, dis, is_open, constrain, ...)`,
`env.move_by_displacement(arm_tag, x, y, z, quat, move_axis)`, `env.move_to_pose(arm_tag, target_pose)`,
`env.open_gripper(arm_tag)`, `env.close_gripper(arm_tag)`, `env.back_to_origin(arm_tag)`; `ArmTag("left"|"right")`,
`Action`, and `GRASP_DIRECTION_DIC` from `envs.utils` / `envs._GLOBAL_CONFIGS`. Objects are RoboTwin `Actor`s
(`.get_pose()`, `.get_functional_point(i)`, `.get_contact_point(i)`; articulated ones also `.get_qpos()`).
Every physics step these primitives take is recorded while recording is on; `env.plan_success`
turns False when a plan fails (later moves are skipped). Low-level control: `s.step(row)` with a row in the
recorded layout (`s.action_layout`: 16 joint drive position targets, 16 velocity targets, left/right gripper
command 0 = closed / 1 = open).
Gripper state: the success predicate's gripper clauses (RoboTwin's `is_*_gripper_open()` / `is_*_gripper_close()`) are
evaluated on the **finger joints' drive targets**, not on the two gripper-command columns of a row:
`s.gripper_opening("left")` returns the (least open, most open) finger in command units, and a gripper is open when
its least open finger is above 0.8, closed when its most open finger is below 0.2. A hand-written row therefore opens
a gripper only through its finger position targets (the 7th–8th and 15th–16th of the 16); `env.open_gripper`,
`env.close_gripper` and the other primitives set fingers and command together.

CLI equivalent of the grader:
`python /opt/tools/rcb_traj.py replay --task {task} --instance /app/instance.json --traj /app/output/trajectory.npz`

Coordinates are in the world frame (table centre at the origin, +z up, the robot at y = -0.65 facing +y);
quaternions are WXYZ. Rendering (optional, slow): `Session(..., enable_render=True)` then `s.render_frame("head_camera")`.
'''
(dst / "instruction.md").write_text(instr)
readme = f'''# robotwin_2_0_{task}-privileged

| | |
|---|---|
| Simulator / robot | RoboTwin 2.0 (SAPIEN 3 / PhysX + CuRobo) / aloha-agilex (dual arm) |
| Family / instance | `{task}` / RoboTwin seed {seed} (deliberately not one of the seeds used by the public RoboTwin dataset) |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/mll-lab-nu/eai-robotwin:0.1.1` (needs an NVIDIA GPU: `environment/docker-compose.yaml`) |
| RoboTwin eval step limit | {step_lim} (policy-eval budget upstream; indicative of task length) |

## Goal
{goal}

## Difficulty
{difficulty}

## Reference solution
RoboTwin 2.0's expert methods for `{task}` ({", ".join(names)}; scrubbed from the image), copied verbatim into
`solution/oracle_{task}.py` and bound onto the env; `solution/solve.sh` records it into a trajectory.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice;
pass iff RoboTwin's `check_success` holds after every replay and the final-state hashes agree (`tests/grade.py`),
plus `/logs/verifier/replay.mp4`. The trajectory is the per-physics-step drive-target record (T, 34) captured by
hooking `scene.step()`; the instance is rebuilt from the RoboTwin seed and checked against the stored
initial-state hash on every reset.
'''
(dst / "README.md").write_text(readme)
normalize(dst)   # protocol v1.0 conventions (scripts/task_conventions.py)
print("generated", dst, "expert methods:", names, "actors:", attrs)
