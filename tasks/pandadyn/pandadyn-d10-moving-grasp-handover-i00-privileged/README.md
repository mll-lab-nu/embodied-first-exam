# pandadyn-d10-moving-grasp-handover-i00-privileged

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | privileged |
| Twin | `pandadyn-d10-moving-grasp-handover-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda-bimanual` |
| Family / instance | `d10_moving_grasp_handover` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` |

## Task
Grasp the part with the left gripper while it rides the conveyor, lift it about a hand's length and carry it, still moving, through the presentation point. Hand it to the right gripper while it keeps moving, then lay it into the sliding slot and let go while the slot is moving. The deliverable is one replayable trajectory of 100 Hz joint-target actions (`/app/output/trajectory.npz`,
16 values per row), graded by the task's own staged success check: 5 phases (`moving_pickup`, `moving_presentation`, `overlapping_grips`, `donor_release`, `receiver_slot_delivery`), in order,
with no failure event and no safety-limit violation, within the task's horizon of 25 s.

## Difficulty
Everything happens on the move. The grasp must close on a part that the conveyor is carrying toward its end, and the presentation point must be passed while the part is moving. The handover needs a brief overlap of two independent grippers on one bar, with the bar moving at more than 0.04 m/s through the overlap and the release, without dropping it. The final release must put the bar into a slot that leaves only a small margin along its long axis, while the slot keeps moving and reverses direction. Privileged mode gives the full simulator state (every object's pose and velocity, the fixtures, the
announced goals), the parameters, unlimited exact resets and snapshots, and self-replay; the tooling offers only joint
targets and kinematics. This mode is the control for the standard twin.

## Reference solution
`solution/oracle_actions.npy` (1554 control steps, run by `solution/oracle.py` through the agent's own tooling): a
recorded rollout of this instance by the benchmark's reference controller, which reads the simulator's true state in closed
loop, replayed open-loop. The reference controllers and their recordings are not in the image, and the agent's network
reaches only the model APIs and the package registries.

## Verification
`tests/grade.py` in a separate sandbox: one replay, in a fresh process, from the verifier's own copy of the instance
(`tests/instance.json`; the rebuilt start is checked against its hash); pass iff the task's success check holds in it
(every phase complete, no failure), plus `/logs/verifier/replay.mp4`
(overview camera). Oracle: 1554 control steps (15.54 s simulated), success at the last one; the oracle
run and two fresh-process replays end in the same state (hash `d3dd4e96aa63d9a1`), and the rollout reproduces the physical
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
| Benchmark source | Panda Dynamic Scenes (the environment package `images/pandadyn/panda_dynamics/`, from `images/pandadyn/sync_env.py`); task `PandaMultiStage/D10-MovingGraspHandover-v0` |
| Instance | difficulty `nominal`, seed 0, the resolved parameters and the start's state hash in `environment/instance.json` (`initial_sha` 3bb10643ceecda47) |
| Actions | 16 per control step (10 ms): per arm 7 absolute joint targets (rad) + the total aperture (m); a Ruckig + torque servo per arm |
| Physics | CPU PhysX at 1000 Hz with enhanced determinism (single thread); SAPIEN renders on the GPU only when a frame is asked for |
| Image | `images/pandadyn/` (public); needs an NVIDIA GPU with Vulkan for SAPIEN (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); a scene builds in ~5-15 s |

### Provenance
Scene description `D10`, frozen instance `D10-MovingGraspHandover-i00`, chosen and frozen in `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0`.
