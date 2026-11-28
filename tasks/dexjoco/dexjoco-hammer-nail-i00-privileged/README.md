# DexJoCo · hammer_nail (privileged)

| | |
|---|---|
| Task ID | `dexjoco-hammer-nail-i00-privileged` |
| Benchmark | [DexJoCo](https://dexjoco.github.io/) (Wang et al., 2026), upstream `brave-eai/dexjoco@8d23b0f` |
| Robot | Franka Emika Panda arm with a 16-DoF Wonik Allegro hand |
| Mode | privileged |
| Instance | `hammer_nail`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Pick up the hammer and hammer the nail about 4 cm into the wooden block.

## Success criteria
Success: the nail is driven at least 4 cm deep (DexJoCo's nail depth ≥ 0.04 m); the depth never decreases. The depth is
DexJoCo's model of strikes, not free physics: on each control step that ends with the hammer's head (its face, head,
neck or claw) touching the nail, while the hammer face's fastest downward speed over the last 12 physics substeps is
above 0.2 m/s, the nail goes 0.8 cm × (that speed / 0.2 m/s, at most 3) deeper, up to 7.26 cm in all. There is no
task failure.

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory(...)` writes it: this task's name (`hammer_nail`) and at
most 50,000 action rows of 23 finite values, one row per control step (50 Hz). After the agent's session the
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
