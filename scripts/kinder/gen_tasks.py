#!/usr/bin/env python3
"""gen_tasks.py -- every tasks/kinder-* directory, rendered from subset.toml, facts.json, templates/ and shared/.

  ./gen_tasks.py render  [family ...]   rewrite the task dirs, full mode and its limited twin (no simulator needed)
  ./gen_tasks.py measure [family ...]   pin, check and time each instance -> facts.json (in the image, with a GPU)
  ./gen_tasks.py verify  [family ...]   measure again; fail on drift, a passing nop, or a non-deterministic replay
  Both also write the cameras' t=0 images, --images DIR/<family>/t0_<camera>.png (for build.py --cameras); verify
  leaves facts.json as it is.

What a task says in words comes from subset.toml; every number it states (the scene's digest, the action space, the
costs) comes from facts.json, which only `measure` writes. The simulator-backed commands run in the image:

  sg docker -c "docker run --rm --gpus all -e NVIDIA_DRIVER_CAPABILITIES=compute,graphics,utility -v \\$PWD:/repo \\
    -w /repo --user $(id -u):$(id -g) -e HOME=/tmp ghcr.io/jameskrw/rcb-kinder:$(cat images/VERSION) \\
    python scripts/kinder/gen_tasks.py measure"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TASKS_DIR = ROOT / "tasks"
SHARED, TEMPLATES, FACTS = HERE / "shared", HERE / "templates", HERE / "facts.json"
COMMON = ROOT / "scripts" / "limited"          # the simulator-agnostic half of limited mode: the service, the verifier
# What a task says about its robot and simulator, by kind (below): the README's category, the instruction's robot,
# task.toml's keywords.
KINDS = {
    "tidybot": ("Dynamic3D, TidyBot++", "a simulated TidyBot++ mobile manipulator (KinDER / MuJoCo) via Python: a holonomic "
                "base, a Kinova Gen3\n7-DoF arm and a Robotiq 2F-85 gripper", "mujoco", "tidybot", "mobile-manipulation"),
    "kinematic3d": ("Kinematic3D, PyBullet", "a simulated mobile manipulator (KinDER / PyBullet, kinematic: no dynamics) "
                    "via Python: a mobile base and a Kinova Gen3 7-DoF arm with a gripper", "pybullet", "kinova",
                    "mobile-manipulation"),
}


def load() -> tuple[dict, dict[str, dict]]:
    d = tomllib.loads((HERE / "subset.toml").read_text())
    return d["defaults"], {t["family"]: t for t in d["task"]}


def load_facts() -> dict:
    return json.loads(FACTS.read_text()) if FACTS.exists() else {}


def select(names: list[str], tasks: dict) -> list[dict]:
    if unknown := sorted(set(names) - set(tasks)):
        raise SystemExit(f"unknown families {unknown}; subset.toml has {sorted(tasks)}")
    return [tasks[n] for n in (names or tasks)]


def one_line(s: str) -> str:
    return " ".join(s.split())


def fill(template: str, ctx: dict) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(ctx[m.group(1)]), template)   # an unknown placeholder: KeyError


# What a limited twin says about its robot's sensors, by kind: the instruction's robot, sensors, cost and proprio
# lines, the README's and task.toml's sensor lists.
_ODOM = "the base's odometry (where it is relative to where it started)"
_BOTH = {"images_what": "both robot cameras' images (and the wrist's depth)",
         "sensors_short": "two\ncameras, joint encoders, the base's odometry",
         "sensors_plus": "camera RGB + joint encoders + base odometry"}
LIMITED = {
    "tidybot": {"limited_robot": "a simulated TidyBot++ mobile manipulator (KinDER / MuJoCo) -- a holonomic base, a Kinova "
                                 "Gen3 7-DoF arm\nand a Robotiq 2F-85 gripper",
                "sensors": "its two cameras (RGB, {hw}:\n  `robot_base` on the base, `robot_wrist` on the arm's last link), "
                           "its joint encoders (the arm's angles and\n  velocities, the gripper) and " + _ODOM,
                "proprio_text": "`obs[\"proprio\"]` has `base_pose` ([x, y, yaw] in the odometry frame: where the base "
                                "started, x the way it faced, y\nleft), `base_vel`, `arm_pos`, `arm_vel`, `gripper_pos` "
                                "(the fingers' position: 0 open, 1 at their closed limit) and\n`gripper_vel`; "
                                "`spec()[\"proprio\"]` gives the units.", **_BOTH},
    "kinematic3d": {"limited_robot": "a simulated mobile manipulator (KinDER / PyBullet, kinematic) -- a TidyBot++ base, a "
                                     "Kinova Gen3\n7-DoF arm and a Robotiq 2F-85 gripper",
                    "sensors": "its two cameras (RGB, {hw}:\n  `robot_base` on the base, `robot_wrist` on the arm's last "
                               "link), its joint encoders (the arm's angles, the\n  gripper) and " + _ODOM,
                    "proprio_text": "`obs[\"proprio\"]` has `base_pose` ([x, y, yaw] in the odometry frame: where the "
                                    "base started, x the way it faced, y\nleft), `arm_pos` and `gripper_pos` (the fingers' "
                                    "position: 0 open, 1 at their closed limit); the robot is\nkinematic, so it reports no "
                                    "velocities. `spec()[\"proprio\"]` gives the units.", **_BOTH},
}


def kind(entry_point: str) -> str:
    """KinDER's category, from the environment's registered entry point: tidybot (MuJoCo) or kinematic3d (PyBullet),
    the two robots with a limited-mode adapter."""
    tidybot = entry_point.startswith("kinder.envs.dynamic3d.") and not entry_point.endswith(":Franka3DEnv")
    k = "tidybot" if tidybot else entry_point.split(".")[2]
    if k not in KINDS:
        raise SystemExit(f"{entry_point}: not a robot these tasks support ({', '.join(KINDS)})")
    return k


# The limited sidecar's GPU (docker-compose.yaml), for the MuJoCo tasks' images.
SIM_GPU = """      NVIDIA_DRIVER_CAPABILITIES: compute,graphics,utility
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]"""


def max_steps(t: dict, d: dict) -> int:
    return t.get("max_steps", d["max_steps"])


def instance(t: dict, d: dict, sha: str | None) -> dict:
    return {"env_id": t["env_id"], "seed": d["seed"], "max_steps": max_steps(t, d),
            **({"task_view": t["task_view"]} if "task_view" in t else {}), **({"scene_sha": sha} if sha else {})}


# --------------------------------------------------------------------------- render
def action_layout(f: dict, limited: bool) -> str:
    """The action vector, value by value, as the agent addresses it in this mode."""
    dim, vel, k = f["action_dim"], f["action_dim"] == 18, kind(f["entry_point"])
    if limited:                                 # both robots' base, in the odometry frame
        mag = f"{f['action_high'][0]:g}"
        rows = [f'Each action (`r.step("delta", a)`) is {dim} numbers, one '
                f'{"10 Hz control step" if k == "tidybot" else "control step"}, in the order of `spec()["delta"]["layout"]`:',
                f"- `base_x`, `base_y`: how far to move the base, metres in the odometry frame, together at most {mag} a "
                f"step; `base_yaw`: how far to turn it, radians (+ = counter-clockwise), at most {mag}."]
        if k == "kinematic3d":
            return "\n".join(rows + [
                f"- `arm_1` ... `arm_7`: radians to add to each of the 7 arm joints' angles, each at most {mag} a step; "
                "the arm moves there at once.",
                "- `gripper`: below -0.5 closes the gripper, above 0.5 opens it, in between leaves it as it is; when "
                "that takes hold or lets go: `spec()[\"delta\"][\"units\"]`."])
    elif k != "tidybot":                        # full mode: upstream's own table, and the bounds
        bound = lambda v: "unbounded" if v is None else f"{v:g}"  # noqa: E731
        return "\n".join([f"Each action is {dim} numbers, one control step, in KinDER's own order (`s.action_space`). "
                          "KinDER documents them:", "", f["action_doc"].strip(), "",
                          "Bounds, value by value: " + ", ".join(f"`[{i}]` {bound(lo)} to {bound(hi)}" for i, (lo, hi)
                                                               in enumerate(zip(f["action_low"], f["action_high"]))) + "."])
    else:
        rows = [f"Each action is {dim} numbers, one 10 Hz control step, in KinDER's own order (`s.action_space`):",
                "- `[0:3]` base: how far to move the base in x and y (metres) and turn it (radians, + = counter-"
                "clockwise), in the world frame, each at most 0.1 a step; the base's position controller tracks the "
                "new pose."]
    arm = "`arm_1` ... `arm_7`" if limited else "`[3:10]` arm"
    grip = "`gripper`" if limited else "`[10]` gripper"
    rows += [f"- {arm}: radians to add to each of the 7 arm joints' measured angles, each at most 0.1 a step; the sums "
             "are the joints' new targets, which the arm's PD controller tracks.",
             f"- {grip}: 0 = open, 1 = closed (a command, not a change)."]
    if vel:
        rows.append(f"- {'`arm_1_vel` ... `arm_7_vel`' if limited else '`[11:18]` arm'}: joint velocity targets, rad/s, "
                    "unbounded, which the PD controller tracks along with the position targets.")
    return "\n".join(rows)


def goal_text(stmt: str) -> str:
    """The goal alone, for the sidecar's /spec."""
    first = stmt.split(". ")[0].rstrip(".")
    return first[0].upper() + first[1:] + "."


