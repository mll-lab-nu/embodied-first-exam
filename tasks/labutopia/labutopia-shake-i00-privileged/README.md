# LabUtopia · shake (privileged)

| | |
|---|---|
| Task ID | `labutopia-shake-i00-privileged` |
| Benchmark | [LabUtopia](https://github.com/Rui-li023/LabUtopia) (Li et al., 2025), upstream `Rui-li023/LabUtopia@8df7278` |
| Robot | Franka Emika Panda arm (7 joints) with its two-finger gripper |
| Mode | privileged |
| Instance | `shake`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Pick up the beaker and, holding it in the air, shake it sideways five times, each shake moving it a thumb's length or
more; then hold it still for a second.

## Success criteria
Only control steps at which the beaker's centre is at least 0.05 m higher than its starting height count; the others are
skipped. Five times: the beaker's centre moves 0.05 m or more horizontally from where it was at the first counted step
of that move. After the fifth move, over 60 counted control steps in a row, the centre stays within a 0.01 m range in x
and within a 0.01 m range in y.

The verifier replays `/app/output/trajectory.npz` (array `actions`, shape (T, 18), 1 ≤ T ≤ 36,000, finite values) once,
open-loop, in a fresh process in a separate sandbox without network, from its own copy of the frozen instance. Each row
is one control step of 1/60 s: 9 position targets and 9 velocity targets, clipped to the action limits. The replay
stops at the first control step at which the condition above is met: that is a success. Rows after it are not executed. A
replay that runs out of rows, or reaches 36,000 control steps, without meeting the condition scores 0.

A missing file scores 0, and so does an invalid one: not a readable `.npz`, no `actions` array, a `task` entry that
names another task, the wrong shape, a non-finite value, or more than 36,000 rows. A replay that gives no result, and a
replay whose scene does not rebuild the instance's recorded placements, are infrastructure failures, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 39 GiB | 16384 | 16 GiB | 20 GiB |
| verifier | 8 | 32 GiB | no cap | 16 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: RTX 4090, L40S, held by `main`.
- Recommended GPU: RTX 4090 24GB / L40S 48GB.

## License
LabUtopia ([Rui-li023/LabUtopia](https://github.com/Rui-li023/LabUtopia) @ `8df7278`): the code is under the
[MIT License](https://github.com/Rui-li023/LabUtopia/blob/8df72784265c375a327ffa3f0a0cf8c676f229a7/LICENSE); the data
assets (the laboratory scenes and objects) are under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/):
**non-commercial use only** (research and education). The simulator is NVIDIA Isaac Sim 6.1.0, under the
[NVIDIA Isaac Sim / Omniverse licence](https://docs.isaacsim.omniverse.nvidia.com/latest/common/NVIDIA_Omniverse_License_Agreement.html);
it may not be redistributed, so the simulator image is built locally and never published. The robot model and 64
files from NVIDIA's public asset server come under NVIDIA's terms.
