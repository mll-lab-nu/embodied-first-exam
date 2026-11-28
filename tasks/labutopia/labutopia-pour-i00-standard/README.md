# LabUtopia · pour (standard)

| | |
|---|---|
| Task ID | `labutopia-pour-i00-standard` |
| Benchmark | [LabUtopia](https://github.com/Rui-li023/LabUtopia) (Li et al., 2025), upstream `Rui-li023/LabUtopia@8df7278` |
| Robot | Franka Emika Panda arm (7 joints) with its two-finger gripper |
| Mode | standard |
| Instance | `pour`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Pick up the small beaker and tip it over the large beaker as if pouring into it, then turn it back upright and hold it
over the large beaker for about a second and a half.

## Success criteria
In this order, at any point of the episode (once it has happened it counts, whatever follows):
1. The small beaker's centre rises to more than 0.12 m higher than its starting height.
2. Its orientation at the next control step is the reference. After that, a step counts only while the small beaker's
   centre is within 0.0776 m horizontally of the large beaker's centre (LabUtopia's pour distance for this beaker).
3. At a counted step it is turned more than 50 degrees from the reference.
4. At a later counted step it is back within 30 degrees of the reference.
5. After that, it is more than 0.05 m higher than its starting height at 84 counted control steps (1.4 s). These steps need
   not be consecutive: steps that do not count neither add to nor reset the total.

The graded episode is the one live episode, as it ran; nothing is replayed to grade it. There is no reset. The episode
ends when the agent sends `/finish`, when the agent's session ends (at the latest after 1 h), or after 36,000
control steps (600 s of simulated time). Meeting the condition does not end the episode, and the service never reports
success while it runs. The condition above is checked after every control step. When the episode ends at `/finish` or at the
session's end while a timed hold of the condition is partly done, the last command is held for up to 120 more control steps,
and the hold counts if it completes in that time.

An episode that ends in a simulator error scores 0. A live episode that did not start in the instance's recorded
placements, and a service that never wrote its record, are infrastructure failures, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 32 GiB | 16384 | no GPU | 20 GiB |
| `sim` | 16 | 24 GiB | 16384 | 16 GiB | — |
| verifier (as `main`) | 8 | 32 GiB | no cap | no GPU | 20 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: RTX 4090, L40S, held by `sim`.
- Recommended GPU: RTX 4090 24GB / L40S 48GB.

## License
LabUtopia ([Rui-li023/LabUtopia](https://github.com/Rui-li023/LabUtopia) @ `8df7278`): the code is under the
[MIT License](https://github.com/Rui-li023/LabUtopia/blob/8df72784265c375a327ffa3f0a0cf8c676f229a7/LICENSE); the data
assets (the laboratory scenes and objects) are under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/):
**non-commercial use only** (research and education). The simulator is NVIDIA Isaac Sim 6.1.0, under the
[NVIDIA Isaac Sim / Omniverse licence](https://docs.isaacsim.omniverse.nvidia.com/latest/common/NVIDIA_Omniverse_License_Agreement.html);
it may not be redistributed, so the simulator image is built locally and never published. The robot model and 64
files from NVIDIA's public asset server come under NVIDIA's terms.
