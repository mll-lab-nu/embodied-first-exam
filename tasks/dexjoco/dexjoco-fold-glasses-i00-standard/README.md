# DexJoCo · fold_glasses (standard)

| | |
|---|---|
| Task ID | `dexjoco-fold-glasses-i00-standard` |
| Benchmark | [DexJoCo](https://dexjoco.github.io/) (Wang et al., 2026), upstream `brave-eai/dexjoco@8d23b0f` |
| Robot | Franka Emika Panda arm with a 16-DoF Wonik Allegro hand |
| Mode | standard |
| Instance | `fold_glasses`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Fold the glasses and put them in the open case.

## Success criteria
Success: for 50 consecutive control steps (1.0 s), at the end of each step, both temples are folded (the hinge joints
`temple_0` and `temple_1` each above 1.1 rad) and the glasses' origin (`glasses`) is inside the case: within 0.145 m of
the case's origin (`case`, fixed to the table) along the world x and y axes, and from 0.045 m below to 0.0275 m above
it. There is no task failure.

Graded: the live episode the simulator service ran; nothing is replayed. There is one episode and no reset. A success
never ends the episode and is never shown to the agent. The episode ends at the agent's `/finish`, when the agent's
time (1 h) runs out, or at a task failure where the task has one; there is no step limit (a runaway guard at
10,000,000 control steps ends it like `/finish`).

The check is judged on the state the episode ends in: if it does not pass at that moment, the robot holds its last command for up to 60 more control steps (1.2 s), and the episode is a success if the check passes within them; the control steps already held count towards the 50.

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
