# Embodied Olympics · volleyball spike (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-volleyball-spike-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `volleyball_spike`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Spike the set: jump and hit the ball with a hand above the net down into the opponent's court, then land on your feet
without touching the net and stand.

## Success criteria
An official volleyball court (9.0 m by 9.0 m on each side of the net; the net's top 2.43 m high, an antenna above each
side line). The robot is the outside hitter, standing on its attack line facing the net 3.0 m ahead, the left side line
1.0 m to its left. A volleyball (0.21 m across, 0.27 kg) is set by a ball machine from the robot's right 3.0 s after the
start; it rises to about 4.5 m and comes down 0.5 m from the net in front of the robot. The referee's stages, in order:
spike, over the net, in the court, landing.
- Spike: the ball's first contact after the set, before it touches the floor, is with a hand (the parts beyond the
  wrist; one or both), after the ball has passed its highest point, at contact points all higher than the net's top,
  while the robot is in the air (nothing of it touching the floor or anything else). Its contacts last at most 0.1 s
  (over when the ball has been clear of the robot for 0.03 s); the ball leaves the hand moving downward and at least 1.0
  times as fast as just before the hand touched it.
- Over the net: the ball's centre crosses the net's plane above the net's top and between the side lines (it may touch
  the net).
- In the court: the ball's first contact with the floor is in the opponent's court (9.0 m by 9.0 m, lines included).
  From then on the ball is dead and what it touches is not judged.
- Landing: the flight of the spike was a jump (when it lands, the pelvis had risen at least 0.1 m above its height when
  the feet left the floor), and the robot then stands for 1.0 s without a break: only the feet on the floor, the trunk
  within about 20 degrees of upright, the pelvis slower than 0.35 m/s. The success is called at the end of the 1.0 s.

Fouls (each fails the attempt at once):
- the robot touches the ball machine or the ball waiting in it;
- the ball touches the floor before the spike;
- any part of the robot other than a hand touches the ball;
- the first contact comes before the ball has passed its highest point, from the floor, with a contact point at or below
  the net's top, or in a flight in which the pelvis does not rise 0.1 m;
- the contacts last longer than 0.1 s; the ball leaves the hand upward or slower than it came;
- a hand touches the ball again;
- the ball touches an antenna, crosses the net's plane before the spike, under the net's top or outside the side lines,
  or lands anywhere but in the opponent's court;
- the robot touches the net, an antenna or a post at any time; a foot is on the floor wholly beyond the centre line.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the floor. Time limit: 12
s (1,200 control steps).

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
