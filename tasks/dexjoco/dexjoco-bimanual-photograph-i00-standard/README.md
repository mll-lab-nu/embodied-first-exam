# DexJoCo · bimanual_photograph (standard)

| | |
|---|---|
| Task ID | `dexjoco-bimanual-photograph-i00-standard` |
| Benchmark | [DexJoCo](https://dexjoco.github.io/) (Wang et al., 2026), upstream `brave-eai/dexjoco@8d23b0f` |
| Robot | Two Franka Emika Panda arms side by side, each with a 16-DoF Wonik Allegro hand |
| Mode | standard |
| Instance | `bimanual_photograph`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Take a picture of the logo: hold the camera a short way in front of the logo and well above the table, pointed straight
at it, and press its shutter button.

## Success criteria
Success, at the end of a single control step (no hold), all three hold:
- the camera is placed: its view point (site `view_direction_site`) is within 0.16 m of the line along the world x axis
  through the point 0.40 m in front of the logo (towards the robot), and within 0.10 m of that point along the line;
- the camera is aimed: its optical axis (the local z axis of geom `camera_axis_z`) is within 10° of the world +x
  direction, towards the logo;
- the shutter is pressed: the shutter button (`shutter`) is in contact with a geom that is not part of the camera.

There is no task failure.

Graded: the live episode the simulator service ran; nothing is replayed. There is one episode and no reset. A success
never ends the episode and is never shown to the agent. The episode ends at the agent's `/finish`, when the agent's
time (1 h) runs out, or at a task failure where the task has one; there is no step limit (a runaway guard at
10,000,000 control steps ends it like `/finish`).

The check is judged as an event: the episode is a success if it passes at the end of at least one control step of the episode.

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
