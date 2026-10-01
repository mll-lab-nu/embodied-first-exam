#!/usr/bin/env python3
"""gen_tasks.py -- every tasks/kinder-* directory, rendered from subset.toml, facts.json, templates/, shared/ and oracles/.

  ./gen_tasks.py render  [family ...]   rewrite both modes' task dirs (keeps their results/; no simulator needed)
  ./gen_tasks.py check                  fail unless tasks/ is exactly what render writes, and no task names another
  ./gen_tasks.py measure [family ...]   pin, check and time each instance -> facts.json (in the image, with a GPU)
  ./gen_tasks.py verify  [family ...]   measure again; fail on drift, a passing nop, a non-deterministic replay
  measure and verify also write the cameras' t=0 images, --images DIR/<family>/t0_<camera>.png; verify leaves
  facts.json as it is.

What a task says in words comes from subset.toml; every number it states (the scene's digest, the action space, the
costs) comes from facts.json, which only `measure` writes. The simulator-backed commands run in the image:

  docker run --rm --gpus all -e NVIDIA_DRIVER_CAPABILITIES=compute,graphics,utility -v $PWD:/repo -w /repo \\
    --user $(id -u):$(id -g) -e HOME=/tmp <image: images/kinder/VERSION> python scripts/kinder/gen_tasks.py measure
"""
from __future__ import annotations

import argparse
import ast
import filecmp
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
SHARED, TEMPLATES, ORACLES, FACTS = HERE / "shared", HERE / "templates", HERE / "oracles", HERE / "facts.json"
STANDARD = SHARED / "standard"                 # the standard-mode sidecar, client and verifier (eai-standard/2.1)
IMAGE = "ghcr.io/embodied-agent-interface-v2-internal/eai-kinder:" + (ROOT / "images/kinder/VERSION").read_text().strip()
# The agent container and the verifier of every standard-mode task: Python and the client only, pinned by digest.
CLIENT_IMAGE = ("docker.io/library/python:3.12.14-slim"
                "@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f")
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


def agent_hosts() -> list[str]:
    """The model-API hosts every task's agent may reach: scripts/set_agent_egress.py's HOSTS, the repository's one list
    (read, not imported: that script acts on import)."""
    tree = ast.parse((ROOT / "scripts" / "set_agent_egress.py").read_text())
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "HOSTS" for t in n.targets))


# What a standard-mode twin says about its robot's sensors, by kind: the instruction's robot, sensors, cost and
# proprio lines, the README's and task.toml's sensor lists.
_ODOM = "the base's odometry (where it is relative to where it started)"
_BOTH = {"images_what": "both robot cameras' images (and the wrist's depth)",
         "sensors_short": "two\ncameras, joint encoders, the base's odometry",
         "sensors_plus": "camera RGB-D + joint encoders + base odometry"}
SENSORS = {
    "tidybot": {"standard_robot": "a simulated TidyBot++ mobile manipulator (KinDER / MuJoCo) -- a holonomic base, a "
                                  "Kinova Gen3 7-DoF\narm and a Robotiq 2F-85 gripper",
                "sensors": "its two cameras (RGB, {hw}: `robot_base` on the base, `robot_wrist` on the arm's last "
                           "link, which also gives depth), its joint encoders (the arm's angles and velocities, the "
                           "gripper) and " + _ODOM,
                "proprio_text": "Each proprioception row (`meta[\"proprio\"][\"now\"]`, `res.proprio`) has, in "
                                "`spec()[\"proprio_layout\"]` order: `base_x`, `base_y`, `base_yaw` (the odometry frame: "
                                "where the base started, x the way it faced, y left), `base_vx`, `base_vy`, "
                                "`base_yaw_rate`, `arm_1` ... `arm_7`, `arm_1_vel` ... `arm_7_vel`, `gripper` (the "
                                "fingers' position: 0 open, 1 at their closed limit) and `gripper_vel`; "
                                "`spec()[\"proprio\"]` gives the units.", **_BOTH},
    "kinematic3d": {"standard_robot": "a simulated mobile manipulator (KinDER / PyBullet, kinematic) -- a TidyBot++ base, "
                                      "a Kinova Gen3\n7-DoF arm and a Robotiq 2F-85 gripper",
                    "sensors": "its two cameras (RGB, {hw}: `robot_base` on the base, `robot_wrist` on the arm's last "
                               "link, which also gives depth), its joint encoders (the arm's angles, the gripper) and "
                               + _ODOM,
                    "proprio_text": "Each proprioception row (`meta[\"proprio\"][\"now\"]`, `res.proprio`) has, in "
                                    "`spec()[\"proprio_layout\"]` order: `base_x`, `base_y`, `base_yaw` (the odometry "
                                    "frame: where the base started, x the way it faced, y left), `arm_1` ... `arm_7` "
                                    "and `gripper` (the fingers' position: 0 open, 1 at their closed limit); the robot "
                                    "is kinematic, so it reports no velocities. `spec()[\"proprio\"]` gives the units.",
                    **_BOTH},
}


