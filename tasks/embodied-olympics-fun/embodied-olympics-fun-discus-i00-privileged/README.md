# Embodied Olympics · discus (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-discus-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `discus`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Throw the discus from the circle so that it lands inside the sector at least 15 m out, then leave the circle from its
back half and stand.

## Success criteria
The 2.0 kg discus starts on the right hand; the circle is 2.5 m across inside its rim, and the sector is 34.92 degrees
wide, symmetric about the robot's starting direction. The referee's stages, in order: release, landing, exit.
- Before the release only the right hand (fingers, palm, wrist) may touch the discus, and the discus may not rest on
  the hand without the hand's hold (fingers and thumb or palm on it) for more than 0.2 s.
- Release: the hand's last hold before the discus has touched nothing of the robot for 0.03 s. After it the discus may
  not be held again; nothing but the right hand may touch it, the right hand only in the first 0.2 s, and those
  brushes may change its velocity by at most 0.5 m/s in all.
- Landing: the discus' first touch of the ground is inside the sector lines (on a line is out) and at least 15.0 m
  from the inside of the rim, measured along the line through the circle's centre. Otherwise the attempt fails.
- Exit: after the landing, the robot's first touch of the rim's top or the ground outside the circle is in the rear
  half (behind the line through the circle's centre across the throwing direction).
- The success is called when, after the exit, the robot has stood for 1.0 s without a break (only the feet on the
  ground, the torso within about 20 degrees of vertical, the pelvis slower than 0.35 m/s).

Fouls (each fails the attempt at once): the robot touches the rim's top (a contact within 0.003 m of it counts) or the
ground outside the circle before the discus has landed, or in the front half before the exit; any of the discus rules
above is broken. Fall (a failure at any time): the pelvis below 0.5 m above the circle's floor, or any part other than
the feet on the ground. Time limit: 60 s (6,000 control steps).

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
