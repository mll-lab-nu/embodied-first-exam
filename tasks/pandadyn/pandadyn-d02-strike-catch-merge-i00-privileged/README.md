# pandadyn-d02-strike-catch-merge-i00-privileged

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | privileged |
| Twin | `pandadyn-d02-strike-catch-merge-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda-bimanual` |
| Family / instance | `d02_strike_catch_merge` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` |

## Task
Two small balls wait behind closed shutters near the top of two parallel inclined lanes. The shutters open by themselves, the first shortly after the start and the second a few seconds later, and each released ball rolls down its lane and flies off the open lower end. The left Panda's paddle must touch each ball after the ball has flown free. The right Panda's cup must catch the first ball and carry it away from the catch point without losing it. The cup must then catch the second ball while still holding the first, and finally put both balls into a fixed basin, where they must come to rest with the cup no longer touching them. The deliverable is one replayable trajectory of 100 Hz joint-target actions (`/app/output/trajectory.npz`,
16 values per row), graded by the task's own staged success check: 6 phases (`first_redirect`, `first_catch`, `loaded_cup_relocation`, `second_redirect`, `second_catch`, `both_delivery`), in order,
with no failure event and no safety-limit violation, within the task's horizon of 25 s.

## Difficulty
The balls arrive on a schedule the robot cannot change: the first strike, catch and loaded relocation must fit before the second shutter opens. The second catch must then take a ball deflected by the paddle into a cup that already holds the first ball, without spilling it. Privileged mode gives the full simulator state (every object's pose and velocity, the fixtures, the
announced goals), the parameters, unlimited exact resets and snapshots, and self-replay; the tooling offers only joint
targets and kinematics. This mode is the control for the standard twin.

## Reference solution
`solution/oracle_actions.npy` (1755 control steps, run by `solution/oracle.py` through the agent's own tooling): a
recorded rollout of this instance by the benchmark's reference controller, which reads the simulator's true state in closed
loop, replayed open-loop. The reference controllers and their recordings are not in the image, and the agent's network
reaches only the model APIs and the package registries.

## Verification
`tests/grade.py` in a separate sandbox: two replays, each in a fresh process, from the verifier's own copy of the instance
(`tests/instance.json`; the rebuilt start is checked against its hash); pass iff the task's success check holds in both
(every phase complete, no failure) and both end in the same state (`deterministic`), plus `/logs/verifier/replay.mp4`
(overview camera). Oracle: 1755 control steps (17.55 s simulated), success at the last one; the oracle
run and two fresh-process replays end in the same state (hash `8cb60683ef8fb56b`), and the rollout reproduces the physical
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
| Benchmark source | Panda Dynamic Scenes (the environment package `images/pandadyn/panda_dynamics/`, from `images/pandadyn/sync_env.py`); task `PandaMultiStage/D02-StrikeCatchMerge-v0` |
| Instance | difficulty `nominal`, seed 0, the resolved parameters and the start's state hash in `environment/instance.json` (`initial_sha` 5af2753df0137ee5) |
| Actions | 16 per control step (10 ms): per arm 7 absolute joint targets (rad) + the total aperture (m); a Ruckig + torque servo per arm |
| Physics | CPU PhysX at 1000 Hz with enhanced determinism (single thread); SAPIEN renders on the GPU only when a frame is asked for |
| Image | `images/pandadyn/` (public); needs an NVIDIA GPU with Vulkan for SAPIEN (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); a scene builds in ~5-15 s |

### Provenance
Scene description `D02`, frozen instance `D02-StrikeCatchMerge-i00`, chosen and frozen in `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0`.

### Change Log
- 2026-10-23 (owner): pandadyn 0.2.0, base image `efe:pandadyn-0.2.0`. Configuration only: the balls' mass is the
  `object_mass` parameter (same value); unused parameters are gone. Scene, physics and checks are unchanged. Frozen
  instance: seed 0, `initial_sha` 5af2753df0137ee5; reference rows: 1755 control steps (the same start and reference
  rows as before). Results from before are under the earlier digest and are not ranked with these.
