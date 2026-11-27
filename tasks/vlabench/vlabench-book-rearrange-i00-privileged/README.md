# VLABench · book_rearrange (privileged)

| | |
|---|---|
| Task ID | `vlabench-book-rearrange-i00-privileged` |
| Benchmark | [VLABench](https://github.com/OpenMOSS/VLABench) (Zhang et al., 2024), upstream `OpenMOSS/VLABench@cf588fe` |
| Robot | Franka Emika Panda arm (7 joints) with its two-finger gripper, VLABench's model on a fixed base |
| Mode | privileged |
| Instance | `vlabench/book_rearrange`, seed 0 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Put the three books from the table into the bookshelf side by side, in the order they were published: the oldest on the
robot's left, the newest on its right.

## Success criteria
Condition (VLABench's `contain` and `order`, all at once): the origins of the three books
(`century17_don_quixote_book`, `century18_pride_and_prejudice_book`, `century20_the_metamorphosis_book`) lie inside
the axis-aligned box spanned by the bookshelf's (`shelf_seen`) keypoint sites, over both of its shelves; their x
coordinates increase in that order (Don Quixote, Pride and Prejudice, The Metamorphosis: from the robot's left to its
right); and for each of the first two books, its y and its z are each less than 0.1 m larger than those of the next
book. Whether the books stand upright or touch each other is not checked.

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
