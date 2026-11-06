# pandadyn-s12-moving-bridge-puck-relay-i00-privileged

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | privileged |
| Twin | `pandadyn-s12-moving-bridge-puck-relay-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `s12_moving_bridge_puck_relay` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` |

## Task
At the start a square puck slides fast along a raised source lane towards the Panda, and the paddle hangs just above its path. Strike the puck while it is still sliding at 0.25 m/s or more so that it slides onto a platform (the bridge) that turns continuously about a vertical axis, and from the bridge onto an exit lane. Intercept it there with the paddle, let it separate, strike it again, and send it along the exit lane through the doorway of a swinging gate that opens and closes by itself, without touching the gate, and on across a goal line, without the paddle touching it as it crosses and with the gate still open. The deliverable is one replayable trajectory of 100 Hz joint-target actions (`/app/output/trajectory.npz`,
8 values per row), graded by the task's own staged success check: 5 phases (`incoming_strike`, `physical_bridge_transfer`, `exit_interception`, `second_strike`, `closing_gate_goal`), in order,
with no failure event and no safety-limit violation, within the task's horizon of 32 s.

## Difficulty
The first strike has to meet the fast incoming puck early, before it has slowed below 0.25 m/s. The transfer depends on the timing of the turning bridge and on the puck sliding across the 2 mm steps between surfaces, and the puck must then be intercepted and struck again on a slippery lane. The final shot has to reach the doorway while the cycling gate is open (about a second in every 2.6 s), without touching the gate. The episode lasts 32 s. Privileged mode gives the full simulator state (every object's pose and velocity, the fixtures, the
announced goals), the parameters, unlimited exact resets and snapshots, and self-replay; the tooling offers only joint
targets and kinematics. This mode is the control for the standard twin.

## Reference solution
`solution/oracle_actions.npy` (2171 control steps, run by `solution/oracle.py` through the agent's own tooling): a
recorded rollout of this instance by the benchmark's reference controller, which reads the simulator's true state in closed
loop, replayed open-loop. The reference controllers and their recordings are not in the image, and the agent's network
reaches only the model APIs and the package registries.

## Verification
`tests/grade.py` in a separate sandbox: one replay, in a fresh process, from the verifier's own copy of the instance
(`tests/instance.json`; the rebuilt start is checked against its hash); pass iff the task's success check holds in it
(every phase complete, no failure), plus `/logs/verifier/replay.mp4`
(overview camera). Oracle: 2171 control steps (21.71 s simulated), success at the last one; the oracle
run and two fresh-process replays end in the same state (hash `aa34f0ab3c7134ec`), and the rollout reproduces the physical
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
| Benchmark source | Panda Dynamic Scenes (the environment package `images/pandadyn/panda_dynamics/`, from `images/pandadyn/sync_env.py`); task `PandaMultiStage/S12-MovingBridgePuckRelay-v0` |
| Instance | difficulty `nominal`, seed 0, the resolved parameters and the start's state hash in `environment/instance.json` (`initial_sha` 1f6e3cd472270a39) |
| Actions | 8 per control step (10 ms): per arm 7 absolute joint targets (rad) + the total aperture (m); a Ruckig + torque servo per arm |
| Physics | CPU PhysX at 1000 Hz with enhanced determinism (single thread); SAPIEN renders on the GPU only when a frame is asked for |
| Image | `images/pandadyn/` (public); needs an NVIDIA GPU with Vulkan for SAPIEN (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); a scene builds in ~5-15 s |

### Provenance
Scene description `S12`, frozen instance `S12-MovingBridgePuckRelay-i00`, chosen and frozen in `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0`.
