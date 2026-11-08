# pandadyn-d12-reciprocal-sliding-transfer-i00-privileged

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | privileged |
| Twin | `pandadyn-d12-reciprocal-sliding-transfer-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda-bimanual` |
| Family / instance | `d12_reciprocal_sliding_transfer` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` |

## Task
Each arm holds a level scoop, a shallow square tray that is open on the side facing the other arm. A cube on a very slippery surface starts on the left scoop. Without tilting the scoops, the left arm must make the cube slide out over its open edge onto the right scoop, which must be moving in step with the left scoop (at 0.2 m/s or more) when the cube arrives and then brake to rest with the cube on it within 1.5 s. The right arm then carries it to a new place and makes it slide back the same way onto the left scoop, which must likewise be moving in step when it arrives and then brake to rest. Finally the cube must be set down on a fixed output platform and left there at rest. Until that final deposit begins, the scoops may not tilt by more than 2.1 deg, and the cube may never be without scoop contact for more than about a tenth of a second. The deliverable is one replayable trajectory of 100 Hz joint-target actions (`/app/output/trajectory.npz`,
16 values per row), graded by the task's own staged success check: 5 phases (`left_inertial_slip`, `right_receive_and_brake`, `reverse_geometry`, `left_receive_and_brake`, `final_support_deposit`), in order,
with no failure event and no safety-limit violation, within the task's horizon of 25 s.

## Difficulty
With tilting forbidden and almost no friction, the cube can be moved only by changing the scoops' velocities. Each transfer is a level hand-off across the gap between two independently moving scoops, during which the cube may lose scoop contact for only about 0.1 s. The receiving scoop must be moving at 0.2 m/s or more, matched to the donor within 0.05 m/s, when the cube arrives, and must then brake to rest within 1.5 s with the cube at rest relative to itself, near its centre, for 0.3 s. Privileged mode gives the full simulator state (every object's pose and velocity, the fixtures, the
announced goals), the parameters, unlimited exact resets and snapshots, and self-replay; the tooling offers only joint
targets and kinematics. This mode is the control for the standard twin.

## Reference solution
`solution/oracle_actions.npy` (1251 control steps, run by `solution/oracle.py` through the agent's own tooling): a
recorded rollout of this instance by the benchmark's reference controller, which reads the simulator's true state in closed
loop, replayed open-loop. The reference controllers and their recordings are not in the image, and the agent's network
reaches only the model APIs and the package registries.

## Verification
`tests/grade.py` in a separate sandbox: one replay, in a fresh process, from the verifier's own copy of the instance
(`tests/instance.json`; the rebuilt start is checked against its hash); pass iff the task's success check holds in it
(every phase complete, no failure), plus `/logs/verifier/replay.mp4`
(overview camera). Oracle: 1251 control steps (12.51 s simulated), success at the last one; the oracle
run and two fresh-process replays end in the same state (hash `6eec516509e100aa`), and the rollout reproduces the physical
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
| Benchmark source | Panda Dynamic Scenes (the environment package `images/pandadyn/panda_dynamics/`, from `images/pandadyn/sync_env.py`); task `PandaMultiStage/D12-ReciprocalSlidingTransfer-v0` |
| Instance | difficulty `nominal`, seed 0, the resolved parameters and the start's state hash in `environment/instance.json` (`initial_sha` 2a3820b2e18a91fc) |
| Actions | 16 per control step (10 ms): per arm 7 absolute joint targets (rad) + the total aperture (m); a Ruckig + torque servo per arm |
| Physics | CPU PhysX at 1000 Hz with enhanced determinism (single thread); SAPIEN renders on the GPU only when a frame is asked for |
| Image | `images/pandadyn/` (public); needs an NVIDIA GPU with Vulkan for SAPIEN (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); a scene builds in ~5-15 s |

### Provenance
Scene description `D12`, frozen instance `D12-ReciprocalSlidingTransfer-i00`, chosen and frozen in `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0`.
