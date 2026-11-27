# Embodied Olympics · dribble slalom (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-dribble-slalom-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `dribble_slalom`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Dribble the football out through the six cones, passing each on the side of its yellow mark, round the last one and back
the other way over the start line, keeping the ball within 2 m of you and touching no cone.

## Success criteria
A football lies ahead of the robot, behind a start line; six free-standing cones stand on the robot's forward line, the
first 2.0 m beyond the start line and then every 2.0 m. Each cone has a plane through it, square to the course. The
referee's stages, in order: out 1 to out 6, back 6 to back 1, finish.
- Out: the ball's centre and the pelvis each cross the plane of cone 1 to the robot's starting left, cone 2 to its
  right, and so on alternately to cone 6 (to the right).
- Back: round cone 6, then the planes of cones 6 to 1 again, each on its other side (cone 6 to the left as seen from
  the start, cone 5 to the right, and so on, cone 1 to the right).
- For each plane, the first crossing in the direction of travel after the previous plane decides, for the ball and the
  pelvis separately; a stage latches when both have passed that plane on the correct side.
- Finish: after all twelve planes, the whole ball and the pelvis are back over the start line. The success is called
  then.

Fouls (each fails the attempt at once): the ball or the pelvis crosses a plane on the wrong side; the ball's centre is
more than 2.0 m from the pelvis, measured along the ground; the robot or the ball touches a cone; a hand or arm touches
the ball (any other part may play it). Fall (a failure at any time): the pelvis below 0.35 m, or any part other than
the feet on the ground. Time limit: 90 s (9,000 control steps).

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
