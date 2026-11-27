# BEHAVIOR-1K · sorting_books_on_shelf (privileged)

| | |
|---|---|
| Task ID | `behavior-sorting-books-on-shelf-i00-privileged` |
| Benchmark | [BEHAVIOR-1K](https://behavior.stanford.edu/) (Li et al., 2024), upstream `StanfordVL/BEHAVIOR-1K@b197991` |
| Robot | Galaxea R1 Pro mobile bimanual manipulator (holonomic wheeled base, 4-joint trunk, two 7-joint arms with parallel-jaw grippers) |
| Mode | privileged |
| Instance | `sorting_books_on_shelf`, seed 301 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Stack the books in the bookcase by kind: the three comics in one pile, one notebook on the other and one hardback on the
other.

## Success criteria
All three comic books, both notebooks and both hardbacks are inside the bookcase. Exactly two of the comic books are
each on top of a comic book; at least one notebook is on top of a notebook; and at least one hardback is on top of a
hardback.

The relations above are OmniGibson's object states, evaluated on the simulator after every control step (30 Hz). An
object is *on* another (`ontop`) when the two touch and the other is directly below it; *inside* when the centre of its
bounding box lies in one of the other's container volumes; *next to* (`nextto`) when their bounding boxes are no farther
apart than a sixth of their mean side length and one is a horizontal neighbour of the other; *under* when the other is
directly above it; *touching* when the two are in contact. An object is *closed* when none of its openable joints is
more than 5 % of its range away from closed, and *switched on* when its toggle state is on.

Success needs more than these conditions: they hold for 30 consecutive control steps (1 s of simulated time), and on
each of those steps no object they name (furniture and floors included; a substance has no pose and is not checked) is
held by a gripper's assisted grasp, and each of those objects moves slower than 0.05 m/s. The replay ends at the end of
that window. There is no partial credit.

The graded file is `/app/output/trajectory.npz`: `actions`, a finite (T, 25) array with one row per control step and
at most 40,000 rows, and `task` = `sorting_books_on_shelf`. The verifier replays it open-loop, in a fresh process, from the frozen
start (the scene is rebuilt and checked against the recorded state hash, or every object pose within tolerance). After
the last row the robot holds its last command with the base still for up to 150 control steps (5 s), and a success
within that window counts. It runs up to 3 such replays and the task passes if any one of them succeeds. A replay ends
as a failure when the robot has fallen over (its base more than 3 cm below the floor, or its up axis tilted more than
41.4° from vertical, for 300 consecutive control steps) or on a simulator breakdown (a non-finite robot state, the robot
or a named object more than 10 km from the origin, or the base faster than 100 m/s).

A missing file scores 0, and so does a file that is not a plain npz, lacks `task` or `actions`, names another task, has
another shape, a non-finite value or more than 40,000 rows. A frozen scene that does not rebuild in the verifier, or a
replay process that dies or exceeds its time limit (1200 s plus T / 1.5 s, at least 3600 s and at most 28000 s), is an
infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 29 GiB | 8192 | 22 GiB | 32 GiB |
| verifier | no cap | no cap | no cap | 22 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `main`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## License
The task definitions (BDDL activity definitions) and the simulator are BEHAVIOR-1K's
([StanfordVL/BEHAVIOR-1K](https://github.com/StanfordVL/BEHAVIOR-1K) v3.9.2: OmniGibson and bddl, MIT License; paper: Li
et al., 2024, "BEHAVIOR-1K: A Human-Centered, Embodied AI Benchmark with 1,000 Everyday Activities and Realistic
Simulation", arXiv:2403.09227). The scenes, objects, robot assets and task instances are the BEHAVIOR Data Bundle, under
the BEHAVIOR Data Bundle End User License Agreement: **non-commercial academic research use only (NC)**, no
redistribution, use only within OmniGibson. It is never in an image or in this repository; each user downloads it after
accepting that licence and mounts it read-only. The simulator image contains NVIDIA Isaac Sim 5.1 and Omniverse Kit
(NVIDIA proprietary licence terms, accepted when the image is built).
