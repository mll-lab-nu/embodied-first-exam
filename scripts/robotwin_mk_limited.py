#!/usr/bin/env python3
"""Generate tasks/robotwin_2_0_<task>-standard/ from an existing privileged task + the stack_blocks_two-standard template.
usage: scripts/robotwin_mk_limited.py <task> <oracle_traj.npz> [K=25] [--vel]   (needs numpy: run inside the rcb-robotwin image, e.g.
       docker run --rm -v $PWD:/repo -v <traj dir>:/out ghcr.io/mll-lab-nu/eai-robotwin:0.1.2 python /repo/scripts/robotwin_mk_limited.py <task> /out/oracle_<task>.npz)
The standard-mode oracle replays the privileged oracle's joint targets (every K physics steps, default 25) as `qpos` actions.
The rcb-robotwin image has Python 3.10 (no tomllib): there the v1.0 conventions are skipped with a note; run
`python3 scripts/task_conventions.py tasks/robotwin_2_0_<task>-standard tasks/robotwin_2_0_<task>-privileged` on the host."""
import pathlib, re, shutil, sys, json
import numpy as np
root = pathlib.Path(__file__).resolve().parents[1]
task, traj = sys.argv[1], sys.argv[2]
K = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] != "--vel" else 25   # physics steps per qpos action; finer for timing-sensitive tasks
VEL = "--vel" in sys.argv   # also ship the expert's velocity feed-forward (K=1 + --vel = exact replay; needed by e.g. scan_object)
src = root / "tasks/robotwin_2_0_stack_blocks_two-standard"; unl = root / f"tasks/robotwin_2_0_{task}-privileged"; dst = root / f"tasks/robotwin_2_0_{task}-standard"
assert unl.is_dir(), unl
# regenerate everything; results/ does not belong in the repository (PROTOCOL D3) and normalize() removes it
if dst.exists():
    for c in dst.iterdir():
        if c.name != "results": shutil.rmtree(c) if c.is_dir() else c.unlink()
shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "results"))
# sim sidecar gets this task's instance + the unlimited task's tooling copy
shutil.copy(unl / "environment/instance.json", dst / "environment/sim/instance.json")
shutil.copy(unl / "environment/rcb_traj.py", dst / "environment/sim/rcb_traj.py")
inst = json.load(open(unl / "environment/instance.json")); goal = inst.get("text", task); seed = inst["seed"]
def sub(path, pairs):
    p = dst / path; s = p.read_text()
    for a, b in pairs:
        assert a in s, (path, a[:60]); s = s.replace(a, b)   # a silent no-op here means the template drifted
    p.write_text(s)
sub("environment/docker-compose.yaml", [("RCB_TASK: stack_blocks_two", f"RCB_TASK: {task}")])
tt = (dst / "task.toml").read_text()
tt = tt.replace('name = "robot-coding-bench/robotwin_2_0_stack_blocks_two-standard"', f'name = "robot-coding-bench/robotwin_2_0_{task}-standard"')
tt = re.sub(r'description = ".*"', f'description = "STANDARD MODE (robot as a service, eai-standard/2.1): RoboTwin 2.0 {task} on the same frozen instance as the privileged task (seed {seed}). {goal} The agent only gets a client: /observe (RGB-D video, camera calibration, proprioception) and /submit (joint_position or ee_pose action chunks). No reset, no privileged state; the sim service records the episode as a trajectory and grades it."', tt)
tt = tt.replace('"stack_blocks_two"]', f'"{task}"]').replace('family = "stack_blocks_two"', f'family = "{task}"').replace("instance_seed = 60417", f"instance_seed = {seed}")
assert '\nnetwork_mode = "allowlist"' in tt, "template task.toml: [agent] is not on the egress allowlist"   # the template's: the one allowlist (model APIs and package registries; scripts/set_agent_egress.py)
(dst / "task.toml").write_text(tt)
# instruction: swap the task-specific paragraph
ins = (dst / "instruction.md").read_text()
ins, n_title = re.subn(r"^# RoboTwin 2\.0 · stack_blocks_two — (LIMITED|STANDARD) MODE", f"# RoboTwin 2.0 · {task} — STANDARD MODE", ins, count=1, flags=re.M)
assert n_title == 1, "template title drifted: update the title substitution"
# the goal text, then the facts of the judge for this task (scripts/robotwin/standard_facts.json; robotwin_sync_shared.py checks it)
facts = json.load(open(root / "scripts/robotwin/standard_facts.json")).get(task, {}).get("facts", "")
ins = re.sub(r"\*\*Task:\*\* .*?\n\n", lambda m: f"**Task:** {goal}{' ' + facts if facts else ''}\n\n", ins, count=1, flags=re.S)
ins = ins.replace("Objects here: two 5 cm cubes (red, green). Table top at z ≈ 0.74 m.", "Table top at z ≈ 0.74 m. The scene's objects are what the cameras show.")
(dst / "instruction.md").write_text(ins)
rd = (dst / "README.md").read_text().replace("robotwin_2_0_stack_blocks_two-standard", f"robotwin_2_0_{task}-standard").replace("`robotwin_2_0_stack_blocks_two-privileged`", f"`robotwin_2_0_{task}-privileged`").replace("RoboTwin seed 60417", f"RoboTwin seed {seed}")
(dst / "README.md").write_text(rd)
# oracle: subsample the unlimited oracle trajectory (T,34) -> (N,14) qpos actions
A = np.load(traj)["actions"]; idx = list(range(K - 1, len(A), K))
if not idx or idx[-1] != len(A) - 1: idx.append(len(A) - 1)
Q = np.stack([np.concatenate([A[i, 0:6], [A[i, 32]], A[i, 8:14], [A[i, 33]]] + ([A[i, 16:22], [0.0], A[i, 24:30], [0.0]] if VEL else [])) for i in idx])
np.save(dst / "solution/oracle_qpos.npy", Q); json.dump({"K": K, "velocity_ff": VEL}, open(dst / "solution/oracle_meta.json", "w"))
print(f"generated {dst.name}: seed {seed}, oracle {Q.shape[0]} qpos actions from {len(A)} physics steps")
try:   # protocol v1.0 conventions (scripts/task_conventions.py); needs Python >= 3.11
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); from task_conventions import normalize
    normalize(dst); normalize(unl)   # the privileged twin's README gets its Twin row
except ImportError as exc:
    print(f"note: conventions not applied ({exc}); run scripts/task_conventions.py on {dst.name} and {unl.name} with Python >= 3.11")