def kind(entry_point: str) -> str:
    """KinDER's category, from the environment's registered entry point: tidybot (MuJoCo) or kinematic3d (PyBullet),
    the two robots with a standard-mode adapter."""
    tidybot = entry_point.startswith("kinder.envs.dynamic3d.") and not entry_point.endswith(":Franka3DEnv")
    k = "tidybot" if tidybot else entry_point.split(".")[2]
    if k not in KINDS:
        raise SystemExit(f"{entry_point}: not a robot these tasks support ({', '.join(KINDS)})")
    return k


# The standard sidecar's GPU (docker-compose.yaml), for the MuJoCo tasks' images.
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
def action_layout(f: dict, standard: bool) -> str:
    """The action vector, value by value, as the agent addresses it in this mode."""
    dim, vel, k = f["action_dim"], f["action_dim"] == 18, kind(f["entry_point"])
    if standard:                                # both robots' base, in the odometry frame
        mag = f"{f['action_high'][0]:g}"
        rows = [f'Each row of a `delta` chunk is {dim} numbers, one '
                f'{"10 Hz control step" if k == "tidybot" else "step"}, in the order of '
                '`spec()["action_types"]["delta"]["layout"]`:',
                f"- `base_x`, `base_y`: how far to move the base, metres in the odometry frame, together at most {mag} a "
                f"step; `base_yaw`: how far to turn it, radians (+ = counter-clockwise), at most {mag}."]
        if k == "kinematic3d":
            return "\n".join(rows + [
                f"- `arm_1` ... `arm_7`: radians to add to each of the 7 arm joints' angles, each at most {mag} a step; "
                "the arm moves there at once.",
                "- `gripper`: below -0.5 closes the gripper, above 0.5 opens it, in between leaves it as it is; when "
                "that takes hold or lets go: `spec()[\"action_types\"][\"delta\"][\"semantics\"]`."])
    elif k != "tidybot":                        # privileged mode: upstream's own table, and the bounds
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
    arm = "`arm_1` ... `arm_7`" if standard else "`[3:10]` arm"
    grip = "`gripper`" if standard else "`[10]` gripper"
    rows += [f"- {arm}: radians to add to each of the 7 arm joints' measured angles, each at most 0.1 a step; the sums "
             "are the joints' new targets, which the arm's PD controller tracks.",
             f"- {grip}: 0 = open, 1 = closed (a command, not a change)."]
    if vel:
        rows.append(f"- {'`arm_1_vel` ... `arm_7_vel`' if standard else '`[11:18]` arm'}: joint velocity targets, rad/s, "
                    "unbounded, which the PD controller tracks along with the position targets.")
    return "\n".join(rows)


def goal_text(stmt: str) -> str:
    """The goal alone, for the sidecar's /spec."""
    first = stmt.split(". ")[0].rstrip(".")
    return first[0].upper() + first[1:] + "."


def oracle_fields(t: dict, d: dict, mode: str) -> dict:
    """oracle / oracle_evidence (docs/PROTOCOL.md §2.7) and what the README says about it: an oracle where
    oracles/<family>/<mode>/ has one, else none, with the evidence subset.toml names and the human review."""
    review = f"PR #{d['review_pr']}" if d.get("review_pr") else "this benchmark's pull request"
    if (ORACLES / t["family"] / mode).is_dir():
        return {"oracle_lines": 'oracle = "full"', "reference_solution": one_line(t["oracle_" + mode]),
                "oracle_note": "The oracle (`solution/solve.sh`) scores 1; `nop` scores 0."}
    evidence = one_line(t["oracle_evidence"]) + f"; human review in {review}"
    return {"oracle_lines": f'oracle = "none"\noracle_evidence = {json.dumps(evidence, ensure_ascii=False)}',
            "reference_solution": "None. Solvability rests on the positive example in `oracle_evidence` (task.toml), "
                                  "checked by a human reviewer (docs/PROTOCOL.md §2.7).",
            "oracle_note": f"No oracle; human review in {review}. `nop` scores 0."}


