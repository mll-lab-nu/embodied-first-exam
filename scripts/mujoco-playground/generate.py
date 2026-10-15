#!/usr/bin/env python3
"""Generate MuJoCo Playground's quadruped tasks: tasks/mujoco_playground_<env>-privileged and ...-standard, and
...-standard-realtime for the environments whose scene is dynamic (REALTIME; PROTOCOL §4b, §2.14).

    python3 scripts/mujoco-playground/generate.py            # every instance in instances/
    python3 scripts/mujoco-playground/generate.py --check    # exit 1 if tasks/ differs from what this would write

Inputs: instances/<Env>.json (the frozen instance with the numbers the texts quote: make_instances.py, then
select_instances.py), oracles/<Env>.npy (the reference rows), the templates in templates/, the shared sources in shared/
and the eai-standard/2.2 layer with the standard client's base image and pins (scripts/eai_standard/), all copied byte
for byte. Each task directory is written from scratch and finished with scripts/task_conventions.py (normalize,
PROTOCOL v1.0.1); a quadruped task directory this does not write is removed. Only the standard library is needed.
The four manipulation tasks of this benchmark (tasks/mujoco_playground_{aloha,panda}_*) are not generated here.
"""
import filecmp
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from task_conventions import normalize  # noqa: E402   (protocol v1.0.1 conventions)

TASKS_DIR = ROOT / "tasks"
SHARED = HERE / "shared"
TEMPLATES = HERE / "templates"
LAYER = ROOT / "scripts/eai_standard"
IMAGE = "ghcr.io/mll-lab-nu/eai-mujoco:0.1.3"   # images/mujoco: 0.1.3 = 0.1.2 + the quadruped assets (prepare_assets.sh)
_ENV = dict(ln.split("=", 1) for ln in (LAYER / "client.env").read_text().splitlines() if "=" in ln and ln[0] != "#")
CLIENT_IMAGE = _ENV["CLIENT_IMAGE"].strip()
AUTHOR, ORG = "Changhe Chen", "MLL Lab"
HOSTS = [
    "chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com",
    "*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com", "pypi.org", "files.pythonhosted.org", "deb.debian.org", "security.debian.org", "archive.ubuntu.com", "security.ubuntu.com", "snapshot.ubuntu.com",
]  # fmt: skip
PREFIXES = ("mujoco_playground_go1_", "mujoco_playground_spot_", "mujoco_playground_barkour_")
CAMERAS = {"go1": "`track`, `side`, `back`, `top` (they follow the robot)", "spot": "`track`, `side`, `back`, `top` (they follow the robot)",
           "barkour": "`track` (follows the robot) and `realsense/rgb` (on its head)"}
GO1_FALL = "the trunk's up axis pointing below the horizon (the z component of the IMU frame's z axis negative)"
SPOT_FALL = "the trunk tilted by more than about 32 deg (the z component of the IMU frame's z axis below 0.85)"
BARKOUR_FALL = ("the trunk's up axis pointing below the horizon, a joint outside its box (abduction [-0.7, 0.52], hip "
                "[-1.0, 2.1], knee [0.05, 2.1] rad) or the torso lower than 0.18 m")
GO1_RESAMPLE = "a new draw after Exp(1) x 5 s; a draw may keep a component"
SPOT_RESAMPLE = "a new draw every 201 control steps, zero with probability 0.1"
BARKOUR_RESAMPLE = "a new draw after 501 control steps"
GO1_JOY_DIFF = ("Torque limits and a soft PD drive leave little margin; Playground trains a neural policy with 200 M steps of "
                "PPO for this.")
GO1_JOY_REF = ("MuJoCo Playground's own Go1 joystick policy (`experimental/sim2sim/onnx/go1_policy.onnx` @4057c14, not in the "
               "image) run closed loop on this instance with the observation of Playground's `play_go1_joystick.py`")
