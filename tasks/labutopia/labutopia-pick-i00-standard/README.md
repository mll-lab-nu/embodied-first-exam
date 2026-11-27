# LabUtopia · pick (standard)

| | |
|---|---|
| Task ID | `labutopia-pick-i00-standard` |
| Benchmark | [LabUtopia](https://github.com/Rui-li023/LabUtopia) (Li et al., 2025), upstream `Rui-li023/LabUtopia@8df7278` |
| Robot | Franka Emika Panda arm (7 joints) with its two-finger gripper |
| Mode | standard |
| Instance | `pick`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Pick up the conical flask and hold it up, more than a hand's width off the bench, for a second.

## Success criteria
The conical flask's centre is more than 0.10 m higher than its starting height, and has been for at least the last 60
consecutive control steps (1 s) of the episode.

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
