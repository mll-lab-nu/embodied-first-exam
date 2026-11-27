# Embodied Olympics · bowling (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-bowling-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `bowling`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Bowl a strike: roll the ball down the lane from behind the foul line and knock down all ten pins.

## Success criteria
The lane runs 18.288 m from the foul line to the head pin, with a gutter on each side; ten pins stand in the usual
triangle. The ball starts pressed between the robot's palms; nothing can be gripped. The referee's stages, in order:
delivery, pins, strike.
- Before the release the ball may touch no part of the robot but the hands. The release is the ball's last touch of the
  robot before 0.05 s with no touch; after it no part of the robot may touch the ball (checked until the ball first
  touches a pin).
- Delivery: the released ball crosses the foul line.
- Pins: the ball touches a pin after the delivery. A ball that touches a gutter before that fails the attempt (a
  gutter ball).
- Strike: 5.0 s after the ball's first pin contact, all ten pins are down. A pin is down when it is tilted more than
  20 degrees or is no longer on the lane's surface. Fewer than ten pins down at that count fails the attempt.

Fouls (each fails the attempt at once): any part of the robot touches the lane, a gutter or anything else on or beyond
the foul line, at any time. Fall (a failure at any time before the count): the pelvis lower than 0.5 m above the
approach, or any part other than the feet on the approach or the floor. Time limit: 40 s (4,000 control steps).

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
