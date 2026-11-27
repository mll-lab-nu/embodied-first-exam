# Embodied Olympics · three-ball juggling (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-juggle-three-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `juggle_three`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Juggle 3 balls in a cascade, throwing each from one hand to the other and catching it there, until you have made 10
catches in a row.

## Success criteria
Three balls (0.07 m, 0.13 kg): the blue ball starts in the left hand, the yellow ball in the right hand, and the red
ball in a small ball machine 1.0 m in front of the robot, which lobs it at about 2 s onto the left hand; its launch
counts as a throw by the right hand. The referee's stages, in order: first catch, half way (the fifth catch), ten
catches.
- A ball is in a hand from its catch (blue and yellow from the start) until it has touched nothing of that hand for
  0.02 s; the release is its last contact with the hand. A ball in a hand may touch nothing of the robot but that
  hand.
- A throw: after the release the ball, touching nothing of the robot, rises at least 0.30 m above the point where it
  left the hand; only the rise before it first touches the robot again counts.
- A catch: the other hand holds the ball between its thumb and its index or middle finger (both touching it) for
  0.05 s without a break, starting at most 0.15 s after the ball first touched the robot again.
- The order: the catches alternate between the hands, the left hand first, and take the balls in the order red, blue,
  yellow, red, and so on. The tenth catch is success.

Fouls (each fails the attempt): a ball touches the ground; the waiting red ball is touched (by the robot or a ball)
before its launch; a ball in a hand touches any other part of the robot (the other hand included); a ball in flight
touches a part other than a hand, or touches the hand that released it later than 0.10 s after the release; a ball
is caught by the hand that released it, or before it has risen 0.30 m; a ball that has touched the robot again is not
caught within 0.15 s; a catch is out of order (the wrong hand or the wrong ball). Fall rule: on, the pelvis below
0.35 m or any part other than the feet on the ground. Time limit: 20 s (2,000 control steps).

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