ROBOTS = {
    "go1": {"name": "Unitree Go1", "short": "Go1", "tax": "unitree-go1", "menagerie": "unitree_go1", "feet": "FR, FL, RR, RL",
            "joints": "FR, FL, RR, RL legs, each hip (abduction), thigh (hip pitch), calf (knee)"},
    "barkour": {"name": "Google Barkour vB", "short": "Barkour", "tax": "google-barkour-vb", "menagerie": "google_barkour_vb",
                "feet": "foot_front_left, foot_hind_left, foot_front_right, foot_hind_right",
                "joints": "front-left, hind-left, front-right, hind-right legs, each abduction, hip, knee"},
    "spot": {"name": "Boston Dynamics Spot", "short": "Spot", "tax": "boston-dynamics-spot",
             "menagerie": "boston_dynamics_spot", "feet": "FL, FR, HL, HR",
             "joints": "FL, FR, HL, HR legs, each hx (abduction), hy (hip pitch), kn (knee)"},
}
ENVS = {
    "Go1JoystickFlatTerrain": {"robot": "go1", "kind": "joystick", "kp": 35, "kd": 0.5, "sim_dt": 0.004,
                               "dt": 0.02, "start": "random", "fall": GO1_FALL, "resample": GO1_RESAMPLE,
                               "difficulty": GO1_JOY_DIFF, "reference": GO1_JOY_REF,
                               "xml": "locomotion/go1/xmls/scene_mjx_feetonly_flat_terrain.xml"},
    "Go1JoystickRoughTerrain": {"robot": "go1", "kind": "joystick", "kp": 35, "kd": 0.5, "sim_dt": 0.004,
                               "dt": 0.02, "start": "random", "fall": GO1_FALL, "resample": GO1_RESAMPLE,
                               "difficulty": GO1_JOY_DIFF, "reference": GO1_JOY_REF,
                                "xml": "locomotion/go1/xmls/scene_mjx_feetonly_rough_terrain.xml"},
    "Go1Getup": {"robot": "go1", "kind": "getup", "kp": 35, "kd": 0.5, "sim_dt": 0.004, "min_h": 0.22, "stand_h": "0.255-0.26",
                 "lie_h": 0.15, "drop": "0.5 m in a random orientation with random joint angles and a random base velocity",
                 "xml": "locomotion/go1/xmls/scene_mjx_fullcollisions_flat_terrain.xml",
                 "difficulty": "A trained policy reaches a level crouch easily; standing up from it at the right moment is the rest.",
                 "reference": "A policy trained here on Playground's Go1Getup reward (PPO on the CPU, `scripts/mujoco-playground/"
                              "train/`, not in the image) turns the robot belly-down and level; then the joint targets go "
                              "linearly to the `home` pose in 1 s and hold until the check completes"},
    "SpotGetup": {"robot": "spot", "kind": "getup", "kp": 400, "kd": 20, "sim_dt": 0.004, "min_h": 0.40, "stand_h": "0.44",
                  "lie_h": 0.38, "drop": "1 m in a random orientation with random joint angles (no base velocity)",
                  "xml": "locomotion/spot/xmls/scene_mjx_flat_terrain.xml",
                  "difficulty": "Spot's trunk alone weighs 33 kg and its legs are long: a turn has to be timed against gravity.",
                  "reference": "A policy trained here on Playground's SpotGetup reward (PPO on the CPU, `scripts/mujoco-"
                               "playground/train/`, not in the image), run closed loop until the check completes"},
    "SpotFlatTerrainJoystick": {"robot": "spot", "kind": "joystick", "kp": 300, "kd": 1, "kv": 20,
                                "sim_dt": 0.004, "dt": 0.02, "start": "home", "fall": SPOT_FALL, "resample": SPOT_RESAMPLE,
                                "xml": "locomotion/spot/xmls/scene_mjx_feetonly_flat_terrain.xml",
                                "difficulty": "Spot is large and heavy, and Playground stops the episode once its trunk tilts "
                                              "by about 32 deg, so the gait has to stay level.",
                                "reference": "A policy trained here on Playground's SpotFlatTerrainJoystick reward (PPO on the "
                                             "CPU, `scripts/mujoco-playground/train/`, not in the image)"},
    "SpotJoystickGaitTracking": {"robot": "spot", "kind": "joystick", "kp": 400, "kd": 10, "kv": 20,
                                 "sim_dt": 0.004, "dt": 0.02, "start": "home", "fall": SPOT_FALL, "resample": SPOT_RESAMPLE,
                                 "gait": True, "xml": "locomotion/spot/xmls/scene_mjx_feetonly_flat_terrain.xml",
                                 "difficulty": "On top of the velocity commands the feet have to follow a commanded gait: "
                                               "which feet swing together, at a fixed frequency and to a commanded height.",
                                 "reference": "A policy trained here on Playground's SpotJoystickGaitTracking reward (PPO on "
                                              "the CPU, `scripts/mujoco-playground/train/`, not in the image), with the "
                                              "command added to its observation (`train/qenv.py` SpotJoystickGaitTrackingCmd: "
                                              "Playground's observation leaves the command out, so a policy trained on it "
                                              "marches in place and cannot track the joystick its reward asks for)"},
    "BarkourJoystick": {"robot": "barkour", "kind": "joystick", "kp": 35, "kd": 0.5239, "kv": 0.5,
                        "sim_dt": 0.002, "dt": 0.01, "start": "home", "fall": BARKOUR_FALL, "resample": BARKOUR_RESAMPLE,
                        "pushes": True, "xml": "menagerie/google_barkour_vb/scene_mjx.xml",
                        "difficulty": "Random pushes on the torso come at fixed but unannounced times; the gait has to "
                                      "absorb them without a joint leaving its box.",
                        "reference": "A policy trained here on Playground's BarkourJoystick reward, pushes included (PPO on "
                                     "the CPU, `scripts/mujoco-playground/train/`, not in the image)"},
    "Go1Handstand": {"robot": "go1", "kind": "stand_on_two", "kp": 35, "kd": 0.5, "sim_dt": 0.004, "min_h": 0.40,
                     "pose": "handstand", "on": "front", "air": "hind (RR, RL)", "dir": "down", "z_des": 0.55,
                     "xml": "locomotion/go1/xmls/scene_mjx_flat_terrain.xml"},
    "Go1Footstand": {"robot": "go1", "kind": "stand_on_two", "kp": 35, "kd": 0.5, "sim_dt": 0.004, "min_h": 0.40,
                     "pose": "footstand", "on": "hind", "air": "front (FR, FL)", "dir": "up", "z_des": 0.53, "hind": True,
                     "train_note": " with three training-only changes (`train/qenv.py` Go1FootstandStrict3): this task's "
                                   "hind-leg termination (with Playground's rule alone it learns to sit on a hind hip), half "
                                   "of the episodes starting in Playground's `footstand` keyframe, and a steeper height reward "
                                   "(with Playground's it settles in a squat at 0.2 m)",
                     "xml": "locomotion/go1/xmls/scene_mjx_flat_terrain.xml"},
}
SETTLE, LIN_TOL, YAW_TOL, HOLD, TILT, POSE_HOLD, POSE_TOL, GAIT_TOL = 25, 0.2, 0.3, 25, 10, 100, 30, 0.05
RESET_BUDGET = 10  # standard mode's default reset budget (owner, 2026-10-14; PROTOCOL §4.5, docs/benchmarks/mujoco-playground.md)