def context(t: dict, d: dict, f: dict) -> dict:
    """The full-mode task's placeholders; limited_context() adds its twin's."""
    stmt = one_line(t["task_statement"])
    full = f"kinder-{t['family']}-{d['instance_tag']}"
    lim = f["limited"]
    ms = lim["step_ms"]
    k, n = kind(f["entry_point"]), max_steps(t, d)
    category, robot, *keywords = KINDS[k]
    mujoco = k == "tidybot"
    return {
        "family": t["family"], "env_id": t["env_id"], "env_name": t["env_id"].split("/")[1].removesuffix("-v0"),
        "instance_tag": d["instance_tag"], "seed": d["seed"], "max_steps": n,
        "category": category, "robot": robot, "robot_id": "tidybot-plus-plus",   # both kinds' robot
        "keywords": ", ".join(f'"{w}"' for w in keywords), "view": "task_view" if mujoco else "render",
        "step_time": f" ({n / 10:g} s at 10 Hz)" if mujoco else "", "step_name": "10 Hz control step" if mujoco else "control step",
        "set_state_note": ("`s.env.unwrapped.set_state()` restores KinDER's\nobject-centric state, not everything the physics "
                           "carries, so a rollout continued from it can drift from the same actions\nreplayed from the start: "
                           "check the final trajectory with `s.replay`." if mujoco else
                           "`s.env.unwrapped.set_state()` restores KinDER's\nobject-centric state only approximately, so a "
                           "rollout continued from it can drift from the same actions replayed from\nthe start: check the "
                           "final trajectory with `s.replay`."),
        "twin": f"{full}-limited", "sim_gpu": SIM_GPU if mujoco else "",
        "robot_seconds": f"{n / 10:g}", "task_statement": stmt,
        "task_dir": full, "twin_dir": full, "image_tag": (ROOT / "images" / "VERSION").read_text().strip(),
        "allowed_hosts": ", ".join(f'"{h}"' for h in d["agent_allowed_hosts"]),
        "obs_dim": f["obs_dim"], "action_dim": f["action_dim"],
        "episode_seconds": f"{f['episode_seconds']:.0f}" if f["episode_seconds"] >= 0.5 else f"{f['episode_seconds']:.1g}",
        "action_layout": action_layout(f, limited=False),
        "limited_action_layout": action_layout(f, limited=True),
        "expert_hours": t["expert_hours"], "limited_expert_hours": 2 * t["expert_hours"],
        "agent_timeout": float(d["agent_timeout_sec"]), "agent_timeout_hours": f"{d['agent_timeout_sec'] / 3600:g}",
        "verifier_timeout": float(d["verifier_timeout_sec"]), "image_hw": "×".join(map(str, lim["image_hw"])),
        "ms_single": f"{ms['single']:.1f}", "ms_images": f"{ms['images']:.1f}", "ms_batch": f"{ms['batch']:.1f}",
    }


