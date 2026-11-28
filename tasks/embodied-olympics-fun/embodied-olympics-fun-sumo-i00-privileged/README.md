# Embodied Olympics · sumo (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-sumo-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Opponent | A second Unitree G1 (scripted): from 0.5 s it walks straight at the robot, arms forward at chest height, turning to face it |
| Instance | `sumo`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Win a sumo bout: make your opponent step out of the ring or touch down with anything but its feet before you do.

## Success criteria
One bout on a dohyo: a rigid clay mound 0.55 m high and 6.7 m square with a ring of straw bales whose inside edge is a
circle 4.55 m across. The opponent is a second Unitree G1 that starts behind the other starting line, facing the
robot. From t = 0.5 s it walks at its walking policy's largest forward command (0.8 m/s) straight at the robot,
turning at most 1.0 rad/s to face the robot's pelvis, with both arms stretched forward at chest height; it never grips
and never changes this plan. The referee's one stage is the win, and the success is called with it.

The decision is judged at every physics step (1 ms). A robot loses when any part of it touches the arena floor below
the mound, when any part touches the clay beyond the outside edge of the bales, or when any part other than its feet
touches the clay or a bale. The robot wins when the opponent loses this way first. The attempt fails:
- when the robot loses first, or when the robot's pelvis drops lower than 0.35 m above the clay;
- when both lose in the same physics step (no decision);
- when a foot of the robot touches the opponent's pelvis or torso (a forbidden kick);
- at the time limit with no decision: 30 s (3,000 control steps).
The generic fall rule is off; these rules replace it.

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
