# pandadyn-s09-toss-recatch-delivery-i00-privileged

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | privileged |
| Twin | `pandadyn-s09-toss-recatch-delivery-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `s09_toss_recatch_delivery` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` |

## Task
A ball is thrown high into the air when the episode starts and comes down near the robot. Catch it in the shallow cup the Panda holds, which has one open side. Bring the cup to a launch region and toss the ball straight up out of the cup with a real throw: it must leave the cup floor while rising. Move the cup sideways and catch the ball again. Finally, release it into an open box that slides back and forth along a rail, where it must settle while the box is moving. The deliverable is one replayable trajectory of 100 Hz joint-target actions (`/app/output/trajectory.npz`,
8 values per row), graded by the task's own staged success check: 5 phases (`initial_catch`, `launch_region`, `self_toss`, `displaced_recatch`, `moving_receiver_delivery`), in order,
with no failure event and no safety-limit violation, within the task's horizon of 25 s.

## Difficulty
The ball falls from high up into a cup only 15 mm deep with an open side. The self-toss needs a genuine throw, with the cup accelerating downwards away from the ball while nearly level. The recatch must happen with the cup displaced, and the final release must land in an oscillating box during one of its fast stretches. Privileged mode gives the full simulator state (every object's pose and velocity, the fixtures, the
announced goals), the parameters, unlimited exact resets and snapshots, and self-replay; the tooling offers only joint
targets and kinematics. This mode is the control for the standard twin.

## Reference solution
`solution/oracle_actions.npy` (1241 control steps, run by `solution/oracle.py` through the agent's own tooling): a
recorded rollout of this instance by the benchmark's reference controller, which reads the simulator's true state in closed
loop, replayed open-loop. The reference controllers and their recordings are not in the image, and the agent's network
reaches only the model APIs and the package registries.

## Verification
`tests/grade.py` in a separate sandbox: one replay, in a fresh process, from the verifier's own copy of the instance
(`tests/instance.json`; the rebuilt start is checked against its hash); pass iff the task's success check holds in it
(every phase complete, no failure), plus `/logs/verifier/replay.mp4`
(overview camera). Oracle: 1241 control steps (12.41 s simulated), success at the last one; the oracle
run and two fresh-process replays end in the same state (hash `3f8dccf95457c7ff`), and the rollout reproduces the physical
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
| Benchmark source | Panda Dynamic Scenes (the environment package `images/pandadyn/panda_dynamics/`, from `images/pandadyn/sync_env.py`); task `PandaMultiStage/S09-TossRecatchDelivery-v0` |
| Instance | difficulty `nominal`, seed 0, the resolved parameters and the start's state hash in `environment/instance.json` (`initial_sha` f5d85574581dd770) |
| Actions | 8 per control step (10 ms): per arm 7 absolute joint targets (rad) + the total aperture (m); a Ruckig + torque servo per arm |
| Physics | CPU PhysX at 1000 Hz with enhanced determinism (single thread); SAPIEN renders on the GPU only when a frame is asked for |
| Image | `images/pandadyn/` (public); needs an NVIDIA GPU with Vulkan for SAPIEN (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); a scene builds in ~5-15 s |

### Provenance
Scene description `S09`, frozen instance `S09-TossRecatchDelivery-i00`, chosen and frozen in `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0`.
