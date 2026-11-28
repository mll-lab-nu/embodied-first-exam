# Embodied Olympics · volleyball set (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-volleyball-set-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `volleyball_set`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Set the ball: with one overhead touch of your hands, send it high above the net and into the hitter's target along the
net.

## Success criteria
An official volleyball court (9.0 m by 9.0 m on each side of the net; the net's top 2.43 m high). The robot is the
setter, standing in its front zone facing along the net: the net 1.0 m to its right, the attack line 3.0 m from the
centre line to its left, the side line of position 2 3.0 m behind it. A volleyball (0.21 m across, 0.27 kg) is
tossed to it by a ball machine in the back court 3.0 s after the start and comes down above it. The referee's
stages, in order: set, above the net, in the target.
- Set: the ball's first contact after the toss, before it touches the floor, with the hands only (the parts beyond
  the wrists; one or both), after the ball has passed its highest point and with its centre above the top of the
  head (0.76 m above the waist joint along the trunk). Its contacts last at most 0.1 s; it is over when the ball has
  been clear of the robot for 0.03 s. The ball leaves the hands moving upward and at least 1.0 times as fast as just
  before they touched it.
- Above the net: the ball's centre then rises at least 1.0 m above the net's top.
- In the target: the ball's first contact with the floor is inside a circle of 1.0 m radius centred 1.0 m from the
  net on the robot's side and 1.0 m inside the side line ahead of the robot (the point under the ball's centre
  decides). The success is called at that contact.

Fouls (each fails the attempt at once):
- the robot touches the ball machine or the ball waiting in it;
- the ball touches the floor before or during the set;
- any part of the robot other than a hand touches the ball;
- the first contact comes before the ball has passed its highest point, or with the ball's centre not above the top of
  the head;
- the contacts last longer than 0.1 s (the ball held); the ball leaves the hands downward or slower than it came;
- a hand touches the ball again after the set;
- the ball does not rise 1.0 m above the net's top, or comes down outside the target;
- before the set the pelvis is farther from the net than the attack line (out of the front zone);
- the robot touches the net, an antenna or a post; a foot is on the floor wholly beyond the centre line.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the floor. Time limit:
10 s (1,000 control steps).

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
