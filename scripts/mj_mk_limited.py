#!/usr/bin/env python3
"""Generate the limited-mode twin (<task>-limited) of a MuJoCo task (dextoolbench_*, mujoco_playground_*).

    python3 scripts/mj_mk_limited.py tasks/<unlimited task> [...]     # or: --all

The twin: the agent container has only Python and the client (rcb_client.py + rcb1.py, the RoboTwin limited ones);
the simulator runs in a `sim` sidecar (rcb-mujoco image) serving images/mujoco/limited/server_mj.py with the task's
own tooling and frozen instance. The oracle replays the unlimited oracle's targets through the client; the verifier
grades the sidecar's final.json (a fresh replay of the recorded episode)."""
import json, pathlib, re, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RT = ROOT / "tasks/robotwin_2_0_stack_blocks_two-limited"
SERVER = ROOT / "images/mujoco/limited/server_mj.py"
IMAGE = "ghcr.io/jameskrw/rcb-mujoco:0.1.2"
ALLOW = 'network_mode = "allowlist"      # model APIs only (scripts/set_agent_egress.py); PROTOCOL §4\nallowed_hosts = ["chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com", "*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com"]'


def tool_of(src: pathlib.Path) -> str:
    return next(p.stem for p in (src / "environment").glob("rcb_*.py"))