PRIV_ENV_DOCKERFILE = f"""# MuJoCo Playground quadruped task (privileged): plain MuJoCo with Playground's and Menagerie's assets
# (images/mujoco/prepare_assets.sh), the task's tooling and its frozen instance.
FROM {IMAGE}
COPY instance.json /app/instance.json
COPY rcb_quadruped.py /opt/tools/rcb_quadruped.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""
PRIV_TESTS_DOCKERFILE = f"""# Separate verifier sandbox (PROTOCOL §4): the same image with the verifier's own copies of the tooling and the frozen
# instance. Nothing the agent did in its container reaches this one: Harbor uploads only the declared artifacts.
FROM {IMAGE}
COPY grade.py instance.json rcb_quadruped.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
"""
STD_ENV_DOCKERFILE = f"""# Standard mode: the agent container has NO simulator and no Playground code, only Python and the client, on the shared
# pinned client base with the shared pins (scripts/eai_standard/client.env, client-requirements.txt).
FROM {CLIENT_IMAGE}
COPY client-requirements.txt /tmp/client-requirements.txt
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY rcb_client.py rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""
STD_TESTS_DOCKERFILE = f"""# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but python (the shared client base).
FROM {CLIENT_IMAGE}
COPY test.sh /tests/test.sh
COPY grade.py /tests/grade.py
RUN chmod +x /tests/test.sh
"""
# The agent's time cutoff per mode (PROTOCOL §2.12): this benchmark's own number, written into every task's `[agent]
# timeout_sec`, the one source; normalize renders from it the instruction's closing `## Time limit`, the README row and
# the sim service's wall clock. To change it (an owner decision; the pull request states old -> new), edit it here and
# regenerate.
CUTOFF = {"privileged": 1800, "standard": 1800, "standard-realtime": 1800}
STD_COMPOSE = f"""# Standard mode: the simulator runs in the `sim` sidecar (the agent cannot open it); the agent only reaches port 8000.
# No `expose`/`ports` on sim: under Harbor's egress control it shares main's network namespace (localhost:8000).
# CPU only: MuJoCo physics and rendering (EGL when a GPU is there, else OSMesa); no GPU reservation.
# Crash recovery (docs/STANDARD_MODE.md §13): run.sh exits non-zero when the service crashes, compose restarts the
# container (same container, same /data) and the service replays its journal into the same episode, never a reset.
services:
  main:
    depends_on: [sim]
  sim:
    image: {IMAGE}
    volumes:
      - ./sim:/srv:ro
    working_dir: /tmp
    command: sh /srv/run.sh
    restart: on-failure:6          # N >= 3 (PROTOCOL §4.1); a resume continues the episode
    environment:
      RCB_INSTANCE: /srv/instance.json
      RCB_TOOL: /srv/rcb_quadruped.py
      RCB_DATA: /data
      RCB_WALL_CLOCK_S: "{CUTOFF['standard']}"
      RCB_STARTUP_TIMEOUT_S: "300"   # the scene builds in about a second
      PYTHONPATH: /srv
      RCB_SESSION_LOG: ""           # the sidecar's own Session must not write the agent-side interaction log
      RCB_RESET_BUDGET: "${{RCB_RESET_BUDGET:-{RESET_BUDGET}}}"   # Playground quadrupeds standard: {RESET_BUDGET} resets (PROTOCOL §4.5); 0: one episode
"""


# ------------------------------------------------------------------------------------------- standard-realtime twins
# The dynamic environments (scripts/task_dynamics.toml; PROTOCOL §2.14) get a `-standard-realtime` twin (owner,
# 2026-10-14, board 0112): the same frozen instance and check, served by shared/realtime/server.py (the rcb_service.Sim
# adapter on rcb_quadruped.Session) behind the shared eai-standard/2.3 layer (rcb_realtime.py + rcb_service.py, copied
# unchanged from scripts/humanoidbench/shared/; check-tooling-identity.sh). Per environment: the slowdown S, from the
# real-time factor RTF of that service measured on the reference workstation (PROTOCOL §4b: S = 1 when RTF >= 3, else
# ~1.5 / RTF rounded up), and how it was measured (docs/benchmarks/mujoco-playground.md, "Standard-realtime").
REALTIME = {
    "BarkourJoystick": {
        "slowdown": 1,
        "rtf": "measured RTF 31.6 (2026-10-14, board 0112, ws-1 at load 44, the service capped at 4 CPUs: the "
               "reference's 1000 rows planned from step 0 with the clock flat out, RCB_SLOWDOWN = 0.01), far above 3, so "
               "S = 1. At S = 1 the reference succeeds live and in the fresh replay with no stall, also streamed one row "
               "per call with a camera image every 0.25 s (7.7 ms each over EGL)",
        "why": "scripted pushes (kicks) apply an external force to the torso at moments the agent is not told",
    },
}
RT_RESET_BUDGET = 10   # PROTOCOL §4b: every standard-realtime task allows resets, 10 by default (owner, 2026-10-14)
RT = SHARED / "realtime"
RT_ENV_DOCKERFILE = f"""# Standard-realtime mode: the agent container has NO simulator and no MuJoCo, only Python and the realtime client
# (eai-standard/2.3), on the shared pinned client base with the shared pins (scripts/eai_standard/client.env).
FROM {CLIENT_IMAGE}
COPY client-requirements.txt /tmp/client-requirements.txt
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY rcb_client.py rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""


def rt_compose(env: str) -> str:
    S = REALTIME[env]["slowdown"]
    return f"""# Standard-realtime mode (PROTOCOL §4b): the simulator runs in the `sim` sidecar (the agent cannot open it), on its own clock
