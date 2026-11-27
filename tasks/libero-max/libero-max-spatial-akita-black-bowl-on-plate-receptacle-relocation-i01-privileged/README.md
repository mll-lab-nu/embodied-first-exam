# LIBERO-MAX · libero_spatial · receptacle relocation (privileged)

| | |
|---|---|
| Task ID | `libero-max-spatial-akita-black-bowl-on-plate-receptacle-relocation-i01-privileged` |
| Benchmark | [LIBERO-MAX](https://github.com/liberomax/LIBERO-MAX) (Zhang et al., 2026), upstream `liberomax/LIBERO-MAX@a1e3cef` |
| Robot | Franka Emika Panda arm on a fixed mount with its two-finger gripper (LIBERO's OSC_POSE controller) |
| Mode | privileged |
| Instance | `libero-max/libero_spatial/receptacle_relocation`, seed 195 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Pick up the black bowl next to the plate and put it on the plate.

## Success criteria
Goal: the bowl the task names (`akita_black_bowl_1`) is on the plate (`plate_1`): its origin is not lower than the origin of the plate, the two touch, and their origins are less than 3 cm apart horizontally.

The scene changes once in the graded episode, at the first control step on which the hand (robosuite's end-effector point) is within 0.18 m of the position of the bowl the task names (`akita_black_bowl_1`): LIBERO-MAX moves the plate (`plate_1`) 12 cm across the table: it sets that one object's position, and anything resting in or on it stays where it was. The goal is checked wherever the objects are at the end.

An object's origin is its body's position in the simulator. A control step is 1/20 s. LIBERO checks the goal after
every control step, and the episode ends at the first step on which it holds.

The graded file is `/app/output/trajectory.npz` with an `actions` array of shape (T, 7), 1 ≤ T ≤ 220 (LIBERO's
step limit for this suite), one row per control step after LIBERO's 10 warm-up steps; values outside [-1, 1] are
clipped. The verifier replays it once, open-loop, in a fresh process from the frozen start, with the scene change
applied as above. It passes when the goal first holds on the step of the last row. Rows left after the step on which the
goal first holds make the trajectory invalid, and a replay whose last row leaves the goal unmet scores 0.

A missing file, a file that is not a plain npz (at most 2 MB, only `.npy` members) with a finite `actions` array of that
shape, or more than 220 rows scores 0, as does a replay process that fails or runs over its 1 h limit (a grader
error). A host on which the frozen start does not rebuild bit-exactly is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
LIBERO-MAX ([liberomax/LIBERO-MAX](https://github.com/liberomax/LIBERO-MAX) @ `a1e3cef`; Zhang et al., 2026,
arXiv:2609.36518) has no licence file. Its authors gave written permission to redistribute the two parts used here, the
event parameters and case choice (the frozen instance) and the event runtime in the image, with attribution (cite the
paper and link the repository). The LIBERO package and object assets come from LIBERO-PRO
([Zxy-MLlab/LIBERO-PRO](https://github.com/Zxy-MLlab/LIBERO-PRO) @ `2b910b5`, MIT), built on
[LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO) (MIT); the task data (BDDL and initial-state files) is
LIBERO-PRO's dataset `zhouxueyang/LIBERO-Pro` @ `c86fc3b` (CC BY 4.0). robosuite 1.4.0: MIT; MuJoCo 3.2.6: Apache-2.0.
No part is under a non-commercial licence.