def context(t: dict, d: dict, f: dict) -> dict:
    """The privileged task's placeholders; standard_context() adds its twin's."""
    stmt = one_line(t["task_statement"])
    full = f"kinder-{t['family']}-{d['instance_tag']}"
    std = f["standard"]
    ms = std["step_ms"]
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
        "twin": f"{full}-standard", "sim_gpu": SIM_GPU if mujoco else "",
        "robot_seconds": f"{n / 10:g}", "task_statement": stmt, "difficulty": one_line(t["difficulty"]),
        "task_dir": full, "twin_dir": full, "image": IMAGE, "client_image": CLIENT_IMAGE,
        "allowed_hosts": ", ".join(f'"{h}"' for h in agent_hosts()),
        "obs_dim": f["obs_dim"], "action_dim": f["action_dim"],
        "episode_seconds": f"{f['episode_seconds']:.0f}" if f["episode_seconds"] >= 0.5 else f"{f['episode_seconds']:.1g}",
        "action_layout": action_layout(f, standard=False),
        "standard_action_layout": action_layout(f, standard=True),
        "expert_hours": t["expert_hours"], "standard_expert_hours": 2 * t["expert_hours"],
        "agent_timeout": float(d["agent_timeout_sec"]), "agent_timeout_hours": f"{d['agent_timeout_sec'] / 3600:g}",
        "verifier_timeout": float(d["verifier_timeout_sec"]), "image_hw": "×".join(map(str, std["image_hw"])),
        "ms_single": f"{ms['single']:.1f}", "ms_images": f"{ms['images']:.1f}", "ms_batch": f"{ms['batch']:.1f}",
        **oracle_fields(t, d, "privileged"),
    }


def standard_context(t: dict, d: dict, f: dict, ctx: dict, task_dir: str) -> dict:
    """The standard twin's placeholders: its robot's sensors, and its own goal sentence where the privileged one names
    the goal by world coordinates or state names (subset.toml `standard_statement`)."""
    stmt = one_line(t.get("standard_statement", t["task_statement"]))
    text = {k: v.format(hw=ctx["image_hw"]) for k, v in SENSORS[kind(f["entry_point"])].items()}
    kinematic = kind(f["entry_point"]) == "kinematic3d"
    return ctx | text | {"task_dir": task_dir, "task_statement": stmt,
                         "task_text_yaml": json.dumps(goal_text(stmt), ensure_ascii=False),   # a YAML string, quotes and all
                         "robot_time": f" ({ctx['robot_seconds']} s of robot time)" if ctx["view"] == "task_view" else "",
                         "chunk_rows": 100,   # max_chunk_s (10 s) / control_dt (0.1 s)
                         "blocked_note": " or at a step the robot refuses (`meta[\"blocked\"]`)" if kinematic else "",
                         **oracle_fields(t, d, "standard")}


def write(path: Path, text: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip("\n") + "\n")
    if executable:
        path.chmod(0o755)


def clear(out: Path) -> None:
    """Everything render writes goes; results/ (agent runs, written by hand or by results tooling) stays."""
    if out.is_dir():
        for p in out.iterdir():
            if p.name != "results":
                shutil.rmtree(p) if p.is_dir() else p.unlink()


def copy_oracle(t: dict, mode: str, out: Path) -> None:
    """solution/: the files of oracles/<family>/<mode>/, plus those directly under oracles/<family>/ (both modes')."""
    fam = ORACLES / t["family"]
    if (fam / mode).is_dir():
        (out / "solution").mkdir(parents=True, exist_ok=True)
        for f in sorted([*(fam / mode).iterdir(), *(p for p in fam.iterdir() if p.is_file())]):
            shutil.copy2(f, out / "solution" / f.name)