def limited_context(t: dict, f: dict, ctx: dict, task_dir: str) -> dict:
    """The limited twin's placeholders: its robot's sensors, and its own goal sentence where the full one names the
    goal by world coordinates or state names (subset.toml `limited_statement`)."""
    stmt = one_line(t.get("limited_statement", t["task_statement"]))
    text = {k: v.format(hw=ctx["image_hw"]) for k, v in LIMITED[kind(f["entry_point"])].items()}
    return ctx | text | {"task_dir": task_dir, "task_statement": stmt,
                         "task_text_yaml": json.dumps(goal_text(stmt), ensure_ascii=False),   # a YAML string, quotes and all
                         "robot_time": f" ({ctx['robot_seconds']} s of robot time)" if ctx["view"] == "task_view" else ""}


def write(path: Path, text: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip("\n") + "\n")
    if executable:
        path.chmod(0o755)


def render(t: dict, d: dict, f: dict) -> list[Path]:
    """Both modes of one task, from scratch: whatever is not rendered here does not belong in the task."""
    ctx = context(t, d, f)
    inst = json.dumps(instance(t, d, f["scene_sha"]), indent=1) + "\n"
    full = TASKS_DIR / ctx["task_dir"]
    lim = full.with_name(full.name + "-limited")
    for out in (full, lim):
        shutil.rmtree(out, ignore_errors=True)

    gpu = [("gpu.docker-compose.yaml", "environment/gpu.docker-compose.yaml")] if ctx["view"] == "task_view" else []
    for name, rel in [("instruction.md", "instruction.md"), ("README.md", "README.md"), ("task.toml", "task.toml"),
                      ("Dockerfile", "environment/Dockerfile"), *gpu,   # the GPU speeds up MuJoCo's images only
                      ("test.sh", "tests/test.sh"), ("solve.sh", "solution/solve.sh")]:
        write(full / rel, fill((TEMPLATES / name).read_text(), ctx), executable=rel.endswith(".sh"))
    for rel in ("environment", "tests"):
        write(full / rel / "instance.json", inst)
        shutil.copyfile(SHARED / "rcb_kinder.py", full / rel / "rcb_kinder.py")
    shutil.copyfile(SHARED / "grade.py", full / "tests" / "grade.py")
    ctx["tests_files"] = " ".join(sorted(p.name for p in (full / "tests").iterdir()))
    write(full / "tests" / "Dockerfile", fill((TEMPLATES / "tests.Dockerfile").read_text(), ctx))

    _check_instruction(full, ctx, t, d)
    ctx_lim = limited_context(t, f, ctx, lim.name)
    for name, rel in [("instruction.md", "instruction.md"), ("README.md", "README.md"), ("task.toml", "task.toml"),
                      ("docker-compose.yaml", "environment/docker-compose.yaml"), ("Dockerfile", "environment/Dockerfile"),
                      ("tests.Dockerfile", "tests/Dockerfile"), ("test.sh", "tests/test.sh"),
                      ("solve.sh", "solution/solve.sh")]:
        write(lim / rel, fill((TEMPLATES / "limited" / name).read_text(), ctx_lim), executable=rel.endswith(".sh"))
    sim = lim / "environment" / "sim"          # what the sidecar mounts at /srv; the agent's image never sees it
    write(sim / "instance.json", inst)
    for src, dst in [(SHARED / "limited" / "server.py", sim / "server.py"), (SHARED / "rcb_kinder.py", sim / "rcb_kinder.py"),
                     (COMMON / "rcb_service.py", sim / "rcb_service.py"),
                     (SHARED / "limited" / "rcb_client.py", lim / "environment" / "rcb_client.py"),
                     (COMMON / "grade.py", lim / "tests" / "grade.py")]:
        shutil.copyfile(src, dst)

    _check_instruction(lim, ctx_lim, t, d)
    return [full, lim]


