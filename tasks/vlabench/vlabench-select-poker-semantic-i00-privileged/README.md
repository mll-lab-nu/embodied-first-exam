# VLABench · select_poker_semantic (privileged)

| | |
|---|---|
| Task ID | `vlabench-select-poker-semantic-i00-privileged` |
| Benchmark | [VLABench](https://github.com/OpenMOSS/VLABench) (Zhang et al., 2024), upstream `OpenMOSS/VLABench@cf588fe` |
| Robot | Franka Emika Panda arm (7 joints) with its two-finger gripper, VLABench's model on a fixed base |
| Mode | privileged |
| Instance | `vlabench/select_poker_semantic`, seed 0 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Pick up the six of spades and hold it at least a hand's length above the table.

## Success criteria
Condition (VLABench's `is_grasped` and `lift`, both at once): a geom of one of the gripper's fingers is in contact with
the card `6_of_spades`, and the card's origin is at a height of at least 0.9 m (the table top is at 0.76 m).

Positions are object origins in the world frame of the instruction (metres, z up). A control step is 0.1 s (100 physics
steps of 1 ms), and VLABench checks the condition after every control step.

The graded file is `/app/output/trajectory.npz`: key `actions`, a finite (T, 9) array with 1 ≤ T ≤ 4000, one row of
joint and finger targets per control step (rows are clipped into the actuators' bounds). The verifier replays it once,
open-loop, in a fresh process from the frozen start. VLABench ends the episode at the first control step after which
the condition holds. The trajectory passes when that is its last row. A row after that step makes the trajectory
invalid (score 0), and a replay whose rows run out before the condition holds scores 0. A missing file, a file that is
not a pickle-free npz of at most 8 MiB, or an `actions` array of another shape, with a non-finite value or with more
than 4000 rows scores 0. A replay that fails with an error, runs over 3600 s, or finds a frozen scene that does not
rebuild with the recorded model and initial-state hashes is a grader error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 20 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 16 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
VLABench ([OpenMOSS/VLABench](https://github.com/OpenMOSS/VLABench) @ `cf588fe`; Zhang et al., 2024, arXiv:2412.18194)
code: MIT License (its `LICENSE.txt`). The scene and object assets come from the Hugging Face dataset
[lerobot/vlabench-assets](https://huggingface.co/datasets/lerobot/vlabench-assets) @ `08d7a44`, which states no licence:
they are downloaded when the image is built and are never redistributed by this repository or in a published image.
MuJoCo 3.2.2 and dm_control 1.0.22: Apache-2.0. No non-commercial terms apply.
