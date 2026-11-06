# pandadyn-s04-impact-release-relay-i00-privileged

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | privileged |
| Twin | `pandadyn-s04-impact-release-relay-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `s04_impact_release_relay` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` |

## Task
A small block (the cue) slides along a raised deck toward the robot side at the start. Strike it with the paddle so that it hits a spring-held gate latch and swings the gate open, releasing a ball (the payload) that waits behind the gate on an inclined chute; within 1 s of the cue's impact the ball must be past the gate and rolling down the chute. Intercept the ball with the paddle after it has left the chute, send it through a narrow passage between two walls, then touch it again and bring it to rest in a target zone on the table beyond the passage. The deliverable is one replayable trajectory of 100 Hz joint-target actions (`/app/output/trajectory.npz`,
8 values per row), graded by the task's own staged success check: 5 phases (`cue_strike`, `mechanical_unlatch`, `payload_interception`, `passage_redirection`, `payload_braking`), in order,
with no failure event and no safety-limit violation, within the task's horizon of 25 s.

## Difficulty
The cue must be struck so that it hits the narrow trigger tail hard enough to open the spring-held gate promptly (the ball has to be on its way within 1 s), and the ball leaves the chute fast, so interception, redirection through a 0.09 m passage and braking to rest follow each other quickly. Privileged mode gives the full simulator state (every object's pose and velocity, the fixtures, the
announced goals), the parameters, unlimited exact resets and snapshots, and self-replay; the tooling offers only joint
targets and kinematics. This mode is the control for the standard twin.

## Reference solution
`solution/oracle_actions.npy` (441 control steps, run by `solution/oracle.py` through the agent's own tooling): a
recorded rollout of this instance by the benchmark's reference controller, which reads the simulator's true state in closed
loop, replayed open-loop. The reference controllers and their recordings are not in the image, and the agent's network
reaches only the model APIs and the package registries.

## Verification
`tests/grade.py` in a separate sandbox: one replay, in a fresh process, from the verifier's own copy of the instance
(`tests/instance.json`; the rebuilt start is checked against its hash); pass iff the task's success check holds in it
(every phase complete, no failure), plus `/logs/verifier/replay.mp4`
(overview camera). Oracle: 441 control steps (4.41 s simulated), success at the last one; the oracle
run and two fresh-process replays end in the same state (hash `1d9b3d9306995778`), and the rollout reproduces the physical
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
| Benchmark source | Panda Dynamic Scenes (the environment package `images/pandadyn/panda_dynamics/`, from `images/pandadyn/sync_env.py`); task `PandaMultiStage/S04-ImpactReleaseRelay-v0` |
| Instance | difficulty `nominal`, seed 0, the resolved parameters and the start's state hash in `environment/instance.json` (`initial_sha` 83eae09aec3383b6) |
| Actions | 8 per control step (10 ms): per arm 7 absolute joint targets (rad) + the total aperture (m); a Ruckig + torque servo per arm |
| Physics | CPU PhysX at 1000 Hz with enhanced determinism (single thread); SAPIEN renders on the GPU only when a frame is asked for |
| Image | `images/pandadyn/` (public); needs an NVIDIA GPU with Vulkan for SAPIEN (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); a scene builds in ~5-15 s |

### Provenance
Scene description `S04`, frozen instance `S04-ImpactReleaseRelay-i00`, chosen and frozen in `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0`.