def _check_instruction(out: Path, ctx: dict, t: dict, d: dict) -> None:
    """The goal and the episode length are what the agent is judged on: both must be in the text it reads."""
    text = (out / "instruction.md").read_text()
    assert ctx["task_statement"] in one_line(text), f"{out.name}: instruction.md lost the task statement"
    assert f"{max_steps(t, d)} control steps" in text, f"{out.name}: instruction.md lost the episode length"


# --------------------------------------------------------------------------- simulator-backed
def probe_limited(inst: Path, work: Path, images: Path) -> dict:
    """The real sidecar service, driven through the shipped client: contract, reset, finalize, cost per step; the
    cameras' t=0 images go to `images` (for the results pages: build.py --cameras)."""
    import imageio.v2 as imageio
    import numpy as np
    sim = work / "sim"
    sim.mkdir()
    for src in (SHARED / "limited" / "server.py", SHARED / "rcb_kinder.py", COMMON / "rcb_service.py"):
        shutil.copyfile(src, sim / src.name)
    shutil.copyfile(inst, sim / "instance.json")
    data = work / "data"
    env = {**os.environ, "RCB_INSTANCE": str(sim / "instance.json"), "RCB_DATA": str(data), "RCB_RESET_BUDGET": "2",
           "RCB_OBS_ROOM_CAMERA": "1", "RCB_OBS_DEPTH": "1", "RCB_TASK_TEXT": "probe"}
    proc = subprocess.Popen([sys.executable, str(sim / "server.py")], env=env, stdout=subprocess.DEVNULL,
                            stderr=open(work / "server.log", "w"))
    try:
        sys.path.insert(0, str(SHARED / "limited"))
        from rcb_client import Robot
        r = Robot("http://localhost:8000", timeout=300)
        sp, dim = r.spec(), r.spec()["delta"]["dim"]
        layout, low, high = sp["delta"]["layout"], sp["delta"]["low"], sp["delta"]["high"]
        own = [c for c in sp["cameras"] if c != "room_camera"]
        digest = lambda o: {c: hashlib.sha256(v.tobytes()).hexdigest()[:12]  # noqa: E731
                            for c, v in [*o["images"].items(), *(("depth " + k, d) for k, d in o.get("depth", {}).items())]}
        t0 = r.observe()
        repeat = all(digest(r.observe()) == digest(t0) for _ in range(3))
        images.mkdir(parents=True, exist_ok=True)
        for c, v in t0["images"].items():
            imageio.imwrite(images / f"t0_{c}.png", v)
        zero = np.zeros(dim)
        bad = zero.copy()
        bad[:2] = 0.8 * high[0]                    # each axis within bounds, together beyond the base's disc
        try:
            r.step("delta", bad, images=False)
            refused = False
        except ValueError:
            refused = True

        def per_step(n: int, images, batch: int = 0) -> float:
            t = time.perf_counter()
            for _ in range(n):
                r.step("delta", np.tile(zero, (batch, 1)) if batch else zero, images=images)
            return (time.perf_counter() - t) * 1000 / (n * (batch or 1))

        ms = {"single": per_step(30, False), "images": per_step(20, own), "batch": per_step(5, False, 10)}
        after = r.reset()
        out = {"cameras": list(sp["cameras"]), "image_hw": sp["cameras"]["robot_wrist"]["hw"],
               "refuses_out_of_range_action": refused, "reset_images_identical": digest(after) == digest(t0),
               "repeat_images_identical": repeat,   # the same state twice gives the same frames, every camera
               "reset_proprio_identical": after["proprio"] == t0["proprio"],
               # rendered, not black; a robot camera facing a wall or cupboard front is legitimately near-flat,
               # so only the room camera, which frames the task, must show structure
               "images_rendered": all(float(v.mean()) > 5.0 for v in t0["images"].values())
                                  and float(t0["images"]["room_camera"].std()) > 1.0,
               # depth where spec says, and in metres: the wrist sees the floor or a table within a few metres
               "depth_rendered": set(t0.get("depth", {})) == {"robot_wrist"} == set(sp["depth"]["cameras"])
                                 == {c for c, v in sp["cameras"].items() if v["depth"]}
                                 and 0.05 < float(np.median(t0["depth"]["robot_wrist"][t0["depth"]["robot_wrist"] > 0])) < 10.0,
               "step_ms": {k: round(v, 1) for k, v in ms.items()}}
        # a real episode for the finalize to replay: random bounded moves, the base's included (odometry -> world),
        # half the bounds (the base's within its disc) and the gripper at either end of its range
        rng = np.random.default_rng(0)
        half = np.array([0.0 if h is None else 0.5 * h for h in high])
        acts = rng.uniform(-1, 1, (40, dim)) * half
        acts[:, :2] = rng.uniform(-0.7, 0.7, (40, 2)) * high[0]
        g = layout.index("gripper")
        acts[:, g] = rng.choice([low[g], high[g]], 40)
        for a in acts:                         # one by one: a batch stops at a step the robot refuses (blocked)
            r.step("delta", a, images=False)
        proc.send_signal(signal.SIGUSR1)       # what the verifier's collect hook does
        for _ in range(300):
            final = json.loads((data / "final.json").read_text())
            if final.get("finalized"):
                break
            time.sleep(1)
        # iterate, not list(): the reader reports its length as infinite, and list() would preallocate for it
        frames = [f for f in imageio.get_reader(str(data / "replay.mp4"), format="FFMPEG")] if final.get("video") else []
        out["finalize_deterministic"] = bool(final.get("deterministic")) and final.get("n_actions") == len(acts)
        out["finalize_video"] = len(frames) > 1 and float(frames[-1].mean()) > 5.0
        return out
    finally:
        proc.kill()


