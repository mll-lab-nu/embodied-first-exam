# Embodied Olympics · first-time shot (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-first-time-shot-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `first_time_shot`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Shoot first time: with one touch of a foot, send the ball rolling across in front of you into the goal.

## Success criteria
The goal is 7.32 m wide between the posts and 2.44 m high under the bar, 11 m beyond the pass line; there is no
goalkeeper. A ball released down a ramp at 2 s rolls along the pass line from the robot's left to its right. The
referee's stages, in order: shot, goal.
- Shot: the ball's first contact with the robot after the release is made by a foot (the parts below the shin) while
  the ball's centre is between the lines of the two posts. Every contact until the ball has been clear of the robot
  for 0.03 s is the same touch; the touch lasts at most 0.15 s, and the ball leaves it at least as fast as it came and
  moving towards the goal line.
- Goal: the whole ball then crosses the goal line between the posts and under the bar. After the shot it may touch
  the ground, the posts and the bar.

Fouls (each fails the attempt): any part other than a foot touches the ball; the first touch is outside the lines of
the posts; the touch lasts longer than 0.15 s, or the ball leaves it slower than it came or not towards the goal line;
the robot touches the ball again after the shot; the pass rolls past the far post untouched; the ball crosses the goal
line outside the goal, or before the shot; after the shot the ball is slower than 0.1 m/s for 1 s; the robot touches
the ramp or its gate. Fall (a failure at any time): the pelvis below 0.35 m, or any part other than the feet on the
ground. Time limit: 15 s (1,500 control steps).

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