def make(src: pathlib.Path) -> pathlib.Path:
    name = src.name; dst = ROOT / "tasks" / f"{name}-limited"; tool = tool_of(src); dtb = tool == "rcb_dtb"
    inst = json.load(open(src / "environment/instance.json"))
    # regenerate everything except results/ (agent results committed per run)
    if dst.exists():
        for c in dst.iterdir():
            if c.name != "results": shutil.rmtree(c) if c.is_dir() else c.unlink()
    for d in ("environment/sim", "tests", "solution"): (dst / d).mkdir(parents=True)
    # agent container: python + the client
    (dst / "environment/Dockerfile").write_text("# Limited mode: the agent container has NO simulator and no task code — only Python and the client.\n"
        "FROM docker.io/library/python:3.12-slim\nRUN pip install --no-cache-dir requests numpy pillow scipy\n"
        "COPY rcb_client.py rcb1.py /opt/tools/\nENV PYTHONPATH=/opt/tools\nRUN mkdir -p /app/output\nWORKDIR /app\n")
    for f in ("rcb_client.py", "rcb1.py"): shutil.copy(RT / "environment" / f, dst / "environment" / f)
    c = (dst / "environment/rcb_client.py").read_text()      # MuJoCo replays bit-exactly: send the targets as float64
    assert "a = np.asarray(actions, dtype=np.float32)" in c
    (dst / "environment/rcb_client.py").write_text(c.replace("a = np.asarray(actions, dtype=np.float32)", "a = np.asarray(actions, dtype=np.float64)   # float64: MuJoCo replays bit-exactly"))
    # sidecar: the server, the codec, the task's tooling and instance
    shutil.copy(SERVER, dst / "environment/sim/server_mj.py"); shutil.copy(RT / "environment/sim/rcb1.py", dst / "environment/sim/rcb1.py")
    shutil.copy(src / "environment" / f"{tool}.py", dst / "environment/sim" / f"{tool}.py"); shutil.copy(src / "environment/instance.json", dst / "environment/sim/instance.json")
    # DexToolBench: no per-goal time limit in limited mode (owner 2026-09-29: one episode, no reset, so the benchmark's 10 s
    # per goal ended every agent's episode at step 600). Only Harbor's timeouts bound it; the 360,000-step cap (100 min of
    # robot time) just keeps the finalize replay (~2.5 min) inside the collect hook's timeout.
    dtb_env = ('\n      RCB_DTB_GOAL_TIMEOUT_S: "0"\n      RCB_MAX_CONTROL_STEPS: "360000"' if tool == "rcb_dtb" else "")
    (dst / "environment/docker-compose.yaml").write_text(f"""# Limited mode: the simulator runs in the `sim` sidecar (agent cannot open it); the agent only reaches port 8000.
# No `expose`/`ports` on sim: under Harbor's egress control it shares main's network namespace (localhost:8000).
services:
  main:
    depends_on: [sim]
  sim:
    image: {IMAGE}
    volumes:
      - ./sim:/srv:ro
    working_dir: /srv
    command: python /srv/server_mj.py
    restart: on-failure:6
    environment:
      RCB_TOOL: {tool}
      RCB_INSTANCE: /srv/instance.json{dtb_env}
      PYTHONPATH: /srv
      RCB_MJ_ROOT: /opt/rcb_mj
    shm_size: "4gb"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
""")
    # verifier: grades the sidecar's final.json
    (dst / "tests/Dockerfile").write_text("# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but python.\n"
        "FROM docker.io/library/python:3.12-slim\nCOPY test.sh grade.py /tests/\nRUN chmod +x /tests/test.sh\n")
    shutil.copy(RT / "tests/test.sh", dst / "tests/test.sh")
    (dst / "tests/grade.py").write_text('''"""Limited-mode verifier for the MuJoCo tasks: reads what the sim service (which the agent could not touch) wrote.
/data/final.json holds a fresh replay's verdict of the recorded episode (deterministic = the replay ends in the live
episode's final state). DexToolBench: reward = task progress (goals reached / goals); Playground: reward = success."""
import json, os, shutil
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
def write(reward, out):
    open(f"{LOG}/reward.txt", "w").write(f"{reward:.4f}\\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)
p = "/data/final.json"
if not os.path.exists(p):
    write(0.0, {"success": 0, "missing_log": 1, "infra_error": 1, "grader_error": 0}); raise SystemExit
d = json.load(open(p))
for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):
    if os.path.exists(f"/data/{f}"): shutil.copy(f"/data/{f}", f"{LOG}/{f}")
det = bool(d.get("deterministic")); ok = bool(d.get("success")) and det
out = {"success": int(ok), "deterministic": int(det), "finalized": int(bool(d.get("finalized"))), "control_steps": int(d.get("control_steps") or 0),
       "calls": int(d.get("calls") or 0), "elapsed_s": float(d.get("elapsed_s") or 0), "video_rendered": int(bool(d.get("video"))), "grader_error": 0}
# no verdict on the agent: the service crashed (restart refused) or its verification replay failed
if d.get("infra_error") or d.get("finalize_error"):
    out.update(infra_error=1, grader_error=int(bool(d.get("finalize_error"))), reason=str(d.get("reason") or ""), finalize_error=str(d.get("finalize_error") or "")[:300])
if "progress" in d:
    out.update(progress=float(d.get("progress") or 0.0) if det else 0.0, goals_reached=int(d.get("goals_reached") or 0), n_goals=int(d.get("n_goals") or 0),
               failed_on_timeout=int(bool(d.get("failed_on_timeout"))))
    reward = out["progress"]
else:
    out.update({k: (int(v) if isinstance(v, bool) else v) for k, v in d.items() if isinstance(v, (int, float, bool)) and k not in out and k not in ("success",)})
    reward = 1.0 if ok else 0.0
write(reward, out)
''')
    # oracle: the unlimited oracle's targets, one row per control step, through the client
    shutil.copy(src / "solution/oracle_targets.npy", dst / "solution/oracle_targets.npy")
    (dst / "solution/oracle_replay.py").write_text('''"""Limited-mode oracle: submit the unlimited oracle's recorded targets (one row per control step) through the client.
No privileged information at run time; the rows were recorded offline (solution/ of the unlimited task)."""
import json, os, sys
import numpy as np
from rcb_client import Robot
r = Robot(); spec = r.spec(); dt = spec["control_dt"]; rows = max(1, int(spec["max_chunk_s"] / dt) - 1)
A = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle_targets.npy")).astype(np.float64)
cam = next(iter(spec["cameras"]))
for i in range(0, len(A), rows):
    res = r.submit("joint_position", A[i:i + rows], dt=dt, interpolate="hold", cameras=[cam], video="none", note=f"oracle chunk {i // rows}")
    print(f"chunk {i // rows}: rows={res.meta['executed_rows']} steps={res.meta['control_steps']} done={res.meta['done']} task={json.dumps(res.meta['task'])[:120]}", flush=True)
    if res.meta["done"]: break
print("status:", r.status())
''')
    (dst / "solution/solve.sh").write_text("#!/bin/bash\n# Oracle (limited mode): the unlimited oracle's recorded targets, submitted through the client.\nset -e\nmkdir -p /app/output\n"
                                          "cp /solution/oracle_replay.py /app/output/gen.py\npython /solution/oracle_replay.py\n")
    (dst / "solution/solve.sh").chmod(0o755)
    # task.toml
    u = (src / "task.toml").read_text()
    desc = re.search(r'^description = "(.*)"$', u, re.M).group(1)
    kw = re.search(r"^keywords = (\[.*\])$", u, re.M).group(1).replace("]", ', "limited-mode"]')
    meta = re.search(r"\[metadata\]\n(.*?)\n\n", u, re.S).group(1)
    meta = re.sub(r'^tier = .*$', 'tier = "perception"                # camera RGB-D + proprioception; no object poses, no reset', meta, flags=re.M)
    agent_net = ALLOW if dtb else '# egress: Harbor default (public). `scripts/set_agent_egress.py allowlist` closes it to the model APIs.'
    (dst / "task.toml").write_text(f'''schema_version = "1.3"
artifacts = [
  {{ source = "/data/final.json", service = "sim" }},
  {{ source = "/data/episode.jsonl", service = "sim" }},
  {{ source = "/data/trajectory.npz", service = "sim" }},
  {{ source = "/data/replay.mp4", service = "sim" }},
  {{ source = "/data/replay.last.png", service = "sim" }},
  {{ source = "/data/calls/", service = "sim" }},
  "/app/output/",
]

[task]
name = "robot-coding-bench/{name}-limited"
description = "LIMITED MODE (robot as a service, rcb-limited/2.1): {desc} The agent only gets a client: camera RGB-D + proprioception and joint-target chunks; no reset, no object poses; the sim service records the episode and grades a fresh replay of it."
authors = [{{ name = "kangrui" }}]
keywords = {kw}

[metadata]
{meta}
mode = "limited"
protocol = "rcb-limited/2.1"

[verifier]
timeout_sec = 1200.0
environment_mode = "separate"
network_mode = "no-network"

[[verifier.collect]]
service = "sim"
command = "for i in $(seq 1 90); do [ -f /data/server.pid ] && break; sleep 2; done; for i in $(seq 1 400); do grep -q '\\"finalized\\": true' /data/final.json 2>/dev/null && break; [ $((i % 15)) -eq 1 ] && kill -USR1 $(cat /data/server.pid) 2>/dev/null; sleep 2; done; cat /data/final.json"
timeout_sec = 900

[agent]
timeout_sec = 3600.0
{agent_net}

[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 16384

[verifier.environment]
build_timeout_sec = 600.0
''')
    (dst / "instruction.md").write_text(instruction(src, inst, tool))
    (dst / "README.md").write_text(f"# {name}-limited\n\nLimited-mode twin of `{name}` (see its README): the same scene, instance and scoring, served as a robot service "
                                   f"(`images/mujoco/limited/server_mj.py`, protocol rcb-limited/2.1, tooling `{tool}`). The agent sees camera RGB-D and proprioception only.\n\n"
                                   "| | |\n|---|---|\n| oracle | `solution/`: the unlimited oracle's recorded targets submitted through the client (one row per control step) |\n"
                                   "| grading | the sidecar replays the recorded episode in a fresh simulator; `deterministic` = same final state as the live episode |\n")
    return dst


