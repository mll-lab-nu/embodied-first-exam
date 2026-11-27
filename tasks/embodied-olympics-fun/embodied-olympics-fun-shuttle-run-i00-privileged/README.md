# Embodied Olympics · 4 x 10 m shuttle run (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-shuttle-run-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `shuttle_run`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Run the 4 x 10 m shuttle: to the far line and back twice, putting a foot beyond the line at each turn.

## Success criteria
Two lines cross the floor 10 m apart: the start line, which the robot stands just behind, and the far line. Each line
has cones at its ends, 3 m to either side of the centre line. The referee's stages, in order: turn 1, turn 2, turn 3,
finish.
- Turn 1 and turn 3: a foot on the ground wholly beyond the far line (every part of the foot past it; a foot on the
  line does not count), touching the ground only between the line's cones.
- Turn 2: the same at the start line, a foot wholly behind it.
- Finish: after turn 3, the leading point of the torso (not the head, arms, legs or feet) reaches the start line. The
  success is called at that moment.
Turns count only in this order. How the robot faces and turns is free.

Fouls (each fails the attempt): the torso's leading point reaches the start line for the finish outside its cones
(more than 3 m from the centre line); the pelvis leaves the court (more than 4 m to either side of the centre line,
or more than 10 m beyond either line). The generic fall rule is off: a fall does not end the attempt, and the robot may
get up and go on, but the pelvis below 0.4 m for 10 s in a row fails it. Time limit: 30 s (3,000 control steps).

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory()` writes it: an `actions` array of sim rows, one per
10 ms control step, and the task's family name. After the agent's session it is replayed once, open-loop, from the
frozen start, in a fresh process of a separate verifier container without network. Rows run one per control step
until the referee calls the attempt; rows after the call, and rows past the attempt's time limit, are not run. The
task is passed if the referee has called a success when the replay stops. If the rows run out before the referee's
call, the task is not passed. A row the robot cannot run (its first value, the mode, is not one of the robot's modes)
ends the replay at that row without a pass.

The physics diverging (a non-finite state, a bad acceleration, or the robot or a prop faster than 150 m/s) ends the
attempt as a failure, unless a success was called in an earlier control step. Only the trajectory is scored (`gen.py`
and `NOTES.md` are not). A missing file, a file that is not such an array (a link, over 64 MB, more than 40,000 rows,
the wrong row width), a file for another task, or a non-finite value in the rows that are used scores 0. An image that
no longer rebuilds the frozen start, or a replay that crashes or runs over 600 s, is an infrastructure failure, not a
score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
The Embodied Olympics robot library and running-policy port ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics)
@ `7df999b`, a private repository) is released under the MIT License (`LICENSE.roboolympics` in the image); this
benchmark's venues and referees are MIT too. Third-party parts in the image: the Unitree G1 model and meshes from MuJoCo
Menagerie (BSD-3-Clause), the Unitree H1-2 model, meshes and walking policy and the G1 walking policy from
unitree_rl_gym (BSD-3-Clause), the G1 running policy from C1801SYQ/g1_running (Apache-2.0), FALCON's G1 walking policy
from LeCAR-Lab/FALCON (MIT) and the WBC-AGILE G1 walking policy from NVIDIA (Apache-2.0). No non-commercial terms apply.
