# YAMLab notes (study of ARISE-Initiative/yamlab @ ec0455d, 2026-06-28 "init")

Local clone: `yamlab_port/yamlab/` (85 MB, single commit). License: **MIT** (c) 2026 Tianyuan Dai, so porting tasks on top is fine; keep the notice.

## What it is

A bimanual **YAM** workstation simulation framework for teleop data collection (JoyLo leader arms), MimicGen data generation, LeRobot v2 dataset export and parallel policy evaluation. Ships 2 tasks: PutPotOnCooktop (bimanual pick-place, 2 stages) and HangMugOnTree (pick, handover, hang; 3 stages). There is **no scripted oracle / motion planner** in the repo: demos come from teleop and MimicGen.

## Simulator backend

- **Isaac Sim 5.1.0 + Isaac Lab @ f4aa17f (2.3.2)**, PhysX 5, Python 3.11, torch 2.7.0 cu128. Same Isaac generation as our RoboLab / BEHAVIOR images.
- Physics 120 Hz (dt 1/120), decimation 4, so **30 Hz control**; `min_position_iteration_count 16`; episode 180 s.
- Modes (`configs/defaults.yaml`): teleop/replay `cpu x1`, mimicgen `cpu x4`, evaluation `cuda x64`. The **device is a per-task config knob** (a task YAML may set its own `modes:`). This matters: PhysX deformables (FEM) run only on the GPU pipeline.

## Robot and embodiment (must stay unchanged)

