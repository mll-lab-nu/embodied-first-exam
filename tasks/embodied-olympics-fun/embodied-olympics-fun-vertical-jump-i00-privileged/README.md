# Embodied Olympics · vertical jump (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-vertical-jump-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `vertical_jump`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Jump straight up from both feet without a step, touch the vane above you with a hand, land on your feet and stand.

## Success criteria
The robot's standing reach (the top of a hand, flat-footed, legs straight, arm stretched up) is 1.66 m. A light vane
(0.05 kg, 0.9 m long from the robot's left to its right, 0.08 m wide) hangs over it with its underside 0.3 m above
that, hinged at its left end so that it swings away when touched, on a stand (a post and a base plate). The jump is
the robot's first flight (nothing of it touching the ground or the stand) of at least 0.1 s. The referee's stages,
in order: take-off, touch, landing, stand.
- Take-off: until the jump, every point where a foot touches the ground lies within 0.03 m of where that sole stood
  at t = 0, and neither foot is off the ground for more than 0.05 s while the other is on it (a two-foot take-off;
  rising on the toes is allowed). In the flight the pelvis rises at least 0.05 m above its height at lift-off.
- Touch: during that flight a hand (the fist or the wrist beyond the forearm) touches the vane.
- Landing: the first contact after the flight is with the feet only.
- Stand: afterwards (stepping is allowed) the robot stands for 1.0 s without a break: only the feet on the ground,
  the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. The success is called at the end of the
  1.0 s.

Fouls (each fails the attempt at once):
- before the take-off, a step or shuffle (a foot contact more than 0.03 m from its starting place), or one foot off
  the ground for more than 0.05 s while the other is on it;
- before the landing, a touch of the vane by any part other than a hand, or outside the jump's flight;
- any touch of the stand (its post or its base plate), also after the landing;
- a jump in which the pelvis rises less than 0.05 m, a jump that lands without having touched the vane, or a landing
  that is not on the feet only.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the ground. Time limit:
20 s (2,000 control steps).

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
