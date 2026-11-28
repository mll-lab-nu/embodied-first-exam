# AM-Bench · ambench-open-door-fahexa-i00 (privileged)

| | |
|---|---|
| Task ID | `ambench-open-door-fahexa-i00-privileged` |
| Benchmark | [AM-Bench](https://github.com/ambench/ambench) (Wang et al., 2026), upstream `ambench/ambench@60bf5b7` |
| Robot | AM-Bench's FA-Hexa: a fully actuated hexarotor with a 4-joint arm and a two-finger gripper |
| Mode | privileged |
| Instance | `open_door_fahexa`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Push the door open, away from you, about a quarter of the way or more.

## Success criteria
At one control step, the door's hinge is open by more than 20°, away from the robot. The first such step ends the
replay as a success.

The verifier replays `/app/output/trajectory.npz` (`task` = the environment's id, `actions` of shape (T, 8) with
T ≤ 8000) open-loop, in a fresh process in a separate sandbox without network, from its own copy of the frozen
instance, and does so up to 3 times, each in a new process. It stops at the first replay that succeeds, and one is
enough. Each row is one control step of 1/120 s: AM-Bench's end-effector pose action (position, quaternion, gripper;
the gripper value is clipped to [-1, 1]). In a replay, the condition above is checked after every control step, and
the first step at which it holds ends the replay as a success. Rows after it are not executed. AM-Bench's own time-out
ends a replay as a failure: after 15 s of simulated time (control step 1799), or when the rows run out.

A missing file scores 0, and so does an invalid one: not a readable `.npz`, no `task` or `actions` entry, a `task`
that names another environment, the wrong shape, more than 8000 rows, a non-finite value, or a row whose quaternion
has zero length. A replay that gives no result or runs out of its time, a replay whose output shows GPU faults
(PhysX kernels that failed to launch, CUDA out of memory), and a replay whose rebuilt start does not match the frozen
instance are infrastructure failures, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 34 GiB | 1024 | 16 GiB | 10 GiB |
| verifier | 8 | 24 GiB | no cap | 16 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, RTX 4090, held by `main`.
- Recommended GPU: L40S 48GB / RTX 4090 24GB.

## License
AM-Bench ([ambench/ambench](https://github.com/ambench/ambench) @ `60bf5b7`) is released under the
[Apache License 2.0](https://github.com/ambench/ambench/blob/60bf5b73041df4eab571f7d9f0a297aeecbf2e0d/LICENSE); its
third-party notices are in `THIRD_PARTY_NOTICES.md` of that commit. It runs on Isaac Lab (BSD-3-Clause) and NVIDIA
Isaac Sim 5.1.0, under the [NVIDIA Isaac Sim / Omniverse licence](https://docs.isaacsim.omniverse.nvidia.com/latest/common/NVIDIA_Omniverse_License_Agreement.html);
Isaac Sim may not be redistributed, so the simulator image is built locally and never published. The scenes load files
from NVIDIA's public asset buckets (baked into the image), under NVIDIA's terms.
