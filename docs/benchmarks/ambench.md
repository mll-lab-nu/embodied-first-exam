# AM-Bench

[AM-Bench](https://github.com/ambench/ambench) @ 60bf5b7 (Apache-2.0) on Isaac Lab @ f4aa17f / Isaac Sim 5.1.0: aerial
manipulation. The robot is AM-Bench's FA-Hexa, a fully actuated hexarotor (six tilted rotors: it can hold any attitude while
hovering) carrying a 4-joint arm (three pitch joints and a roll joint) with a two-finger gripper, driven by AM-Bench's own
whole-body controller (floating-base inverse kinematics with Pyroki, a PID for the airframe). `simulator = "ambench"`,
`robot = "ambench-fahexa"`.

**A first set (placeholder), privileged mode only.** Three families, three of AM-Bench's twelve tasks, one frozen instance
each:

| Family | AM-Bench environment | Task | Episode | Oracle: success at control step |
|---|---|---|---|---|
| `press_button_fahexa` | `PressButton-Am-FAHexa-Abs-PID-Direct-v0` | press a spring-loaded button on a (tilted) wall by ≥ 4 mm | 20 s | 1027 (end state `fcd4de9b…`) |
| `push_slider_fahexa` | `PushSlider-Am-FAHexa-Abs-PID-Direct-v0` | push a knob 0.95 m along a rail on a wall | 26 s | 1353 (end state `01a85d35…`) |
| `rotate_valve_fahexa` | `RotateValve-Am-FAHexa-Abs-PID-Direct-v0` | turn a valve wheel on a wall ≥ 170° clockwise | 20 s | 1002 (end state `1b976104…`) |

Task directories: `ambench-<task>-fahexa-i00-privileged`. **TossBall** (`TossBall-Am-FAHexa-Abs-PID-Direct-v0`: deliver the
held ball into a bin on the ground) was prepared too (`scripts/ambench/descr/toss_ball.json`) but has no reference solution
yet: AM-Bench's scripted expert, whose release timing and offsets it samples from torch's RNG, did not succeed on the seed-0
instance in 15 runs (with the cameras on: its own draw, then torch seeds 1-8; camera-free: its own draw, then seeds 1-5; every
one ran into the 10 s time-out), so it is left out of this set until that is understood. The standard twins
(`eai-standard/2.2`), more instances and the other tasks (doors, peg-in-hole, pick-and-place variants, perching) and robot
profiles (quadrotor, omnidirectional, the fully actuated hexa with a delta arm) are planned (Standard mode, below).

## Tasks and generator
- `python3 scripts/ambench/mk_tasks.py` writes every AM-Bench task dir from `scripts/ambench/` alone: `instances.json`
  (`modes`, and per task the frozen instance with its hashes and provenance), `frozen/<task>-iNN/` (`instance.json`,
  `oracle_actions.npy`), `descr/<task>.json` (what the task asks and exactly what its check tests, written from the
  task's code), `shared/rcb_ambench.py` (the tooling) and `template/privileged/`. Re-running it leaves `git diff tasks/`
  empty; `--check` only compares. `instances.json`'s `modes` is `["privileged"]` for now.
- Freezing (`scripts/ambench/freeze.py`, on a GPU host with the image): the instance is AM-Bench's seeded reset with seed 0
  (`cfg.seed = 0`, `env.reset(seed=0)`); AM-Bench draws the task's variation from it (where the wall, the button, the
  slider, the valve or the bin is; the button's size). `instance.json` holds the environment id, the seed and `initial_sha`
  (the sha256 of every articulation's and rigid object's root state, joint positions and velocities after the reset); every
  replay rebuilds the start and checks it (`instance_matches`).

## Success (AM-Bench's own)
Each task's `_get_success` (its `terminated` signal), unchanged except RotateValve's angle (below), evaluated after every control step; the episode ends at
the first step where it holds, or with AM-Bench's time-out (`episode_length_buf >= max_episode_length - 1`: control step
2399 / 3119 / 2399). No hold time is required. The privileged instructions give every threshold and the full scene:
PressButton `PlungerSlideJoint >= 0.004 m`; PushSlider `SliderJoint >= 0.45 m` (from -0.5 m); RotateValve
`base_to_shaft >= 17π/18` rad, on the joint's unwrapped angle. (TossBall's check, for when it joins: the ball ≥ 0.12 m from the tool tip, its centre inside
the bin's nominal 0.40 × 0.30 × 0.17 m box, and the airframe at x ≤ bin x − 0.7 m, at the same step; the third condition
already holds at the start, so it does not force a throw.)

