# pandadyn-s03-clear-gate-hockey-i00-privileged

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | privileged |
| Twin | `pandadyn-s03-clear-gate-hockey-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `s03_clear_gate_hockey` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` |

## Task
A square puck slides toward the robot over an almost frictionless table at the start. First touch it with the paddle; then strike it so that, sliding free of the paddle, it hits a sliding blocker bar that obstructs the way to the goal fast enough to push it aside along its rail. Let the puck slide back across a recovery line by itself, strike it a second time, and make it bank off the rail designated for this episode (one of two rails, coloured green; the other is grey) without touching the other rail, and then cross the goal line while the blocker is still pushed aside. The deliverable is one replayable trajectory of 100 Hz joint-target actions (`/app/output/trajectory.npz`,
8 values per row), graded by the task's own staged success check: 5 phases (`first_strike`, `clear_blocker`, `recover_deflection`, `second_strike`, `bank_and_goal`), in order,
with no failure event and no safety-limit violation, within the task's horizon of 35 s.

## Difficulty
The puck slides almost without friction and rebounds off everything, so each strike sets its direction and speed in a single contact. The blocker can only be cleared by a puck sliding free, the puck must come back across the recovery line on its own, and the final shot must bank off the designated rail, and only that one, into a narrow goal while the blocker stays out of the way. Privileged mode gives the full simulator state (every object's pose and velocity, the fixtures, the
announced goals), the parameters, unlimited exact resets and snapshots, and self-replay; the tooling offers only joint
targets and kinematics. This mode is the control for the standard twin.

## Reference solution
`solution/oracle_actions.npy` (3025 control steps, run by `solution/oracle.py` through the agent's own tooling): a
recorded rollout of this instance by the benchmark's reference controller, which reads the simulator's true state in closed
loop, replayed open-loop. The reference controllers and their recordings are not in the image, and the agent's network
reaches only the model APIs and the package registries.

## Verification
`tests/grade.py` in a separate sandbox: two replays, each in a fresh process, from the verifier's own copy of the instance
(`tests/instance.json`; the rebuilt start is checked against its hash); pass iff the task's success check holds in both
(every phase complete, no failure) and both end in the same state (`deterministic`), plus `/logs/verifier/replay.mp4`
(overview camera). Oracle: 3025 control steps (30.25 s simulated), success at the last one; the oracle
run and two fresh-process replays end in the same state (hash `0c1d3e2436d6820c`), and the rollout reproduces the physical
state the benchmark recorded for it after every control step, bit for bit. `nop`: no trajectory, reward 0; a trajectory that
holds the arm still fails (the benchmark's parked controls never succeeded).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU with Vulkan (RTX 4090 / L4).
- Measured: 50 oracle trials, 25 per mode (rcb_monitor samples every 5 s, efe:pandadyn-0.1.0, RTX 4090, 2026-10-13): privileged trial peak 0.79 GiB (anon + shmem), GPU 0.05 GiB; standard sim service peak 0.94 GiB, GPU 0.35 GiB, agent container 0.03 GiB; CPU p90 about 1 core per container; one filmed scene (render_video, S12 and D07): RSS 1.2-1.3 GiB, GPU 0.25 GiB; CPU: one core per scene (CPU PhysX, single-threaded) + one for the agent
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 5 GiB GPU memory, 16 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 5 GiB GPU memory, 16 GiB memory. Limits measured: GPU: 0.25 GiB per scene -> max(1.5 x peak, peak + 4) with room for a few scenes at once; memory: 1.3 GiB per scene, 16 GiB lets an agent run about ten scenes in parallel (50 oracle trials, 25 per mode (rcb_monitor samples every 5 s, efe:pandadyn-0.1.0, RTX 4090, 2026-10-13): privileged trial peak 0.79 GiB (anon + shmem), GPU 0.05 GiB; standard sim service peak 0.94 GiB, GPU 0.35 GiB, agent container 0.03 GiB; CPU p90 about 1 core per container; one filmed scene (render_video, S12 and D07): RSS 1.2-1.3 GiB, GPU 0.25 GiB); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Benchmark source | Panda Dynamic Scenes (the environment package `images/pandadyn/panda_dynamics/`, from `images/pandadyn/sync_env.py`); task `PandaMultiStage/S03-ClearGateHockey-v0` |
| Instance | difficulty `nominal`, seed 0, the resolved parameters and the start's state hash in `environment/instance.json` (`initial_sha` bcbfb438eec4fcea) |
| Actions | 8 per control step (10 ms): per arm 7 absolute joint targets (rad) + the total aperture (m); a Ruckig + torque servo per arm |
| Physics | CPU PhysX at 1000 Hz with enhanced determinism (single thread); SAPIEN renders on the GPU only when a frame is asked for |
| Image | `images/pandadyn/` (public); needs an NVIDIA GPU with Vulkan for SAPIEN (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); a scene builds in ~5-15 s |

### Provenance
Scene description `S03`, frozen instance `S03-ClearGateHockey-i00`, chosen and frozen in `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0`.

### Change Log
- 2026-10-23 (owner): pandadyn 0.2.0, base image `efe:pandadyn-0.2.0`. Harder, stricter checks: one of the two rails
  is designated per instance (coloured green) and the final shot must bank off it and touch no other rail since its
  last paddle contact; the blocker counts as hit only by a puck sliding free of the paddle for 0.15 s or more at 0.15
  m/s or more (an earlier contact fails the task); the puck must slide back across the recovery line by itself; the
  horizon is 35 s (was 25 s). The paddle's adapter is now joined to the paddle by a bridge. The tool's mass is
  unchanged; its centre of mass and inertia shift slightly. Frozen instance: seed 0, `initial_sha` bcbfb438eec4fcea;
  reference rows: 3025 control steps (was seed 0, `initial_sha` 449f78c9e8366697). Results from before are under the
  earlier digest and are not ranked with these.