def render(t: dict, d: dict, f: dict, tasks_dir: Path = TASKS_DIR) -> list[Path]:
    """Both modes of one task, from scratch (but their results/): what is not rendered here does not belong."""
    ctx = context(t, d, f)
    inst = json.dumps(instance(t, d, f["scene_sha"]), indent=1) + "\n"
    full = tasks_dir / ctx["task_dir"]
    std = full.with_name(full.name + "-standard")
    for out in (full, std):
        clear(out)

    gpu = [("gpu.docker-compose.yaml", "environment/gpu.docker-compose.yaml")] if ctx["view"] == "task_view" else []
    for name, rel in [("instruction.md", "instruction.md"), ("README.md", "README.md"), ("task.toml", "task.toml"),
                      ("Dockerfile", "environment/Dockerfile"), *gpu,   # the GPU speeds up MuJoCo's images only
                      ("test.sh", "tests/test.sh")]:
        write(full / rel, fill((TEMPLATES / name).read_text(), ctx), executable=rel.endswith(".sh"))
    for rel in ("environment", "tests"):
        write(full / rel / "instance.json", inst)
        shutil.copyfile(SHARED / "rcb_kinder.py", full / rel / "rcb_kinder.py")
    shutil.copyfile(SHARED / "grade.py", full / "tests" / "grade.py")
    ctx["tests_files"] = " ".join(sorted(p.name for p in (full / "tests").iterdir()))
    write(full / "tests" / "Dockerfile", fill((TEMPLATES / "tests.Dockerfile").read_text(), ctx))
    copy_oracle(t, "privileged", full)
    _check_instruction(full, ctx, t, d)

    ctx_std = standard_context(t, d, f, ctx, std.name)
    for name, rel in [("instruction.md", "instruction.md"), ("README.md", "README.md"), ("task.toml", "task.toml"),
                      ("docker-compose.yaml", "environment/docker-compose.yaml"), ("Dockerfile", "environment/Dockerfile"),
                      ("tests.Dockerfile", "tests/Dockerfile"), ("test.sh", "tests/test.sh")]:
        write(std / rel, fill((TEMPLATES / "standard" / name).read_text(), ctx_std), executable=rel.endswith(".sh"))
    sim = std / "environment" / "sim"           # what the sidecar mounts at /srv; the agent's image never sees it
    write(sim / "instance.json", inst)
    for src, dst in [(STANDARD / "server.py", sim / "server.py"), (STANDARD / "rcb_service.py", sim / "rcb_service.py"),
                     (STANDARD / "rcb1.py", sim / "rcb1.py"), (SHARED / "rcb_kinder.py", sim / "rcb_kinder.py"),
                     (STANDARD / "rcb_client.py", std / "environment" / "rcb_client.py"),
                     (STANDARD / "rcb1.py", std / "environment" / "rcb1.py"),
                     (STANDARD / "grade.py", std / "tests" / "grade.py")]:
        shutil.copyfile(src, dst)
    copy_oracle(t, "standard", std)
    _check_instruction(std, ctx_std, t, d)
    return [full, std]


def _check_instruction(out: Path, ctx: dict, t: dict, d: dict) -> None:
    """The goal and the episode length are what the agent is judged on: both must be in the text it reads."""
    text = (out / "instruction.md").read_text()
    assert ctx["task_statement"] in one_line(text), f"{out.name}: instruction.md lost the task statement"
    assert f"{max_steps(t, d)} control steps" in text, f"{out.name}: instruction.md lost the episode length"


# --------------------------------------------------------------------------- check
def names_another_task(task: Path, families: set[str]) -> list[str]:
    """Identifier-shaped mentions of another family in what a task ships into its containers ("dynamo", 'shelf',
    kinder/Shelf3D-..., --family shelf); plain English words ("the top shelf") do not count."""
    own = tomllib.loads((task / "task.toml").read_text())["metadata"]["family"]
    bad = []
    for sub in ("environment", "tests", "solution"):
        for f in sorted((task / sub).rglob("*")) if (task / sub).is_dir() else []:
            if f.is_file() and f.suffix not in (".npz", ".npy", ".pyc"):
                text = f.read_text(errors="ignore")
                bad += [f"{f.relative_to(task)} names {o}" for o in sorted(families - {own})
                        if re.search(rf"""["']{re.escape(o)}["']|--(?:task|family)\s+{re.escape(o)}\b""", text)]
    return bad