**RotateValve: the unwrapped angle (2026-10-14, board 0110, before the first release).** `base_to_shaft` has no limits,
and omni.physx (107.3, Isaac Sim 5.1) creates an articulation's revolute joint without limits as a wrapped joint, whose
position PhysX reports in [-π, π] (omni.physx's own tests: "the joint without limits will be created as regular WRAPPED
joint"). AM-Bench's check `joint_pos >= 17π/18` on that value also passes a counter-clockwise turn of 190° (reported as
+170°), while the task (and its instruction) is a clockwise turn of 170°. The tooling, the same file in the agent's
environment and in the grader, replaces RotateValve's `_get_success` with the same comparison on the unwrapped angle: the
sum of the joint's per-step changes since the reset, each wrapped into [-π, π) (the joint's velocity limit, 5 rad/s, moves it
at most 0.042 rad per 1/120 s step, so the sum is exact). Physics, states, `initial_sha` and the end-state hashes are
unchanged; for a clockwise turn below π the two readings agree, so the recorded oracle ends at the same step. The angle is
`s.valve_angle()` in the tooling. This is a correction of a wrap-around, not a stricter rule: the upstream threshold,
direction and timing stay as they are.

## Oracle (PROTOCOL §2.7)
`oracle = "full"`, 3/3. The reference solution of an instance is AM-Bench's scripted expert for the task
(`policies/scripted/<task>.py`, `inject_noise=False`), run in closed loop on the frozen instance by `freeze.py` (in a
camera-free Session, as the grader) and recorded as the rows the tooling executed, followed by 2 s of holding its last
command (`solution/oracle_actions.npy`); `solution/oracle.py` replays them through the agent's own tooling. The expert reads
the simulator's state between steps, so its own live episode is not the reference: two fresh-process replays with the
grader's CLI must both succeed and end in the same state before an instance is frozen. The hold is there because a replay
can lag the live episode (in the first, camera-on recording RotateValve's expert succeeded live at its 993rd row while a
replay of exactly those rows ended them short of 170°); rows after a replay's own success never run.

The experts are not in the image: the Dockerfile copies AM-Bench without `policies/scripted/`, `ambench_learn`, its scripts,
documentation and git history, blanks the task registrations' `scripted_policy_entry_point`, and fails if anything left
names them. `freeze.py` mounts the expert read-only from a checkout outside the image. AM-Bench is public on GitHub and
not on PyPI; the agent's egress is the model APIs and the package registries (`network_mode = "allowlist"`), so the
experts cannot be fetched during a trial.

## Tooling (`rcb_ambench.py`)
`Session` (frozen instance, reset, step, `hold_action`, status, `actions`, replay, `save_trajectory`), the privileged state
(`state()`: AM-Bench's own observation; `objects()`: every task object and fixture with pose, velocities and joint state;
`proprio()`: base and end-effector poses and velocities, gripper width, arm joints, the current command), the two onboard
cameras on request (`Session(cameras=True)`: `render_frame`, `start_video` / `stop_video`) and `env` (the Isaac Lab
environment itself). No motion primitives: reaching, pressing, pushing and turning are the agent's.
- **Actions**: AM-Bench's absolute end-effector pose action of the `Abs-PID` profile, 8 per control step: the ee_link
  target position (x, y, z, m, relative to the environment's origin), its orientation (qw, qx, qy, qz in AM-Bench's command
  frame of the end effector; `hold_action()` and `proprio()["command"]` give the current target in that convention) and the
  gripper (-1 closed .. +1 open). The tooling clips only the gripper to [-1, 1] and refuses a zero quaternion; it does not
  normalise the quaternion (that would change the float32 bits AM-Bench receives). 120 Hz control, one physics step of
  1/120 s per action.
- **Cameras off by default.** A default Session does not build the robot profile's onboard cameras (`ee_camera`,
  `base_camera`; `cfg.robot_profile.*_camera = None`) and launches Isaac Sim without rendering; the task, its physics and
  its success check are AM-Bench's. Determinism, below, is why.
- **End state.** Isaac Lab resets an environment whose episode ended inside that very step (`DirectRLEnv.step` →
  `_reset_idx`), so after the last step the scene is already the next start. The tooling hashes the state just before that
  reset and reports it as the episode's `state_sha`.
- `reset()` runs in `torch.inference_mode`, as `step()` does (after a step Isaac Lab's buffers are inference tensors, and a
  reset outside that mode failed). The CLI and the recorder exit at once on an error: Isaac Sim can otherwise hang at exit.
- CLI: `replay` (one fresh-process replay, no cameras: the grader's), `film` (the rows with the cameras on, filmed: an
  illustration), `make-instance`, `run-actions`.

## Determinism (measured on Isaac Sim 5.1, GPU PhysX, RTX 4090, 2026-10-14)
- **Without the onboard cameras a fresh process replays the same rows bit for bit**: PressButton's rows, two fresh
  processes run side by side, the same state after 200 and 500 steps and the same end state (`fcd4de9b…`); every frozen
  instance's two fresh-process replays end in the same end state (Oracle).
