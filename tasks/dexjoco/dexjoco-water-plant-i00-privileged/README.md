# DexJoCo · water_plant (privileged)

| | |
|---|---|
| Task ID | `dexjoco-water-plant-i00-privileged` |
| Benchmark | [DexJoCo](https://dexjoco.github.io/) (Wang et al., 2026), upstream `brave-eai/dexjoco@8d23b0f` |
| Robot | Franka Emika Panda arm with a 16-DoF Wonik Allegro hand |
| Mode | privileged |
| Instance | `water_plant`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Spray the potted plant: pick up the spray bottle, hold its nozzle close to the plant and aimed at it, and keep the
trigger squeezed for a moment.

## Success criteria
Success: for 30 consecutive control steps (0.6 s), all of these hold at the end of each step:
- the trigger is pulled: the trigger joint (`spray_trigger`) has risen above 0.34 rad and not dropped below 0.25 rad
  since;
- the nozzle is in the zone around the plant: the nozzle's reference point (`spray_nozzle`) is at most 0.20 m from the
  plant's origin (`plant`) horizontally and within ±0.20 m of its height;
- the spray points at the plant: the spray direction (the bottle body's local +z axis; its long axis, bottom to head, is
  local +y) is within 45° of the line from the nozzle's reference point to the plant's origin.

The trigger and zone conditions are DexJoCo's own check; the aim condition is added by this benchmark, and DexJoCo's
own success (trigger and zone alone) does not end the episode.

Task failure (ends the episode at once, scoring 0): the trigger is pulled while the nozzle is outside the zone.

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory(...)` writes it: this task's name (`water_plant`) and at
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