def instruction(src, inst, tool) -> str:
    u = (src / "instruction.md").read_text()
    title = u.splitlines()[0].replace("# ", "# ", 1) + " — LIMITED MODE (robot as a service)"
    intro = u.split("\n\n")[1].strip()
    score = re.search(r"## (Scoring \(the benchmark's own rule\)|Success)\n(.*?)\n\n", u, re.S)
    score_txt = score.group(2).replace("`s.check()` computes exactly this.", "The service applies exactly this rule.").strip() if score else ""
    if tool == "rcb_dtb":
        score_txt = re.sub(r"Each goal has \*\*30 s \(1,800 control steps\)\*\*;.*?at most 360,000 control steps\.",
                           "In this mode goals have **no time limit** (the benchmark gives each goal 10 s; here you get one episode and no reset). "
                           "The episode ends when every goal is reached, when your time is up, or after **360,000 control steps (100 min of robot time)**.", score_txt, flags=re.S)
        assert "no time limit" in score_txt, "DexToolBench scoring text changed; update the limited wording"
    if tool == "rcb_dtb":
        task_obs = ('`meta["task"]` = the current goal (`goal`, x y z qx qy qz qw), `goal_index`, `n_goals`, `goals_reached`, `steps_left_on_goal`\n'
                    "(the benchmark shows the controller the current goal, as SimToolReal's deployment does). The episode **ends** when every\n"
                    "goal is reached or at the step limit (`spec[\"max_control_steps\"]`); after that the service answers 409.\n"
                    "`steps_left_on_goal` is null: no goal has a time limit here.")
        dims = "29: `joint1..joint7` (iiwa), then the 22 Sharpa hand joints (names in `spec[\"action_types\"][\"joint_position\"][\"layout\"]`)"
    else:
        task_obs = ('`meta["task"]` = the task\'s target (`target_pos`, and `target_quat_wxyz` where it has one). The episode runs until your\n'
                    "time is up; the **final state** is graded (so end in the pose you want graded, and keep it).")
        dims = f"{'14: per arm `waist, shoulder, elbow, forearm_roll, wrist_angle, wrist_rotate, gripper`' if tool == 'rcb_aloha' else '8: `actuator1..7` joint targets (rad), `actuator8` finger opening (0..0.04 m)'}"
    return f"""{title}

{intro}

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode.

## Rules (real-robot rules)
- **No reset.** Knocked-over objects stay knocked over.
- **No privileged state.** You see what the cameras see (RGB, optional depth, with each camera's calibration) plus the
  robot's own joint positions, velocities and targets. No object poses, no success predicate.
- Your wall-clock budget is 60 minutes (`meta["time_left_s"]`). There is nothing to hand in: the service records the
  episode as the trajectory and grades it. Leave your script at `/app/output/gen.py` for the record.
- Do not use pretrained manipulation policies or any published solution for this benchmark; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
{score_txt}

## Client (`/opt/tools/rcb_client.py`, protocol `rcb-limited/2.1`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # control_dt, action layout + limits, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # camera names
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> float16 metres
obs.meta["proprio"]                           # {{"layout": [...], "now": [...]}}: joint positions, velocities, current targets
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z)
obs.meta["task"]                              # see below
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold the targets and watch for 2 s (max 30)
res = r.submit("joint_position", A, dt=spec["control_dt"], cameras=cams[:1], video="mp4")   # A: (T, {dims.split(':')[0]}) rows dt apart
res.meta["done"], res.meta["reason"], res.meta["task"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```
- Actions `joint_position` ({dims}); rows are `dt` apart (a multiple of `control_dt`), each held
  (`interpolate="hold"`) or ramped from the previous row (`"linear"`, default) over its control steps; clipped to the
  limits in the spec. A chunk covers at most 10 s.
- {task_obs}
"""


if __name__ == "__main__":
    args = sys.argv[1:]
    srcs = [p for p in sorted((ROOT / "tasks").glob("*")) if (p.name.startswith("dextoolbench_") or p.name.startswith("mujoco_playground_")) and not p.name.endswith("-limited")] if args == ["--all"] else [pathlib.Path(a) for a in args]
    for s in srcs: print(make(s).name)
