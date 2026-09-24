#!/usr/bin/env python3
"""Generate tasks/robotwin_2_0_<task>-limited/ from an existing unlimited task + the stack_blocks_two-limited template.
usage: scripts/robotwin_mk_limited.py <task> <oracle_traj.npz>
The limited oracle replays the unlimited oracle's joint targets (every 25 physics steps) as `qpos` actions."""
import pathlib, re, shutil, sys, json
import numpy as np
root = pathlib.Path(__file__).resolve().parents[1]
task, traj = sys.argv[1], sys.argv[2]
src = root / "tasks/robotwin_2_0_stack_blocks_two-limited"; unl = root / f"tasks/robotwin_2_0_{task}"; dst = root / f"tasks/robotwin_2_0_{task}-limited"
assert unl.is_dir(), unl
if dst.exists(): shutil.rmtree(dst)
shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
# sim sidecar gets this task's instance + the unlimited task's tooling copy
shutil.copy(unl / "environment/instance.json", dst / "environment/sim/instance.json")
shutil.copy(unl / "environment/rcb_traj.py", dst / "environment/sim/rcb_traj.py")
inst = json.load(open(unl / "environment/instance.json")); goal = inst.get("text", task); seed = inst["seed"]
def sub(path, pairs):
    p = dst / path; s = p.read_text()
    for a, b in pairs: s = s.replace(a, b)
    p.write_text(s)
sub("environment/docker-compose.yaml", [("RCB_TASK: stack_blocks_two", f"RCB_TASK: {task}")])
tt = (dst / "task.toml").read_text()
tt = tt.replace('name = "robot-coding-bench/robotwin_2_0_stack_blocks_two-limited"', f'name = "robot-coding-bench/robotwin_2_0_{task}-limited"')
tt = re.sub(r'description = ".*"', f'description = "LIMITED MODE (robot as a service, rcb-limited/1.0): RoboTwin 2.0 {task} on the same frozen instance as the unlimited task (seed {seed}). {goal} The agent only gets a client: observe (RGB + proprioception), step (qpos or ee action). No reset, no privileged state; the sim service records the episode as a trajectory and grades it."', tt)
tt = tt.replace('"stack_blocks_two"]', f'"{task}"]').replace('family = "stack_blocks_two"', f'family = "{task}"').replace("instance_seed = 60417", f"instance_seed = {seed}")
(dst / "task.toml").write_text(tt)
# instruction: swap the task-specific paragraph
ins = (dst / "instruction.md").read_text()
ins = ins.replace("# RoboTwin 2.0 · stack_blocks_two — LIMITED MODE (robot as a service)", f"# RoboTwin 2.0 · {task} — LIMITED MODE (robot as a service)")
ins = re.sub(r"\*\*Task:\*\* .*?\n\n", f"**Task:** {goal}\n\n", ins, count=1, flags=re.S)
ins = ins.replace('r.step("qpos", a14)', 'r.step("qpos", a14)')
ins = re.sub(r"Table top is at z ≈ 0\.74 m,\nblocks are 5 cm cubes\.", "Table top is at z ≈ 0.74 m.", ins)
(dst / "instruction.md").write_text(ins)
rd = (dst / "README.md").read_text().replace("robotwin_2_0_stack_blocks_two-limited", f"robotwin_2_0_{task}-limited").replace("`robotwin_2_0_stack_blocks_two`", f"`robotwin_2_0_{task}`").replace("RoboTwin seed 60417", f"RoboTwin seed {seed}")
(dst / "README.md").write_text(rd)
# oracle: subsample the unlimited oracle trajectory (T,34) -> (N,14) qpos actions
A = np.load(traj)["actions"]; K = 25; idx = list(range(K - 1, len(A), K))
if not idx or idx[-1] != len(A) - 1: idx.append(len(A) - 1)
Q = np.stack([np.concatenate([A[i, 0:6], [A[i, 32]], A[i, 8:14], [A[i, 33]]]) for i in idx])
np.save(dst / "solution/oracle_qpos.npy", Q)
print(f"generated {dst.name}: seed {seed}, oracle {Q.shape[0]} qpos actions from {len(A)} physics steps")
