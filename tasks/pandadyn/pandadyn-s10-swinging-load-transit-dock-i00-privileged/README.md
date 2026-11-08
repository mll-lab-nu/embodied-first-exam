# pandadyn-s10-swinging-load-transit-dock-i00-privileged

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | privileged |
| Twin | `pandadyn-s10-swinging-load-transit-dock-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `s10_swinging_load_transit_dock` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` |

## Task
A carrier rests on two small ledges between the gripper's open fingers. It is a short bar with a pendulum (a rod ending in a ball) hanging from a hinge under it, and the pendulum is already swinging. Grip the bar with both fingers and damp the swing. Carry the carrier, still gripped, through two waypoints without letting the carrier or its pendulum touch a block obstacle, brake to rest at the second waypoint, and damp the residual swing again. Finally lower it slowly until the pendulum's ball rests centred in a dock, with the swing settled and the bar still gripped. The deliverable is one replayable trajectory of 100 Hz joint-target actions (`/app/output/trajectory.npz`,
8 values per row), graded by the task's own staged success check: 5 phases (`grasp_settle_and_damp`, `obstacle_transit`, `turn_and_brake`, `residual_swing_cancel`, `load_dock`), in order,
with no failure event and no safety-limit violation, within the task's horizon of 25 s.

## Difficulty
The pendulum is nearly undamped and is driven only through the bar's motion. Every acceleration of the hand, through the turn and the braking, excites it again, and it must be settled three times, the last while the bob sits in a small dock; the carrier must also come to rest at the turn, and the ball may enter the dock only slowly. Privileged mode gives the full simulator state (every object's pose and velocity, the fixtures, the
announced goals), the parameters, unlimited exact resets and snapshots, and self-replay; the tooling offers only joint
targets and kinematics. This mode is the control for the standard twin.

## Reference solution
`solution/oracle_actions.npy` (1456 control steps, run by `solution/oracle.py` through the agent's own tooling): a
recorded rollout of this instance by the benchmark's reference controller, which reads the simulator's true state in closed
loop, replayed open-loop. The reference controllers and their recordings are not in the image, and the agent's network
reaches only the model APIs and the package registries.

## Verification
`tests/grade.py` in a separate sandbox: one replay, in a fresh process, from the verifier's own copy of the instance
(`tests/instance.json`; the rebuilt start is checked against its hash); pass iff the task's success check holds in it
(every phase complete, no failure), plus `/logs/verifier/replay.mp4`
(overview camera). Oracle: 1456 control steps (14.56 s simulated), success at the last one; the oracle
run and two fresh-process replays end in the same state (hash `8c1ac08180026dd0`), and the rollout reproduces the physical
state the benchmark recorded for it after every control step, bit for bit. `nop`: no trajectory, reward 0; a trajectory that
holds the arm still fails (the benchmark's parked controls never succeeded).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 5 | 10 GiB | 1024 | 3 GiB | 10 GiB |
| verifier | 4 | 8 GiB | no cap | 3 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any 8 GB+ NVIDIA GPU with Vulkan (RTX 4090 / L4).

## Details
| | |
|---|---|
| Benchmark source | Panda Dynamic Scenes (the environment package `images/pandadyn/panda_dynamics/`, from `images/pandadyn/sync_env.py`); task `PandaMultiStage/S10-SwingingLoadTransitDock-v0` |
| Instance | difficulty `nominal`, seed 0, the resolved parameters and the start's state hash in `environment/instance.json` (`initial_sha` be10a4a14935d0d0) |
| Actions | 8 per control step (10 ms): per arm 7 absolute joint targets (rad) + the total aperture (m); a Ruckig + torque servo per arm |
| Physics | CPU PhysX at 1000 Hz with enhanced determinism (single thread); SAPIEN renders on the GPU only when a frame is asked for |
| Image | `images/pandadyn/` (public); needs an NVIDIA GPU with Vulkan for SAPIEN (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); a scene builds in ~5-15 s |

### Provenance
Scene description `S10`, frozen instance `S10-SwingingLoadTransitDock-i00`, chosen and frozen in `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0`.
