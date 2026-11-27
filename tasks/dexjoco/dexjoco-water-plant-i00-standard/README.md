# DexJoCo · water_plant (standard)

| | |
|---|---|
| Task ID | `dexjoco-water-plant-i00-standard` |
| Benchmark | [DexJoCo](https://dexjoco.github.io/) (Wang et al., 2026), upstream `brave-eai/dexjoco@8d23b0f` |
| Robot | Franka Emika Panda arm with a 16-DoF Wonik Allegro hand |
| Mode | standard |
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

Graded: the live episode the simulator service ran; nothing is replayed. There is one episode and no reset. A success
never ends the episode and is never shown to the agent. The episode ends at the agent's `/finish`, when the agent's
time (1 h) runs out, or at a task failure where the task has one; there is no step limit (a runaway guard at
10,000,000 control steps ends it like `/finish`).

The check is judged as an event: the episode is a success if the 30-step count is reached at some control step, even if a task failure ends the episode later; a task failure before that scores 0.

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