- Two **YAM** arms (I2RT), each 6-DoF (`joint1..6`) plus a parallel-jaw gripper (`left_finger`, `right_finger`, prismatic; open -0.0475, closed 0.0, so about 95 mm total stroke). USD `robot/yam/arm/yam.usd` (binary USDC).
- Bases (world frame, metres): left (0.2525, +0.305, 0.76), right (0.2525, -0.305, 0.76), both identity quaternion: **both face +X, side by side** (unlike ALOHA's facing arms). Arms have `disable_gravity=True`, self-collision off, contact sensors on.
- Measured by the task agents (2026-10-12): the table collider (`table_surface`) top is z **0.7500** (objects rest there; yam.yaml's 0.7517 is the calibration value), and its extent is x 0.3025..0.8975, y -0.65..+0.65 (wider than yam.yaml's corners). The YAM gripper squeezes only ~9-14 N, and its finger collision hulls form a V-shaped fork with inner contact only near the tips. YAMLab mode="replay" drops the success/time_out terminations, so oracles must run in mode="evaluation". Enabling cameras perturbs PhysX.
- Table top z = **0.7517** (yam.yaml); tabletop x 0.2995..1.0015 (70 cm deep), y -0.55..+0.55 (110 cm wide). Workstation USD = table + gate frame (kinematic collider).
- Controller: implicit PD joint-position actuators, `high_pd` gains (shoulder/elbow kp 800 kd 50, wrist kp 30 kd 5, gripper kp 2000 kd 100); effort limits 28 / 10 / 10 / 100 N(m).
- **Action = 14-D absolute joint-position targets** `[left_arm(6), left_gripper(1), right_arm(6), right_gripper(1)]` (`robot/yam/action.py`). The gripper command drives `left_finger`; `step()` mirrors it onto `right_finger`. Optional grasp clamp (`--enable_gripper_clamp`): once a grasp is detected, the gripper target is clamped to actual + 7.5 mm so it does not crush/eject the object.
- Cameras: `top` (world-fixed, 640x480 pinhole), `left_wrist`, `right_wrist` (on link_6). TiledCamera, RGB.
- Grasp detection: per finger, contact force on the target object >= 0.1 N and contact on the finger pad. Contact sensors only exist for objects listed in the task's `grasp_detect` map, and they need **rigid** target objects.
- IK: no IK in the env. MimicGen uses Isaac Lab's differential IK; `utils/jparse_ik.py` has a J-PARSE pseudo-inverse IK step (single env). An oracle therefore = Cartesian waypoints -> (iterated) differential IK on the arm Jacobian -> 14-D joint targets. Reach per arm is about 0.6 m (vendor figure; to be measured in sim by each task agent).

## How a task is defined (README 6.2)

1. `configs/tasks/<task>.yaml`: `env_names`, `objects:` (mass, spawn randomization), `grasp_detect`, `kwargs`, `success`, `friction`, `modes` (device / num_envs per mode), `mimic_signals`, `pose_schedule`. Validated by a pydantic schema (`configs/schema.py`): unknown keys are rejected.
2. `envs/tasks/<task>_manager_cfg.py`: scene cfg subclassing `YamBimanualSceneCfg` adding `RigidObjectCfg` / `ArticulationCfg` assets; `Events` (reset), `Rewards`, `Terminations` cfgs; `<Task>ManagerEnvCfg(YamBimanualEnvCfg)`; `CONTACT_OBJECT_NAMES`.
3. `envs/tasks/<task>_manager.py`: `<Task>Manager(YamBimanualEnv)` with `get_current_task_info()` and `reset_success_check()`, a `make_<task>_env` factory (`make_task_env(cfg_cls, env_cls, **kw)`) and `gym.register(...)`.
4. Register the module in `envs/tasks/__init__.py`; map gym id -> robot in `envs/robot_registry.py`.
5. Assets: USD instance dirs with `asset_size.json` (`scripts/precompute_asset_sizes.py`), passed as `--asset NAME=PATH`. Our STL parts must be converted to USD (Isaac Lab `MeshConverter` / `sim_utils.MeshCuboidCfg` etc.; convex decomposition for dynamic concave parts; static parts can use triangle-mesh colliders).

Success logic is plain Python on the env (helpers in `utils/task_logic.py`: pick, place-on-top, hang, below-table), latched per stage over N consecutive control steps; termination terms `time_out`, `task_success`, `*_below_table`.

## Deformables support

- **YAMLab itself: none.** No rope, cable, cloth or soft body anywhere in the repo (grep for deform/rope/cable/cloth/particle/soft: 0 hits). Both tasks are rigid.
- **Isaac Lab 2.3 underneath offers:**
  - `DeformableObject` / `DeformableObjectCfg` + `sim_utils.MeshCuboidCfg(deformable_props=...)` or a USD mesh: PhysX **FEM volumetric soft bodies**, **GPU pipeline only** (sim device cuda), kinematic targets per vertex, self-collision optional. A thin 8 mm x 1 m rope as a FEM volume needs many tets and is known to be fragile (thin-feature tunnelling, jitter); grasping it with a parallel gripper relies on friction against FEM, with no contact-sensor support for grasp detection.
  - **Articulations / rigid-body chains**: a rope or cable as a chain of capsule rigid bodies joined by spherical/D6 joints with stiffness and damping. Fully supported by PhysX on CPU and GPU, collisions between non-adjacent links work (knots and crossings are representable), link poses are directly readable for a goal check. This is what our old fiber_bundling cable already was ("articulated_cable").
  - PhysX particle cloth / PBD exists in Isaac Sim but Isaac Lab has no managed asset for it. Not needed for these five families.
- **Conclusion:** rope and cable tasks are portable as **capsule chains** (rigid links + compliant joints), not as FEM. Knot topology must come from the start pose (we write the old centreline into link poses) plus link-link collision; a knot's start state must be settled without links interpenetrating.

## How examples are scripted

Entry scripts build an `argparse` parser, add `AppLauncher.add_app_launcher_args`, launch the app, then import yamlab and call `create_task_environment(task, mode=..., assets=..., ...)` (a `gym.make` wrapper). They then loop `env.step(action14)`. `scripts/benchmark_eval_throughput.py` is the cleanest template for an oracle runner (it has a swappable `compute_actions`). Replay (`scripts/replay_data.py`) re-simulates recorded states and can re-render cameras to a LeRobot dataset.

## Headless

`--headless` (AppLauncher) and `--enable_cameras` when camera observations are wanted (needed for frames/video). Isaac Sim needs an RTX GPU with Vulkan; CPU-only machines cannot run it.

## Where it can run (our hosts)

- **RTX rendering status (2026-10-12):** physics-only YAMLab runs work on vast (PutPotOnCooktop with cameras stripped, CPU PhysX, about 73 control steps/s). `--enable_cameras` segfaults on vast in `rtx.scenedb` at RTX startup (Vulkan sees the GPU; multiGpu off, driver check off and extra X11 libs did not help). Video path: replay saved oracle actions on ws/ws3 in an Isaac 5.1 container (short jobs; hosts are loaded).
- **ws render path: WORKING (2026-10-12 07:47).**
  - Container: `ghcr.io/mll-lab-nu/eai-robolab:0.1.2` (Isaac Sim 5.1, Isaac Lab 2.3.2.post1 pip; YAMLab runs on it unchanged). yamlab's import deps are in a `--no-deps` overlay at `/data/qineng/04_code_robot_challenge/2026-10-12_yamlab/pylib` (datasets 3.6, pyarrow 18.1, lerobot v2.0, ...; numpy stays 1.26).
  - Wrapper: `~/01_projects/04_code_robot_challenge/tmp/2026-10-12_yamlab/run_in_container.sh "<cmd>"`, with `YL_TIMEOUT` seconds enforced INSIDE the container, 24 GB RAM, 8 CPUs, label `yamlab_port=1`. Mounts: tmp dir -> /work, data dir -> /data, `PYTHONPATH=/data/pylib:/work/yamlab`.
  - Timing: the first Kit start compiled shaders for ~5 min on loaded ws; later starts are faster (Kit caches in /data/.../cache).
  - Smoke: PutPotOnCooktop-v0 with top + wrist cameras, 640x480, CPU physics, 40 steps in 12 s. Frames: `setup/render_smoke/`.
  - To render a family: copy its yamlab copy to `/work/runs/<family>/yamlab` (+ assets, actions) and run its replay script with `--enable_cameras` and `PYTHONPATH=/data/pylib:/work/runs/<family>/yamlab`.
- **vast** (RTX PRO 6000 Max-Q 96 GB, Vulkan ICD present, `NVIDIA_DRIVER_CAPABILITIES=all`, no docker): native install in `/workspace/yamlab_port/venv` (uv venv, Python 3.11, torch 2.7.0 cu128, isaacsim 5.1.0, Isaac Lab f4aa17f, yamlab -e, LeRobot v2.0) via `setup/vast_install.sh`. GPU shared with gpusearch (100 % util already; about 66 GB VRAM free on 2026-10-12): Isaac must use little VRAM and nice 19.
- **ws / ws2 / ws3** (RTX 4090 24 GB, docker): fallback. Load ~50 on 32 threads and GPUs busy on 2026-10-12. ws has `eai-robolab:0.1.2` (Isaac Lab 2.3.2 + Isaac Sim 5.1) which could host YAMLab with a pip overlay.
- **NU Quest**: CPU partitions plus `gengpu` A100/H100 nodes (`-A p33180 -p gengpu --gres=gpu:a100:1` or `h100`, single GPU, modest time limits; Singularity/Apptainer with `--nv`, bind node-local scratch as /tmp or NVRTC dies). Caveat: A100/H100 have no RT cores, and NVIDIA does not support Isaac Sim RTX rendering on them, so they are a physics-only (PhysX GPU/CPU) path and an unlikely render path. Try first if ws/ws3 cannot render. CPU nodes: offline geometry (coacd, clearance analysis, numpy IK planning).
- **Laptop: off-limits for compute.**