def cmd_check(args) -> int:
    """tasks/ must be what render writes from today's sources (results/ aside), with no stale kinder-* directory, and
    no task may name another."""
    d, tasks = load()
    facts, failed = load_facts(), []
    with tempfile.TemporaryDirectory() as tmp:
        rendered = {p.name for t in tasks.values() for p in render(t, d, facts[t["family"]], Path(tmp))}
        for name in sorted(rendered):
            cmp = filecmp.dircmp(TASKS_DIR / name, Path(tmp) / name, ignore=["results", "__pycache__"])
            failed += _diff(cmp, name)
    failed += [f"tasks/{p.name}: no longer rendered" for p in sorted(TASKS_DIR.glob("kinder-*")) if p.name not in rendered]
    for name in sorted(rendered):
        failed += [f"tasks/{name}: {b}" for b in names_another_task(TASKS_DIR / name, set(tasks))]
    print("\n".join(f"FAIL {x}" for x in failed) or f"check: {len(rendered)} task dirs are what render writes")
    return 1 if failed else 0


def _diff(c: filecmp.dircmp, prefix: str) -> list[str]:
    out = [f"tasks/{prefix}/{x}: differs from its render" for x in c.diff_files]
    out += [f"tasks/{prefix}/{x}: not rendered" for x in c.left_only] + [f"tasks/{prefix}/{x}: missing" for x in c.right_only]
    for sub, sc in c.subdirs.items():
        out += _diff(sc, f"{prefix}/{sub}")
    return out


