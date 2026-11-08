# pandadyn-s06-cube-flip-route-recover-i00-privileged

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | privileged |
| Twin | `pandadyn-s06-cube-flip-route-recover-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `s06_cube_flip_route_recover` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` |

## Task
A cube rests on a raised launch surface. With a short push from the pusher blade, tip it over so that the face that initially faces the robot (-x) ends up on top, the cube completing the tip by its own momentum after the blade has let go, and let it settle. Then push the flipped cube onto an inclined chute, let it slide down by itself, meet it with the blade on its downhill side near the chute's lower end, and bring it to rest in the pocket at the bottom of the chute with the same face still on top. The deliverable is one replayable trajectory of 100 Hz joint-target actions (`/app/output/trajectory.npz`,
8 values per row), graded by the task's own staged success check: 4 phases (`momentum_face_flip`, `oriented_chute_entry`, `downstream_intercept`, `pocket_delivery`), in order,
with no failure event and no safety-limit violation, within the task's horizon of 25 s.

## Difficulty
The flip needs a short, well-dosed push that is released early so the cube finishes the tip by its own momentum without being touched again; on the chute the cube speeds up by itself and must be met on its downhill side at speed after a contact-free slide, then stopped in a shallow pocket without tumbling onto another face. Privileged mode gives the full simulator state (every object's pose and velocity, the fixtures, the
announced goals), the parameters, unlimited exact resets and snapshots, and self-replay; the tooling offers only joint
targets and kinematics. This mode is the control for the standard twin.

## Reference solution
`solution/oracle_actions.npy` (1295 control steps, run by `solution/oracle.py` through the agent's own tooling): a
recorded rollout of this instance by the benchmark's reference controller, which reads the simulator's true state in closed
loop, replayed open-loop. The reference controllers and their recordings are not in the image, and the agent's network
reaches only the model APIs and the package registries.

## Verification
`tests/grade.py` in a separate sandbox: one replay, in a fresh process, from the verifier's own copy of the instance
(`tests/instance.json`; the rebuilt start is checked against its hash); pass iff the task's success check holds in it
(every phase complete, no failure), plus `/logs/verifier/replay.mp4`
(overview camera). Oracle: 1295 control steps (12.95 s simulated), success at the last one; the oracle
run and two fresh-process replays end in the same state (hash `ad3ddd2643881562`). The start's arm pose
depends on the BLAS kernel, so every container that builds the scene pins it (`OPENBLAS_CORETYPE=Haswell`: the same
start and oracle state on every x86-64 host with AVX2); the bank's rollout was recorded under another kernel, its rows
succeed here. `nop`: no trajectory, reward 0; a trajectory that
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
| Benchmark source | Panda Dynamic Scenes (the environment package `images/pandadyn/panda_dynamics/`, from `images/pandadyn/sync_env.py`); task `PandaMultiStage/S06-CubeFlipRouteRecover-v0` |
| Instance | difficulty `nominal`, seed 0, the resolved parameters and the start's state hash in `environment/instance.json` (`initial_sha` 4511f6c2f6be99c4) |
| Actions | 8 per control step (10 ms): per arm 7 absolute joint targets (rad) + the total aperture (m); a Ruckig + torque servo per arm |
| Physics | CPU PhysX at 1000 Hz with enhanced determinism (single thread); SAPIEN renders on the GPU only when a frame is asked for |
| Image | `images/pandadyn/` (public); needs an NVIDIA GPU with Vulkan for SAPIEN (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); a scene builds in ~5-15 s |

### Provenance
Scene description `S06`, frozen instance `S06-CubeFlipRouteRecover-i00`, chosen and frozen in `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0`.
