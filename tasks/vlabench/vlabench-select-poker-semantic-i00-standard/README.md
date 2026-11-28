# VLABench · select_poker_semantic (standard)

| | |
|---|---|
| Task ID | `vlabench-select-poker-semantic-i00-standard` |
| Benchmark | [VLABench](https://github.com/OpenMOSS/VLABench) (Zhang et al., 2024), upstream `OpenMOSS/VLABench@cf588fe` |
| Robot | Franka Emika Panda arm (7 joints) with its two-finger gripper, VLABench's model on a fixed base |
| Mode | standard |
| Instance | `vlabench/select_poker_semantic`, seed 0 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Pick up the six of spades and hold it at least a hand's length above the table.

## Success criteria
Condition (VLABench's `is_grasped` and `lift`, both at once): a geom of one of the gripper's fingers is in contact with
the card `6_of_spades`, and the card's origin is at a height of at least 0.9 m (the table top is at 0.76 m).

Positions are object origins in the world frame of the instruction (metres, z up). A control step is 0.1 s (100 physics
steps of 1 ms), and the service checks the condition after every control step. It never reports it, and a success does
not end the episode.

Graded is the one live episode (no reset). It ends at the agent's `POST /finish`, after 9,000 control steps, when the
agent's session ends, or on a simulator error. Unless stated otherwise above, it passes when the condition holds after
the last control step of the episode. A simulator error raised by the agent's calls, or simulator crashes during its
calls that the service cannot resume from, end the episode with 0. A frozen scene that does not rebuild with the
recorded model and initial-state hashes, or service crashes outside the agent's calls, are infrastructure errors, not a
score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 5 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 11 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## License
VLABench ([OpenMOSS/VLABench](https://github.com/OpenMOSS/VLABench) @ `cf588fe`; Zhang et al., 2024, arXiv:2412.18194)
code: MIT License (its `LICENSE.txt`). The scene and object assets come from the Hugging Face dataset
[lerobot/vlabench-assets](https://huggingface.co/datasets/lerobot/vlabench-assets) @ `08d7a44`, which states no licence:
they are downloaded when the image is built and are never redistributed by this repository or in a published image.
MuJoCo 3.2.2 and dm_control 1.0.22: Apache-2.0. No non-commercial terms apply.