# --------------------------------------------------------------------------- simulator-backed
def probe_standard(inst: Path, work: Path, images: Path) -> dict:
    """The real sidecar service, driven through the shipped client: its contract, a crash it must survive, the finalize,
    the cost per control step; the cameras' t=0 images go to `images`."""
    import imageio.v2 as imageio
    import numpy as np
    sim = work / "sim"
    sim.mkdir()
    for src in (STANDARD / "server.py", STANDARD / "rcb_service.py", STANDARD / "rcb1.py", SHARED / "rcb_kinder.py"):
        shutil.copyfile(src, sim / src.name)
    shutil.copyfile(inst, sim / "instance.json")
    data = work / "data"
    env = {**os.environ, "RCB_INSTANCE": str(sim / "instance.json"), "RCB_DATA": str(data), "RCB_RESET_BUDGET": "2",
           "RCB_OBS_ROOM_CAMERA": "1", "RCB_OBS_DEPTH": "1", "RCB_TASK_TEXT": "probe"}
    log = open(work / "server.log", "w")

    def start() -> subprocess.Popen:
        return subprocess.Popen([sys.executable, str(sim / "server.py")], env=env, stdout=log, stderr=log)

    proc = start()
    try:
        sys.path.insert(0, str(STANDARD))
        from rcb_client import Robot
        r = Robot("http://localhost:8000", timeout=300)
        sp = r.spec()
        dim, layout, low, high = (sp["action_types"]["delta"][k] for k in ("dim", "layout", "low", "high"))
        digest = lambda res: {c: hashlib.sha256(v.tobytes()).hexdigest()[:12]  # noqa: E731
                              for c, v in [*res.last.items(), *(("depth " + k, a) for k, a in res.depth.items())]}
        t0 = r.get_obs(include_depth=True)
        repeat = all(digest(r.get_obs(include_depth=True)) == digest(t0) for _ in range(3))
        images.mkdir(parents=True, exist_ok=True)
        for c, v in t0.last.items():
            imageio.imwrite(images / f"t0_{c}.png", v)
        zero = np.zeros(dim)
        far = zero.copy()
        far[:2] = 0.8 * high[0]                   # each axis within bounds, together beyond the base's disc
        res = r.submit("delta", far, video="none")
        clipped = res.meta["n_clipped"] == 1 and res.meta["executed_rows"] == 1

        def per_step(n: int, rows: int, cameras: list[str], depth: bool = False) -> float:
            t = time.perf_counter()
            for _ in range(n):
                r.submit("delta", np.tile(zero, (rows, 1)), cameras=cameras, include_depth=depth, video="none")
            return (time.perf_counter() - t) * 1000 / (n * rows)

        own = [c for c in sp["cameras"] if c != "room_camera"]   # every answer carries at least one camera's last frame
        ms = {"single": per_step(20, 1, own[:1]), "images": per_step(15, 1, own, depth=True),
              "batch": per_step(5, 10, own[:1])}
        after = r.reset(include_depth=True)
        out = {"protocol": sp["protocol"], "cameras": list(sp["cameras"]), "image_hw": sp["cameras"]["robot_wrist"]["hw"],
               "clips_out_of_range_action": clipped, "reset_images_identical": digest(after) == digest(t0),
               "repeat_images_identical": repeat,   # the same state twice gives the same frames, every camera
               "reset_proprio_identical": after.meta["proprio"]["now"] == t0.meta["proprio"]["now"],
               # rendered, not black; a robot camera facing a wall or cupboard front is legitimately near-flat,
               # so only the room camera, which frames the task, must show structure
               "images_rendered": all(float(v.mean()) > 5.0 for v in t0.last.values())
                                  and float(t0.last["room_camera"].std()) > 1.0,
               # depth where spec says, and in metres: the wrist sees the floor or a table within a few metres
               "depth_rendered": set(t0.depth) == {"robot_wrist"} == {c for c, v in sp["cameras"].items() if v["depth"]}
                                 and 0.05 < float(np.median(t0.depth["robot_wrist"][t0.depth["robot_wrist"] > 0])) < 10.0,
               "step_ms": {k: round(v, 1) for k, v in ms.items()}}
        # a real episode, crashed in the middle and resumed: random bounded moves, half the bounds (the base's inside
        # its disc) and the gripper at either end of its range, sent in chunks
        rng = np.random.default_rng(0)
        half = np.array([0.0 if h is None else 0.5 * h for h in high])
        acts = rng.uniform(-1, 1, (40, dim)) * half
        acts[:, :2] = rng.uniform(-0.7, 0.7, (40, 2)) * high[0]
        g = layout.index("gripper")
        acts[:, g] = rng.choice([low[g], high[g]], 40)
        r.submit("delta", acts[:20], video="none")
        before = r.status(), r.get_obs().meta["proprio"]["now"]
        proc.kill()                             # a crash; compose would restart it: the same episode must come back
        proc.wait()
        proc = start()
        r = Robot("http://localhost:8000", timeout=300)
        out["resumes_same_episode"] = (r.status()["control_steps"], r.get_obs().meta["proprio"]["now"]) == \
                                      (before[0]["control_steps"], before[1])
        for i in range(20, 40, 5):
            if r.submit("delta", acts[i:i + 5], video="none").done:
                break
        proc.send_signal(signal.SIGUSR1)        # what the verifier's collect hook does
        for _ in range(300):
            final = json.loads((data / "final.json").read_text())
            if final.get("finalized"):
                break
            time.sleep(1)
        # iterate, not list(): the reader reports its length as infinite, and list() would preallocate for it
        frames = [f for f in imageio.get_reader(str(data / "replay.mp4"), format="FFMPEG")] if final.get("video") else []
        out["finalize_deterministic"] = bool(final.get("deterministic")) and final.get("sim_startups") == 2
        out["finalize_video"] = len(frames) > 1 and float(frames[-1].mean()) > 5.0
        return out
    finally:
        proc.kill()
        proc.wait()
        log.close()


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
    acts[:, :2] *= 0.7                                        # the base move inside a standard twin's disc (0.7 of the box)
    t0 = time.perf_counter()
    a, b = s.replay(acts), s.replay(acts)
    moving = (time.perf_counter() - t0) / (a["steps"] + b["steps"]) * s.max_steps
    f["episode_seconds"] = max(f["episode_seconds"], round(moving, 1))   # PyBullet checks collisions only on a move
    np.savez(work / "traj.npz", actions=acts, env_id=s.env_id, seed=s.seed, meta="{}")
    last = subprocess.run([sys.executable, str(SHARED / "rcb_kinder.py"), "replay", "--instance", str(inst), "--traj",
                           str(work / "traj.npz")], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
    fresh = json.loads(last[last.index("{"):])   # PyBullet prints "base_root" to stdout, with no newline, on loading
    f["deterministic"] = a["state_sha"] == b["state_sha"] == fresh["state_sha"]
    f["standard"] = probe_standard(inst, work, images / t["family"])
    shutil.rmtree(work, ignore_errors=True)
    return f


def checks(fam: str, f: dict) -> list[str]:
    bad = [k for k, v in f["standard"].items() if v is False]   # the sidecar's checks: every flag must hold
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
    for name in ("render", "check", "measure", "verify"):
        q = sub.add_parser(name)
        if name != "check":
            q.add_argument("families", nargs="*")
        if name in ("measure", "verify"):
            q.add_argument("--images", default="/tmp/rcb-standard-images", help="where the t=0 camera images go")
    a = p.parse_args()
    return {"render": cmd_render, "check": cmd_check, "measure": cmd_measure, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
