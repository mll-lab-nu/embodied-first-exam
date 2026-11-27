# YAMLab · HangMugOnTree-v0 (privileged)

| | |
|---|---|
| Task ID | `yamlab-hang-mug-on-tree-i13-privileged` |
| Benchmark | [YAMLab](https://github.com/ARISE-Initiative/yamlab) (Dai, 2026), upstream `ARISE-Initiative/yamlab@ec0455d` |
| Robot | Two I2RT YAM arms (6 joints each) with parallel two-finger grippers, on a workstation table |
| Mode | privileged |
| Instance | `hang_mug_on_tree`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Pick up the mug with the left arm, pass it to the right arm in the air, and hang it on the mug tree.

## Success criteria
Three stages, in this order; a stage is counted only after the one before it has latched.

1. Pick: the left gripper is grasping the mug and the mug's centre is more than 5 cm above its resting height (the
   height of its centre when it stands on the table, 4.2 cm above the table top), on 8 consecutive control
   steps. The right gripper is not checked.
2. Handover: the right gripper is grasping the mug, the left gripper is not, and the mug's centre is more than 5 cm
   above its resting height, on 30 consecutive control steps (about 1 s).
3. Hang: the mug's centre is less than 13.5 cm from the mug tree's centre horizontally (half the tree's footprint
   diagonal, at least 10 cm), more than 8.7 cm above the table top (half the mug's height plus 5 cm), neither
   gripper is grasping the mug, and the mug's height stays within 3 cm of its height on the first step of the run, on 30
   consecutive control steps (about 1 s).

A gripper is grasping the mug when both its fingers touch the mug with a contact force of at least 0.1 N, at a point on
their pads.

The graded file is `/app/output/trajectory.npz`: `task` = `hang_mug_on_tree` and `actions`, a finite (T, 14) array with at most
100,000 rows, one row per control step (1/30 s). The verifier replays it once, open-loop, in a fresh process from the
frozen start, and the task succeeds when every stage above has latched at some control step of that replay. The replay
stops at that step; later rows are not run. The replay ends as a failure, at the step it happens, when the mug or the mug tree
falls more than 1 cm below the table top. A trajectory that ends before every stage has
latched scores 0.

A missing file, a file that is not a plain npz with `task` and `actions`, a wrong `task`, a wrong shape, a NaN or
infinite value or more than 100,000 rows scores 0. A replay that gives no result or runs out of its time limit, or a
frozen scene that does not rebuild as recorded, is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 29 GiB | 4096 | 16 GiB | 10 GiB |
| verifier | 8 | 24 GiB | no cap | 16 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, RTX PRO 6000 Blackwell, held by `main`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## License
YAMLab ([ARISE-Initiative/yamlab](https://github.com/ARISE-Initiative/yamlab) @ `ec0455d`), its scene and object USDs
and its dataset (`yamlab/yamlab_datasets` on Hugging Face) are released under the MIT License (Copyright (c) 2026
Tianyuan Dai). Isaac Lab is BSD-3-Clause; YAMLab's LeRobot fork is Apache-2.0. NVIDIA Isaac Sim 5.1 and its wheels are
proprietary: NVIDIA licenses them for use, not for redistribution, so the simulator image is built on your machine and
building it accepts NVIDIA's Isaac Sim / Omniverse licence terms. No non-commercial terms apply.