def stated_bound(v, side: int) -> float | None:
    """An action bound to 4 decimals, as the instruction states it, stepped inward where rounding lands outside it
    in the space's own dtype: an action can take a stated bound as it is."""
    if not math.isfinite(v):
        return None
    r = round(float(v), 4)
    return round(r - side * 1e-4, 4) if side * (type(v)(r) - v) > 0 else r


def measure_one(t: dict, d: dict, images: Path) -> dict:
    import numpy as np
    sys.path.insert(0, str(SHARED))
    import gymnasium
    from rcb_kinder import Session
    work = Path(tempfile.mkdtemp(prefix=f"kinder-{t['family']}-"))
    inst = work / "instance.json"
    inst.write_text(json.dumps(instance(t, d, None)))
    s = Session(inst)
    sha = s.state_sha()
    inst.write_text(json.dumps(instance(t, d, sha)))
    low, high, dim = s.action_space.low, s.action_space.high, s.action_space.shape[0]
    f = {"scene_sha": sha, "obs_dim": int(s.obs().shape[0]), "action_dim": int(dim),
         "entry_point": gymnasium.spec(s.env_id).entry_point,
         "action_doc": s.env.unwrapped.metadata.get("action_space_description", ""),
         "action_low": [stated_bound(v, -1) for v in low], "action_high": [stated_bound(v, +1) for v in high]}
    t0 = time.perf_counter()
    nop = s.replay(np.zeros((s.max_steps, dim)))              # holding still for the whole episode
    f["episode_seconds"] = round(time.perf_counter() - t0, 1)
    f["nop_success"] = nop["success"]
    rng = np.random.default_rng(0)                            # a bounded random trajectory: in process twice, then fresh
    acts = rng.uniform(np.where(np.isfinite(low), low, 0), np.where(np.isfinite(high), high, 0), size=(200, dim))
    acts[:, :2] *= 0.7                                        # the base move inside a limited twin's disc (0.7 of the box)
    t0 = time.perf_counter()
    a, b = s.replay(acts), s.replay(acts)
    moving = (time.perf_counter() - t0) / (a["steps"] + b["steps"]) * s.max_steps
    f["episode_seconds"] = max(f["episode_seconds"], round(moving, 1))   # PyBullet checks collisions only on a move
    np.savez(work / "traj.npz", actions=acts, env_id=s.env_id, seed=s.seed, meta="{}")
    last = subprocess.run([sys.executable, str(SHARED / "rcb_kinder.py"), "replay", "--instance", str(inst), "--traj",
                           str(work / "traj.npz")], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
    fresh = json.loads(last[last.index("{"):])   # PyBullet prints "base_root" to stdout, with no newline, on loading
    f["deterministic"] = a["state_sha"] == b["state_sha"] == fresh["state_sha"]
    f["limited"] = probe_limited(inst, work, images / t["family"])
    shutil.rmtree(work, ignore_errors=True)
    return f


def checks(fam: str, f: dict) -> list[str]:
    bad = [k for k, v in f["limited"].items() if v is False]   # the sidecar's checks: every flag must hold
    bad += ["nop passes"] if f["nop_success"] else []
    bad += ["replay not deterministic"] if not f["deterministic"] else []
    return [f"{fam}: {b}" for b in bad]


def cmd_measure(args) -> int:
    d, tasks = load()
    facts, failed = load_facts(), []
    for t in select(args.families, tasks):
        facts[t["family"]] = f = measure_one(t, d, Path(args.images))
        failed += checks(t["family"], f)
        print(t["family"], json.dumps(f), flush=True)
        FACTS.write_text(json.dumps(facts, indent=1, sort_keys=True) + "\n")   # after each: a crash keeps the rest
    print("\n".join(f"FAIL {x}" for x in failed) or "measure: all checks pass")
    return 1 if failed else 0


def cmd_verify(args) -> int:
    d, tasks = load()
    facts, failed = load_facts(), []
    for t in select(args.families, tasks):
        new, old = measure_one(t, d, Path(args.images)), facts.get(t["family"], {})
        failed += checks(t["family"], new)
        for k in ("scene_sha", "obs_dim", "action_dim", "action_low", "action_high", "nop_success", "entry_point",
                  "action_doc"):
            if new[k] != old.get(k):
                failed.append(f"{t['family']}: {k} drifted: facts.json {old.get(k)}, measured {new[k]}")
    print("\n".join(f"FAIL {x}" for x in failed) or "verify: all checks pass")
    return 1 if failed else 0


def cmd_render(args) -> int:
    d, tasks = load()
    facts = load_facts()
    for t in select(args.families, tasks):
        if t["family"] not in facts:
            raise SystemExit(f"{t['family']}: no facts yet -- run `gen_tasks.py measure {t['family']}` in the image")
        for out in render(t, d, facts[t["family"]]):
            print("rendered", out.relative_to(ROOT))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="gen_tasks.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("render", "measure", "verify"):
        q = sub.add_parser(name)
        q.add_argument("families", nargs="*")
        if name != "render":
            q.add_argument("--images", default="/tmp/rcb-limited-images", help="where the t=0 camera images go")
    a = p.parse_args()
    return {"render": cmd_render, "measure": cmd_measure, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