- **With the cameras (Isaac renders every step) GPU PhysX becomes timing-dependent.** The same rows in fresh processes with
  the cameras on agreed after 200 steps and then parted: two runs ended in `7421b6ec…`, one in `fcd4de9b…` (all succeeded at
  step 1027). PhysX's enhanced determinism does not help (`7421b6ec…` again). Reading the camera images makes it worse: a
  replay that filmed both cameras every 4 steps ended without success. This is also why the expert's live episode (which
  reads the state between steps) ends elsewhere than the replays of its rows.
- So the grader, the reference recordings and the agent's default Session are camera-free; the cameras are for looking
  (`Session(cameras=True)`), and the instruction tells the agent to check every trajectory with the camera-free CLI.
- How it was missed at first: the first probes hashed the state after the last step, which Isaac Lab had already reset to
  the next start (End state, above); those hashes agreed while the end states did not.
- Only a process's first episode is guaranteed bit-identical; later resets in the same process need not be.
- The hashes are those of this GPU model; another GPU model may differ in the last bits (a trial is graded on the host it
  ran on; BUILD_ONLY "Check a build").

## Grading
Privileged: `tests/grade.py` replays `/app/output/trajectory.npz` twice, each in a fresh camera-free process
(`rcb_ambench.py replay`); success = AM-Bench's check held in both, the end states' hashes agree, and the rebuilt start
matches `initial_sha`. The verdict is written first; then a third process films the rows with the cameras on
(`/logs/verifier/replay.mp4`, an illustration: `video_episode_success`, never the reward). Whose failure a 0 is follows
YAMLab's grader: an unreadable deliverable is `bad_trajectory`, another task's file `wrong_task` (the agent's 0); so is
a row whose quaternion has zero or non-finite length (`bad_quaternion_rows`, checked when the file is read; the replay
CLI also reports a row it refuses as `bad_trajectory`, a verdict, never a replay without a result; 2026-10-14, board
0121: such a row used to end the replay process without a result, `replay_failed`, an infra error); a replay
without a result, a replay time-out or `instance_ok = 0` is `grader_error = infra_error = 1`. A replay process that ends
without a result (Isaac died; the CLI exits at once on an error instead of hanging) is run once more (`replay_retries`).
Each process has max(1800 s, 1500 s + runnable rows / 4), the runnable rows being the trajectory cut at the episode length;
`[verifier] timeout_sec = 9000` fits the three processes for PushSlider's 3120 rows plus one rerun. The first limits
(1200 s, 900 s + rows / 5) were too short: in the first PressButton oracle trial the verifier's first replay, a cold start
compiling its shaders on a host at load average ~100 with two other Isaac processes on the GPU, died in the scene build
("Failed to get DOF velocities from backend") and then hung until its limit (`infra_error`). The verifier runs with
`network_mode = "no-network"`: every web asset the scenes load is in the image (BUILD_ONLY, Data).

## Time budget (D8)
3600 s for every task (each task's `[agent] timeout_sec`, the proposal's default; PROTOCOL §2.12), stated in each instruction's
closing `## Time limit` section. Every Python process pays ~2-6 min of Isaac Sim launch and scene build (the upper end with
other Isaac jobs on the GPU); stepping runs at about 9-15 control steps/s, so a full episode (20-26 s simulated) takes
3-5 min.

## Standard mode (planned)
Not in this set. Two things must be settled first: (1) a standard sidecar has to render the cameras for the agent's
observations, and rendering makes GPU PhysX timing-dependent (Determinism), so the live episode and fresh replays will
differ: the standard tasks would be graded by their live episode (PROTOCOL §4.8, as RoboDojo's non-reproducible tasks), or
the observations rendered by a second, camera-only process fed the physics state; (2) a `/kinematics` endpoint for a
floating-base arm.

## Declarations
- **Tooling: thin wrappers only.** The environment's own action, its state, its cameras, recording and replay. Task-level
  skills (reach, press, push, turn) are never added.
- **World-frame information (D7).** The privileged instructions give the full scene (the reset distributions and the
  frozen instance's state through the tooling).
- **Pointers to the reference solution.** The reference rows come from AM-Bench's public scripted experts; the image has
  none and the agent's egress cannot reach GitHub. `instance.json` names no expert (`mk_tasks.py` refuses one that does);
  the provenance is in `scripts/ambench/instances.json` only.
- **Upstream data.** Four of AM-Bench's USDs load files from NVIDIA's asset bucket by URL (the bin's geometry, the button's
  material, the robot's paint); the image holds copies and `images/ambench/localize_assets.py` rewrites the URLs to them.
