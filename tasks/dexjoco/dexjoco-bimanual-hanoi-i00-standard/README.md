# DexJoCo · bimanual_hanoi (standard)

| | |
|---|---|
| Task ID | `dexjoco-bimanual-hanoi-i00-standard` |
| Benchmark | [DexJoCo](https://dexjoco.github.io/) (Wang et al., 2026), upstream `brave-eai/dexjoco@8d23b0f` |
| Robot | Two Franka Emika Panda arms side by side, each with a 16-DoF Wonik Allegro hand |
| Mode | standard |
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

Graded: the live episode the simulator service ran; nothing is replayed. There is one episode and no reset. A success
never ends the episode and is never shown to the agent. The episode ends at the agent's `/finish`, when the agent's
time (1 h) runs out, or at a task failure where the task has one; there is no step limit (a runaway guard at
10,000,000 control steps ends it like `/finish`).

The check is judged on the state the episode ends in: if it does not pass at that moment, the robot holds its last command for up to 60 more control steps (1.2 s), and the episode is a success if the check passes within them with no task failure; the control steps already held count towards the 20. A task failure ends the episode with 0, also after the check has passed.

An episode ended by a simulator error raised by the agent's own call scores 0, and so does a service that crashed only
inside the agent's calls. An episode that does not start from the frozen instance (its state hash differs), a service
that runs fewer than 4 OpenBLAS threads, or a service crash outside the agent's calls is an infrastructure failure,
not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 6 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 4 | 10 GiB | no cap | no GPU | 10 GiB |

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
