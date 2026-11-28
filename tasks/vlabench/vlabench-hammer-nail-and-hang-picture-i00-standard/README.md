# VLABench · hammer_nail_and_hang_picture (standard)

| | |
|---|---|
| Task ID | `vlabench-hammer-nail-and-hang-picture-i00-standard` |
| Benchmark | [VLABench](https://github.com/OpenMOSS/VLABench) (Zhang et al., 2024), upstream `OpenMOSS/VLABench@cf588fe` |
| Robot | Franka Emika Panda arm (7 joints) with its two-finger gripper, VLABench's model on a fixed base |
| Mode | standard |
| Instance | `vlabench/hammer_nail_and_hang_picture`, seed 0 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Hammer the nail into the wall, then bring the 本所立川 painting right up to the nail, as if to hang it there.

## Success criteria
Condition (both at once): the nail's slide joint is between 0.05 m and 0.08 m, both included (VLABench's
`joint_in_range`; the joint's own range is 0 to 0.06 m); and after some control step of the episode, the grasp point of the painting
(`本所立川_painting`, its one grasp site) was less than 0.05 m from the nail's origin (the nail's fixed base; it does
not move as the nail is driven). Once that has happened it stays counted, even if the painting moves away again.

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
