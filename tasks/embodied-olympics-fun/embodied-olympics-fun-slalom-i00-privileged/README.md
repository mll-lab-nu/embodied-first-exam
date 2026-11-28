# Embodied Olympics · Illinois agility run (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-slalom-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `slalom`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Run the Illinois agility course without touching a cone: round the far-left cone, back round the cone on the start line,
weave up and back through the centre cones, round the far-right cone and back over the finish line.

## Success criteria
A course 10 m long and 5 m wide on a sports floor: a free cone at each corner, and four centre cones on the centre line,
the first on the start line and then one every 3.3 m. The robot starts behind the start line, on the left half. The
path is judged on the pelvis. The referee's stages, in order:
- Far-left cone: the pelvis crosses the left side line's continuation beyond the far line, in either direction.
- Bottom cone, first time: the pelvis crosses the centre line before the start line, from left to right.
- Up 1-2, up 2-3, up 3-4: the pelvis crosses the centre line between the first and second centre cones from right to
  left, between the second and third from left to right, between the third and fourth from right to left.
- Top cone: it crosses the centre line beyond the fourth centre cone, from left to right.
- Down 3-4, down 2-3, down 1-2: between the fourth and third from right to left, the third and second from left to
  right, the second and first from right to left.
- Bottom cone, second time: before the start line, from left to right.
- Far-right cone: the pelvis crosses the right side line's continuation beyond the far line, in either direction.
- Finish: the leading point of the torso (not the head, arms, legs or feet) reaches the start line with the pelvis on
  the right half. The success is called at that moment.

Fouls (each fails the attempt): any part of the robot touching any of the eight cones; any crossing of the centre line
by the pelvis that is not the next one in this list, at any time. The generic fall rule is off: a fall does not end
the attempt, and the robot may get up and go on, but the pelvis below 0.4 m for 10 s in a row fails it. Time limit:
60 s (6,000 control steps).

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
