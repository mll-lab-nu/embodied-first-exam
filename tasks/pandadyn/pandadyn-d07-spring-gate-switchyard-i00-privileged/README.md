# pandadyn-d07-spring-gate-switchyard-i00-privileged

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | privileged |
| Twin | `pandadyn-d07-spring-gate-switchyard-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda-bimanual` |
| Family / instance | `d07_spring_gate_switchyard` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.1.0` |

## Task
A low-friction puck slides inside a U-shaped pen of bouncy rails that is open toward the right arm, and a spring-loaded swinging gate stands inside the pen. The left Panda has a bare gripper. It must take hold of the gate with both fingers and swing it open one way. The right Panda's paddle must then hit the puck so that it travels deep into the pen. While the puck runs round, the left hand, still gripping, must swing the gate the other way: at the moment the puck hits the upper (+y) rail, the gate must be at that opposite angle. The right paddle then intercepts the puck. Finally the puck must cross a goal line in front of a backstop on the right arm's side while the gate is still deflected well away from its rest position and the paddle is not touching the puck. The deliverable is one replayable trajectory of 100 Hz joint-target actions (`/app/output/trajectory.npz`,
16 values per row), graded by the task's own staged success check: 5 phases (`left_gate_open`, `right_loop_shot`, `gate_reconfiguration`, `return_interception`, `final_gate_shot`), in order,
with no failure event and no safety-limit violation, within the task's horizon of 35 s.

## Difficulty
The left hand must keep a two-finger hold on a light, spring-loaded gate and swing it from one side to the other in time with a fast, bouncing puck. The swing must reach the opposite angle exactly when the puck hits the upper rail. Meanwhile the right paddle must time two separate contacts, and the final crossing still needs the gate held well open. Privileged mode gives the full simulator state (every object's pose and velocity, the fixtures, the
announced goals), the parameters, unlimited exact resets and snapshots, and self-replay; the tooling offers only joint
targets and kinematics. This mode is the control for the standard twin.

## Reference solution
`solution/oracle_actions.npy` (2434 control steps, run by `solution/oracle.py` through the agent's own tooling): a
recorded rollout of this instance by the benchmark's reference controller, which reads the simulator's true state in closed
loop, replayed open-loop. The reference controllers and their recordings are not in the image, and the agent's network
reaches only the model APIs and the package registries.

## Verification
`tests/grade.py` in a separate sandbox: two replays, each in a fresh process, from the verifier's own copy of the instance
(`tests/instance.json`; the rebuilt start is checked against its hash); pass iff the task's success check holds in both
(every phase complete, no failure) and both end in the same state (`deterministic`), plus `/logs/verifier/replay.mp4`
(overview camera). Oracle: 2434 control steps (24.34 s simulated), success at the last one; the oracle
run and two fresh-process replays end in the same state (hash `c7f4026e283e76a9`), and the rollout reproduces the physical
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
| Benchmark source | Panda Dynamic Scenes (the environment package `images/pandadyn/panda_dynamics/`, from `scripts/pandadyn/sync_env.py`); task `PandaMultiStage/D07-SpringGateSwitchyard-v0` |
| Instance | difficulty `nominal`, seed 0, the resolved parameters and the start's state hash in `environment/instance.json` (`initial_sha` 09fa46e74fcf5ec6) |
| Actions | 16 per control step (10 ms): per arm 7 absolute joint targets (rad) + the total aperture (m); a Ruckig + torque servo per arm |
| Physics | CPU PhysX at 1000 Hz with enhanced determinism (single thread); SAPIEN renders on the GPU only when a frame is asked for |
| Image | `images/pandadyn/` (public); needs an NVIDIA GPU with Vulkan for SAPIEN (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); a scene builds in ~5-15 s |

### Provenance
Generated by `scripts/pandadyn/mk_tasks.py` from `scripts/pandadyn/descr/D07.json` and `scripts/pandadyn/frozen/D07-SpringGateSwitchyard-i00/`
(chosen and frozen by `scripts/pandadyn/freeze.py` in `ghcr.io/mll-lab-nu/efe:pandadyn-0.1.0`; the choice and its provenance are in
`scripts/pandadyn/instances.json`).
