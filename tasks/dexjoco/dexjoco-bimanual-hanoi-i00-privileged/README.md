# DexJoCo · bimanual_hanoi (privileged)

| | |
|---|---|
| Task ID | `dexjoco-bimanual-hanoi-i00-privileged` |
| Benchmark | [DexJoCo](https://dexjoco.github.io/) (Wang et al., 2026), upstream `brave-eai/dexjoco@8d23b0f` |
| Robot | Two Franka Emika Panda arms side by side, each with a 16-DoF Wonik Allegro hand |
| Mode | privileged |
| Instance | `bimanual_hanoi`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Stack all three disks on the post on the right arm's side, as in a Tower of Hanoi: the large disk at the bottom, then
the medium one, then the small one on top.

## Success criteria
Each disk belongs to the post (A, B or C; C is on the right arm's side) whose axis its centre is nearest horizontally,
if it is within 0.04 m of it. A disk farther from every post is on the table when its centre is at most 0.06 m above
the top of the base, else in the air. A disk is at rest when the norm of its six free-joint velocities is at most 0.35.
A disk is seated when its centre is within 0.04 m of its post's axis horizontally and within 0.012 m of the height it
has in a stack resting on the base.

Success: for 20 consecutive control steps (0.4 s), at the end of each step, post C holds the large, the medium and the
small disk in that order from the bottom up, posts A and B are empty, and all three disks are seated and at rest.

Task failure (ends the episode, scoring 0), once the same one has lasted 10 consecutive control steps: a larger disk
above a smaller one on a post whose disks are all seated and at rest; or, with all three disks at rest, a disk on the
table.

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory(...)` writes it: this task's name (`bimanual_hanoi`) and at
most 50,000 action rows of 46 finite values, one row per control step (50 Hz). After the agent's session the
verifier replays it once, open-loop, from its own copy of the frozen start (`tests/instance.npz`), in a fresh process
of a separate container without network. As in DexJoCo's own evaluation, the replay ends at the first control step on
which the success check above passes or a task failure above happens; rows after that step are not run. The task is
passed if the replay ends in success; a replay whose rows run out before that scores 0. A missing file scores 0, and so
does a file for another task or one that is not such an array (not an npz, pickled or object arrays, no `task` or
`actions` entry, a wrong number of columns, NaN or infinite values, more than 50,000 rows, a row with a zero tcp
quaternion). Only the trajectory is scored (`gen.py` is not). A start that does not rebuild to the instance's recorded
state hash, a verifier that runs fewer than 4 OpenBLAS threads, or an error inside the grader is an infrastructure
failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 2048 | no GPU | 10 GiB |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Others
The simulation repeats exactly only for one OpenBLAS thread count (DexJoCo's controller does its linear algebra in
numpy): every container that runs it sets `OPENBLAS_NUM_THREADS=4` and needs at least 4 CPUs in its CPU affinity (a
cpuset or `taskset` narrows it; a CPU quota does not). A grading process that runs fewer than 4 OpenBLAS threads gives
no verdict (`too_few_cpus`, an infrastructure failure).

## License
DexJoCo ([brave-eai/dexjoco](https://github.com/brave-eai/dexjoco) @ `8d23b0f`; Wang et al., 2026, "DexJoCo: A
Benchmark and Toolkit for Task-Oriented Dexterous Manipulation on MuJoCo", arXiv:2605.16257) is released under the MIT
License (copyright 2026 Dexjoco contributors). Bundled robot models keep their own terms: the Franka Emika Panda model
(Apache License 2.0) and the Wonik Allegro hand model (BSD 2-Clause). Upstream's teleoperation stack includes GeoRT
under a **non-commercial** license (CC BY-NC); it is removed from the task image and not used. The simulator is MuJoCo
3.4.0 (Apache License 2.0).