# once an episode starts (sim/rcb_realtime.py, the shared eai-standard/2.3 layer, with sim/server.py, this benchmark's
# adapter); the agent only reaches port 8000. No `expose`/`ports` on sim: under Harbor's egress control it shares
# main's network namespace (localhost:8000).
# GPU on sim: the physics is MuJoCo on the CPU, but every image the agent asks for is rendered here, and on a clock that
# does not stop a render is time the simulator cannot step (EGL on the GPU; OSMesa where EGL does not work).
# `graphics` is the capability that mounts the EGL driver (server.py writes its ICD manifest).
# Crash recovery: compose restarts the service, which resumes the same episode, paused, never a reset.
# Knobs: ${{NAME:-default}} takes NAME from the shell that runs harbor. The defaults are the task's configuration;
# results under other settings are reported separately.
services:
  main:
    depends_on: [sim]
  sim:
    image: {IMAGE}
    volumes:
      - ./sim:/srv:ro
    working_dir: /tmp
    command: python /srv/rcb_realtime.py
    restart: on-failure:6          # N >= 3 (PROTOCOL §4.1); a resume continues the episode, paused
    environment:
      RCB_INSTANCE: /srv/instance.json
      RCB_DATA: /data
      RCB_WALL_CLOCK_S: "{CUTOFF['standard-realtime']}"
      RCB_STARTUP_TIMEOUT_S: "300"   # the scene builds in about a second
      PYTHONPATH: /srv
      RCB_SESSION_LOG: ""           # the sidecar's own Session must not write the agent-side interaction log
      RCB_SLOWDOWN: "${{RCB_SLOWDOWN:-{S}}}"                # S = {S}: the world runs at 1/S of real speed (this environment's measured RTF; PROTOCOL §4b)
      RCB_RESET_BUDGET: "${{RCB_RESET_BUDGET:-{RT_RESET_BUDGET}}}"        # {RT_RESET_BUDGET} resets (PROTOCOL §4b default); 0: one episode
      RCB_GL: "${{RCB_GL:-auto}}"                     # auto: EGL on the GPU when it works, else OSMesa
      NVIDIA_DRIVER_CAPABILITIES: compute,graphics,utility
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
"""


def rt_values(env: str, v: dict) -> dict:
    rt, e = REALTIME[env], ENVS[env]
    dt = e.get("dt", 0.02)
    S = rt["slowdown"]
    ep = v["episode_md_std"].replace("every response's `meta[\"command_now\"]` is the current command",
                                     "the proprioception's `cmd_vx`, `cmd_vy`, `cmd_wz` are the command in force")
    end = (v["std_end"].replace(", when you submit `done`,", ",").replace("when you submit `done`, ", "")
           .replace(" (before the end of the schedule, both are failures)", " (before the end of the schedule, a failure)"))
    success = v["std_success"].replace("(`imu_linvel`)", "(`linvel_*`)").replace("(`imu_gyro`)", "(`gyro_*`)")
    return {**v, "std_success": success, "slowdown": S, "dt_ms": f"{dt * 1000:g}", "control_hz": f"{1 / dt:g}",
            "real_time_note": " (real time)" if S == 1 else "", "episode_md_rt": ep, "rt_end": end,
            "rt_resets": RT_RESET_BUDGET, "rt_episodes": RT_RESET_BUDGET + 1, "expert_hours_rt": "6.0",
            "dynamic_why": rt["why"], "rtf_text": rt["rtf"], "agent_timeout": CUTOFF["standard-realtime"]}


def snake(env: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", env).lower()


def render(template: str, values: dict) -> str:
    text = (TEMPLATES / template).read_text()
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    if "{{" in text:
        raise ValueError(f"{template}: unfilled placeholder near {text[text.index('{{'):][:40]!r}")
    return text


def reset_dir(d: Path) -> None:
    """A task directory is written from scratch: what is not rendered here does not belong (no results/, PROTOCOL D3)."""
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)


def put(path: Path, text: str | None = None, src: Path | None = None, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if src is not None:
        shutil.copyfile(src, path)
    else:
        path.write_text(text)
    path.chmod(mode)


def f(x, d=2) -> str:
    return f"{x:.{d}f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


def schedule_table(inst: dict, dt: float = 0.02) -> str:
    rows = ["| from (s) | vx (m/s) | vy (m/s) | yaw rate (rad/s) |", "|---:|---:|---:|---:|"]
    for c in inst["commands"]:
        rows.append(f"| {c['start_step'] * dt:.2f} | {c['vx']:+.3f} | {c['vy']:+.3f} | {c['wz']:+.3f} |")
    return "\n".join(rows)


def gains(e: dict) -> str:
    """The drive as Playground sets it: Kp as the actuators' gain, Kd as joint damping (an actuator's own kv stays)."""
    kv = f", plus the actuators' own damping of {e['kv']:g} N m s/rad" if e.get("kv") else ""
    return f"kp = {e['kp']:g} N m/rad, joint damping {e['kd']:g} N m s/rad{kv}"


def selection_text(env: str) -> str:
    sel = json.loads((HERE / "selection" / f"{env}.json").read_text())["candidates"]
    chosen = next(c["seed"] for c in sel if c.get("chosen"))
    skipped = [f"{c['seed']}: {c['skipped']}" for c in sel if c.get("skipped")]
    return f"seed {chosen}" + (f"; skipped {'; '.join(skipped)}" if skipped else "; the first candidate")


def values(env: str, inst: dict) -> dict:
    e = ENVS[env]
    rb = ROBOTS[e["robot"]]
    fa = inst["facts"]
    H = int(inst["horizon"])
    v = {
        "name": f"mujoco_playground_{snake(env)}", "env": env, "kind": e["kind"], "seed": inst["seed"],
        "robot_name": rb["name"], "robot_tax": rb["tax"], "menagerie": rb["menagerie"], "feet": rb["feet"],
        "joint_text": rb["joints"], "foot0": rb["feet"].split(", ")[0], "task": inst["text"], "task_toml": json.dumps(inst["text"])[1:-1],
        "kp": e["kp"], "kd": e["kd"], "sim_dt": e["sim_dt"], "dt": f"{e.get('dt', 0.02):g}",
        "substeps": round(e.get("dt", 0.02) / e["sim_dt"]), "xml": e["xml"], "gains": gains(e),
        "cameras": CAMERAS[e["robot"]], "n_rows": fa["reference_rows"], "selection": selection_text(env), "author": AUTHOR,
        "org": ORG, "allowed_hosts": ", ".join(json.dumps(h) for h in HOSTS), "resets": RESET_BUDGET,
        "episodes": RESET_BUDGET + 1,
    }
    if e["kind"] == "joystick":
        rough = "Rough" in env
        dt = e["dt"]
        T = H * dt
        ground = ("The ground is Playground's rough terrain: a 20 x 20 m heightfield (`hfield.png`, up to 5 cm high) "
                  "centred on the world origin, with nothing beyond its edge." if rough else "The ground is flat.")
        if e["start"] == "random":
            start = (f"The robot starts at Playground's `home` pose, its base moved to ({f(fa['start_xy_m'][0], 3)}, "
                     f"{f(fa['start_xy_m'][1], 3)}) m and turned to a yaw of {f(fa['start_yaw_deg'], 1)} deg, with a random "
                     "base velocity (Playground's reset).")
        else:
            start = "The robot starts standing still at Playground's `home` pose (this environment's reset does not move it)."
        quirk = (" One control step is 10 ms of simulated time: Playground's Barkour environment keeps Menagerie's 2 ms "
                 "timestep and takes 5 substeps." if dt != 0.02 else "")
        sched = (f"For {T:g} s ({H} control steps) it is given this command schedule, drawn by Playground's command "
                 f"process ({e['resample']}). A command is a velocity in the robot's own frame: vx forward, vy to the left "
                 "(the trunk's planar velocity), and the yaw rate:")
        extra, extra_std, gait_rule, gait_std = "", "", "", ""
        if e.get("pushes"):
            ks = inst["kicks"]
            fmax = max(0.5 * fa["torso_mass_kg"] * k["velocity_mps"] / (k["duration_steps"] * 0.02) for k in ks)
            extra = (f"\n\nThe torso is pushed {len(ks)} times (Playground's kicks): each push lasts "
                     f"{ks[0]['duration_steps']} control steps, a half-sine of horizontal force up to {fmax:.0f} N in a random "
                     "direction; `instance.json` (`kicks`) lists when and where, and `s.push_force(t)` gives the force of "
                     "control step t.")
            extra_std = (f"\n\nThe torso is pushed {len(ks)} times at moments you are not told (Playground's kicks: "
                         f"half-sine pushes of up to {fmax:.0f} N lasting {ks[0]['duration_steps'] * dt:g} s, in random "
                         "horizontal directions).")
        if e.get("gait"):
            g = inst["gait"]
            extra = extra_std = (f"\n\nThe feet must also follow a **{g['name']}** gait at {g['frequency_hz']:.2f} Hz with a "
                                 f"swing height of {g['foot_height_m']:.3f} m: foot i's target height at control step t is "
                                 "Playground's `gait.get_rz(wrap(phase0[i] + t * phase_dt), foot_height)` (a cubic Bezier up "
                                 f"over the first half of the phase, then down), with phase0 = {[round(x, 4) for x in g['phase0']]} "
                                 f"(feet {rb['feet']}) and phase_dt = {g['phase_dt']:.4f} rad.")
            gait_rule = (f"; and the mean, over the same steps, of the feet's RMS height error to their target heights is "
                         f"at most {GAIT_TOL} m")
            gait_std = f", and a mean RMS foot-height error to the gait's targets of at most {GAIT_TOL} m"
        v.update(
            episode_md=f"## The episode\n{start} {ground}{quirk}\n{sched}\n\n{schedule_table(inst, dt)}{extra}\n\n`s.commands` "
                       "holds the schedule per control step; `s.state()[\"command\"]` is the current one.",
            episode_md_std=f"## The episode\n{start} {ground}{quirk}\n{sched}\n\n{schedule_table(inst, dt)}{extra_std}\n\nThe "
                           "same schedule is `spec[\"command_schedule\"]`; every response's `meta[\"command_now\"]` is the "
                           "current command." + (" The gait is `spec[\"gait\"]`." if e.get("gait") else ""),
            success_md=(f"The episode lasts exactly {H} control steps: the trajectory must have T = {H} rows. Success iff\n"
                        f"1. the robot never meets Playground's termination rule for this environment: {e['fall']}; and\n"
                        f"2. in every command segment, over its control steps after the first {SETTLE} ({SETTLE * dt:g} s): the "
                        f"mean planar velocity error |v_xy - cmd_xy| is at most {LIN_TOL} m/s, with v the IMU's velocimeter "
                        f"(`local_linvel`, trunk frame), and the mean yaw-rate error |w_z - cmd_wz| at most {YAW_TOL} "
                        f"rad/s, with w the IMU's gyro{gait_rule}.\n\n`s.check()` reports `fell_at`, each segment's errors "
                        "and `success`."),
            rows_rule=f"T = {H} (the whole schedule)",
            state_cmd=", command", spec_cmd=", command_schedule" + (", gait" if e.get("gait") else ""),
            std_end=(f"after {H} control steps, the whole schedule (`spec[\"max_control_steps\"]`, counted by "
                     f"`meta[\"control_steps\"]`), when the robot meets its termination rule ({e['fall']}: a failure), "
                     "when you submit `done`, or when your time is up (before the end of the schedule, both are failures)."),
            std_success=(f"is judged on the whole schedule: no termination, and in every command segment, after its first "
                         f"{SETTLE} control steps, a mean |v_xy - cmd_xy| of at most {LIN_TOL} m/s (`imu_linvel`) and a mean "
                         f"|w_z - cmd_wz| of at most {YAW_TOL} rad/s (`imu_gyro`){gait_std}."),
            task_detail=(f"For {T:g} s the robot gets a joystick command schedule ({len(inst['commands'])} segments: "
                         "planar velocity and yaw rate in its own frame) and must track it without falling over."
                         + (" The ground is a 20 x 20 m heightfield with bumps up to 5 cm." if rough else "")
                         + (f" Its torso is pushed {len(inst['kicks'])} times." if e.get("pushes") else "")
                         + (f" Its feet must follow a {inst['gait']['name']} gait." if e.get("gait") else "")),
            grading_toml=f"velocity tracking over the whole {T:g} s schedule without a fall (two fresh-process replays).",
            difficulty=(f"Velocity tracking for {T:g} s: the agent has to make a 12-joint quadruped walk (a gait, not one "
                        "motion) and steer it through the schedule's changes of speed, direction and turning rate, and an "
                        f"open-loop trajectory of {H} steps only works if it is computed against the simulator. "
                        f"{e['difficulty']}"
                        + (" On the heightfield the feet land at unpredictable heights: Playground's own Go1 policy, which "
                           "made the reference, falls or loses track on some of the candidate seeds (select_instances.py "
                           "skips them)." if rough else "")),
            reference=(f"{e['reference']}, its targets recorded (`scripts/mujoco-playground/oracle.py`): worst segment errors "
                       f"{fa['reference_worst_lin_err']:.3f} m/s and {fa['reference_worst_yaw_err']:.3f} rad/s"
                       + (f", foot height {fa['reference_worst_gait_err']:.3f} m" if e.get("gait") else "") + "."),
            check_short=(f"Oracle: success, worst segment errors {fa['reference_worst_lin_err']:.3f} m/s and "
                         f"{fa['reference_worst_yaw_err']:.3f} rad/s."),
            oracle_end=f"after the {H} steps of the schedule, with success",
            instance_extra=f" and Playground's command process over the {H} steps" + (" (and its pushes)" if e.get("pushes") else ""),
            expert_hours="3.0", expert_hours_std="4.0",
        )
    elif e["kind"] == "getup":
        name = rb["short"]
        v.update(
            episode_md=(f"## The episode\nPlayground's reset dropped the robot from {e['drop']}, then let it settle for "
                        f"0.5 s with its joints held: at t = 0 it lies with its trunk tilted {f(fa['start_tilt_deg'], 1)} deg "
                        f"from upright. You have {H} control steps ({H * 0.02:g} s)."),
            episode_md_std=(f"## The episode\nThe robot was dropped from {e['drop']} and settled for 0.5 s with its joints "
                            f"held: at the start it lies with its trunk tilted {f(fa['start_tilt_deg'], 1)} deg from upright. "
                            f"You have {H} control steps ({H * 0.02:g} s)."),
            success_md=(f"Success iff the trajectory (at most {H} rows) ends with {HOLD} control steps in a row (0.5 s) after "
                        f"each of which the trunk is upright, tilted at most {TILT} deg (the angle between the IMU frame's z "
                        f"axis and world z), and the IMU is at least {e['min_h']} m above the floor (the {name} stands at "
                        f"{e['stand_h']} m; lying down is below {e['lie_h']} m). End the trajectory once that holds. "
                        "`s.check()` reports the last tilt, height and `success`."),
            rows_rule=f"1 <= T <= {H}",
            state_cmd="", spec_cmd="",
            std_end=(f"the moment the robot has been upright for {HOLD} control steps in a row (success), after {H} control "
                     "steps (`spec[\"max_control_steps\"]`, counted by `meta[\"control_steps\"]`), when you submit `done`, or "
                     "when your time is up."),
            std_success=(f"is {HOLD} control steps in a row with the trunk within {TILT} deg of upright and the IMU at least "
                         f"{e['min_h']} m above the floor (the {name} stands at {e['stand_h']} m), judged after every control "
                         "step; when the episode ends otherwise, it is judged on its last control steps."),
            task_detail=(f"It starts lying with its trunk tilted {f(fa['start_tilt_deg'], 1)} deg (Playground's random drop, "
                         f"then a 0.5 s settle) and has {H * 0.02:g} s to stand upright at its standing height."),
            grading_toml="an upright stance held for the trajectory's last 0.5 s (two fresh-process replays).",
            difficulty=(f"Recovery from a fall: the robot lies on its side or back and has to turn itself over with its legs "
                        f"and then stand up within {H * 0.02:g} s, with the trunk, thighs and calves all in contact with the "
                        "floor (full collisions). The motion is whole-body and contact-rich, and a turn that fails leaves "
                        f"it on its back. {e['difficulty']}"),
            reference=(f"{e['reference']} (`scripts/mujoco-playground/oracle.py`): upright after {fa['reference_rows']} control "
                       f"steps, IMU at {fa['reference_imu_height']:.3f} m."),
            check_short=f"Oracle: success after {fa['reference_rows']} control steps.",
            oracle_end=f"with success after {fa['reference_rows']} control steps",
            instance_extra=" (a drop; the 0.5 s settle runs in the task's own MuJoCo)",
            expert_hours="2.0", expert_hours_std="3.0",
        )
    else:
        pose = (f"the trunk's forward axis (the IMU frame's x axis) within {POSE_TOL} deg of straight {e['dir']}, the IMU "
                f"at least {e['min_h']} m above the floor, and the {e['air']} feet off the ground")
        pose_is = (f"the trunk's forward axis (the IMU frame's x axis) is within {POSE_TOL} deg of straight {e['dir']}, the "
                   f"IMU is at least {e['min_h']} m above the floor and the {e['air']} feet are off the ground")
        term = ("the trunk's up axis below -0.25 (z component of the IMU frame's z axis), or any part of a front leg other "
                "than its foot (thigh, calf, hip) touching the floor"
                + (" (Playground's rule as its code reads it), or the same for a hind leg (the list its Footstand sets "
                   "up but never reads; without it, sitting on a hind hip would count)" if e.get("hind") else ""))
        v.update(
            episode_md=(f"## The episode\nThe robot starts at Playground's `home` pose, its base moved to "
                        f"({f(fa['start_xy_m'][0], 3)}, {f(fa['start_xy_m'][1], 3)}) m, turned to a yaw of "
                        f"{f(fa['start_yaw_deg'], 1)} deg, with a random base velocity (Playground's reset). You have {H} "
                        f"control steps ({H * 0.02:g} s)."),
            episode_md_std=(f"## The episode\nThe robot starts standing at Playground's `home` pose with a random base "
                            f"velocity (Playground's reset). You have {H} control steps ({H * 0.02:g} s)."),
            success_md=(f"Success iff the trajectory (at most {H} rows) ends with {POSE_HOLD} control steps in a row (2 s) "
                        f"after each of which {pose_is}; and no control step before its end meets Playground's termination "
                        f"rule: {term}. End the trajectory once the hold is complete. `s.check()` reports `fell_at`, the "
                        "last pose angle and height, and `success`."),
            rows_rule=f"1 <= T <= {H}",
            state_cmd="", spec_cmd="",
            std_end=(f"the moment the pose has been held for {POSE_HOLD} control steps in a row (success), when the robot "
                     f"meets the termination rule ({term}: a failure), after {H} control steps (`spec[\"max_control_steps\"]`), "
                     "when you submit `done`, or when your time is up."),
            std_success=(f"is {POSE_HOLD} control steps in a row (2 s) with {pose}, without a termination before; judged "
                         "after every control step."),
            task_detail=(f"From standing, it has {H * 0.02:g} s to get into a {e['pose']} on its {e['on']} legs and hold it "
                         f"for 2 s (Playground's {e['pose']} reward aims at the IMU {e['z_des']} m high)."),
            grading_toml=f"a {e['pose']} held for the trajectory's last 2 s, without a termination (two fresh-process replays).",
            difficulty=(f"Dynamic balance on two legs: the robot has to throw its weight onto its {e['on']} legs, lift the "
                        f"other pair and then balance an inverted, top-heavy body on two small feet with 35 N m/rad position "
                        "drives, correcting continuously; a front leg touching the floor or a tip-over ends it. Playground's "
                        f"{e['pose']} is trained with 100 M steps of PPO."),
            reference=(f"A policy trained here on Playground's Go1{e['pose'].capitalize()} reward (PPO on the CPU, "
                       f"`scripts/mujoco-playground/train/`, not in the image){e.get('train_note', '')}, run closed loop with "
                       "Playground's action semantics (targets accumulate) until the hold completes "
                       "(`scripts/mujoco-playground/oracle.py`): "
                       f"{fa['reference_rows']} control steps, pose angle {fa['reference_pose_angle_deg']:.1f} deg and IMU at "
                       f"{fa['reference_imu_height']:.3f} m at the end."),
            check_short=f"Oracle: success after {fa['reference_rows']} control steps.",
            oracle_end=f"with success after {fa['reference_rows']} control steps",
            instance_extra=" (xy, yaw and base velocity)",
            expert_hours="3.0", expert_hours_std="4.0",
        )
    return v


# README Change Log of the standard tasks (PROTOCOL §2.8: published tasks fixed in place; results before a change are not
# retested), oldest first.
STD_CHANGES = [
    "2026-10-10 (review 0067): a `final.json` that is missing, unreadable or was never finalized by the collect hook is "
    "graded `infra_error = 1` (no verdict on the agent); before, a missing one was a plain 0 and an unfinalized one was "
    "graded as it stood. The collect hook writes `final.json` atomically. A request field of the wrong type (`dt` or "
    "`seconds` null, `cameras` not a list of names, a `note` that is not a string) is answered 400 before any physics "
    "instead of ending the episode with a 500. `meta[\"time_left_s\"]` counts from the agent's first call, not from the "
    "service's start.",
]
STD_CHANGES_BARKOUR = [
    "2026-10-10 (review 0067): `/spec` gives the control period of the `joint_position` action as 0.01 s; its text said "
    "\"one per control step (1/50 s)\", contradicting `control_hz = 100`, the `dt` check and the instruction.",
]


STD_CHANGES_R2 = [
    "2026-10-10 (review round 2, board 0067): the client only (`environment/rcb_client.py`). `Robot()` waits up to 3600 s for the service (was 600 s) and prints its progress to stderr once a minute, so the first `Robot()` outlasts the simulator's start (no effect on this benchmark, whose service is up within a minute); `cameras=\"name\"` (a string) is one camera, no longer its characters. The service, the collect hook, the grader, the scene and the pass rule are unchanged.",
    "2026-10-10 (review round 3, board 0067): the shared service layer and the client only "
    "(`environment/sim/rcb_limited.py`, `environment/rcb_client.py`). A camera named more than once in `cameras` "
    "is rendered and returned once (N copies of one name made the service build N x N images within the frame "
    "budget, which could exhaust its memory). A service that has given up on the episode (it could not start it, "
    "or could not resume it after its crashes) answers every request with 409 and the reason, and `Robot()` / "
    "`wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out their timeout (up to "
    "an hour). The adapter, the collect hook, the grader, the scene and the pass rule are unchanged.",
]
STD_CHANGES_RESETS = [
    f"2026-10-14 (owner decision C1, board 0113): {RESET_BUDGET} resets (PROTOCOL §4.5). The service "
    "(`environment/sim/server.py`) gained the optional reset capability: `RCB_RESET_BUDGET` (the compose file's default "
    f"{RESET_BUDGET}; 0 restores the old single episode), `POST /reset` abandons the running or ended episode and starts a "
    "new one from the same frozen start (no physics), refused (409) after a success, once the agent's time is up and once "
    "the budget is spent; only the last episode is graded (`trajectory.npz` holds its rows, replayed twice from the "
    "frozen start as before); `/status` and every `meta` add `episode`, `resets_left` and `control_steps_total`; "
    "`final.json` and `reward.json` add `resets`, `reset_budget` and `episodes`. A crash resumes the current episode "
    "(the journal is replayed with the committed resets). The instruction's rules, the client example (`POST /reset` "
    "through `Robot._post`) and this README say so. The scene, the instance, the success check and the grader's pass "
    "rule are unchanged; results recorded before this change ran with one episode and are reported separately.",
]


def make(env: str, out: Path) -> tuple[Path, ...]:
    inst_path = HERE / "instances" / f"{env}.json"
    inst = json.loads(inst_path.read_text())
    v = values(env, inst)
    v["change_log_std"] = "\n".join(f"- {c}" for c in STD_CHANGES + (STD_CHANGES_BARKOUR if "Barkour" in env else []) + STD_CHANGES_R2
                                    + STD_CHANGES_RESETS)
    oracle = HERE / "oracles" / f"{env}.npy"

    p = out / f"{v['name']}-privileged"
    reset_dir(p)
    put(p / "task.toml", render("task.toml", {**v, "agent_timeout": CUTOFF["privileged"]}))
    put(p / "instruction.md", render("instruction.md", v))
    put(p / "README.md", render("README.md", v))
    put(p / "environment/Dockerfile", PRIV_ENV_DOCKERFILE)
    put(p / "environment/instance.json", src=inst_path)
    put(p / "environment/rcb_quadruped.py", src=SHARED / "rcb_quadruped.py")
    put(p / "tests/Dockerfile", PRIV_TESTS_DOCKERFILE)
    put(p / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(p / "tests/grade.py", src=SHARED / "grade.py")
    put(p / "tests/rcb_quadruped.py", src=SHARED / "rcb_quadruped.py")
    put(p / "tests/instance.json", src=inst_path)
    put(p / "solution/solve.sh", src=SHARED / "solve_privileged.sh", mode=0o755)
    put(p / "solution/oracle_replay.py", src=SHARED / "oracle_privileged.py")
    put(p / "solution/oracle.npy", src=oracle)

    s = out / f"{v['name']}-standard"
    reset_dir(s)
    put(s / "task.toml", render("standard/task.toml", {**v, "agent_timeout": CUTOFF["standard"]}))
    put(s / "instruction.md", render("standard/instruction.md", v))
    put(s / "README.md", render("standard/README.md", v))
    put(s / "environment/Dockerfile", STD_ENV_DOCKERFILE)
    put(s / "environment/docker-compose.yaml", STD_COMPOSE)
    put(s / "environment/client-requirements.txt", src=LAYER / _ENV.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip())
    put(s / "environment/rcb_client.py", src=LAYER / "rcb_client.py")
    put(s / "environment/rcb1.py", src=LAYER / "rcb1.py")
    for name in ("rcb_limited.py", "rcb1.py"):
        put(s / "environment/sim" / name, src=LAYER / name)
    put(s / "environment/sim/run.sh", src=LAYER / "run.sh", mode=0o755)
    put(s / "environment/sim/server.py", src=SHARED / "standard/server.py")
    put(s / "environment/sim/finalize.sh", src=SHARED / "standard/finalize.sh", mode=0o755)
    put(s / "environment/sim/rcb_quadruped.py", src=SHARED / "rcb_quadruped.py")
    put(s / "environment/sim/instance.json", src=inst_path)
    put(s / "tests/Dockerfile", STD_TESTS_DOCKERFILE)
    put(s / "tests/test.sh", src=SHARED / "standard/test.sh", mode=0o755)
    put(s / "tests/grade.py", src=SHARED / "standard/grade.py")
    put(s / "solution/solve.sh", src=SHARED / "standard/solve.sh", mode=0o755)
    put(s / "solution/oracle_replay.py", src=SHARED / "standard/oracle_replay.py")
    put(s / "solution/oracle.npy", src=oracle)
    normalize(p)
    normalize(s)
    if env not in REALTIME:
        return p, s

    r = out / f"{v['name']}-standard-realtime"
    reset_dir(r)
    w = rt_values(env, v)
    put(r / "task.toml", render("realtime/task.toml", w))
    put(r / "instruction.md", render("realtime/instruction.md", w))
    put(r / "README.md", render("realtime/README.md", w))
    put(r / "environment/Dockerfile", RT_ENV_DOCKERFILE)
    put(r / "environment/docker-compose.yaml", rt_compose(env))
    put(r / "environment/client-requirements.txt", src=LAYER / _ENV.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip())
    put(r / "environment/rcb_client.py", src=RT / "rcb_client.py")
    put(r / "environment/rcb1.py", src=LAYER / "rcb1.py")
    for name in ("rcb_realtime.py", "rcb_service.py", "server.py"):
        put(r / "environment/sim" / name, src=RT / name)
    put(r / "environment/sim/rcb1.py", src=LAYER / "rcb1.py")
    put(r / "environment/sim/rcb_quadruped.py", src=SHARED / "rcb_quadruped.py")
    put(r / "environment/sim/instance.json", src=inst_path)
    put(r / "tests/Dockerfile", STD_TESTS_DOCKERFILE)
    put(r / "tests/test.sh", src=SHARED / "standard/test.sh", mode=0o755)
    put(r / "tests/grade.py", src=RT / "grade.py")
    put(r / "solution/solve.sh", src=RT / "solve.sh", mode=0o755)
    put(r / "solution/oracle_plan.py", src=RT / "oracle_plan.py")
    put(r / "solution/oracle.npy", src=oracle)
    normalize(r)
    return p, s, r


def render_all(out: Path) -> list[str]:
    done = []
    for inst in sorted((HERE / "instances").glob("*.json")):
        done += [d.name for d in make(inst.stem, out)]
    return done


def ours(d: Path) -> bool:
    return d.is_dir() and d.name.startswith(PREFIXES)


def check() -> int:
    """tasks/ must be exactly what render_all writes (contents and modes), with no other quadruped task directory."""
    with tempfile.TemporaryDirectory() as tmp:
        names = set(render_all(Path(tmp)))
        have = {d.name for d in TASKS_DIR.iterdir() if ours(d)}
        bad = sorted(have ^ names)
        for name in sorted(names & have):
            stack = [filecmp.dircmp(TASKS_DIR / name, Path(tmp) / name, ignore=["__pycache__"])]
            while stack:
                c = stack.pop()
                diff = filecmp.cmpfiles(c.left, c.right, c.common_files, shallow=False)[1]
                modes = [x for x in c.common_files if (Path(c.left) / x).stat().st_mode != (Path(c.right) / x).stat().st_mode]
                if c.left_only or c.right_only or c.funny_files or diff or modes:
                    bad.append(name)
                    break
                stack += list(c.subdirs.values())
    for name in sorted(set(bad)):
        print(f"FAIL tasks/{name}: differs from scripts/mujoco-playground/generate.py (re-run it)")
    if not bad:
        print(f"{len(names)} task directories match")
    return 1 if bad else 0


def main(args: list[str]) -> int:
    if args == ["--check"]:
        return check()
    names = render_all(TASKS_DIR)
    for d in sorted(TASKS_DIR.iterdir()):
        if ours(d) and d.name not in names:
            shutil.rmtree(d)
            print(f"removed stale {d.relative_to(ROOT)}")
    print(f"generated {len(names)} task directories")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
