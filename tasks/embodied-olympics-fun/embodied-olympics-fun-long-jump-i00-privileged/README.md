# Embodied Olympics · long jump (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-long-jump-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `long_jump`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Do a long jump: run up, take off behind the take-off line and land in the sand pit.

## Success criteria
A runway 40 m long and 1.22 m wide leads to the take-off line (x = 0, the pit-side edge of the take-off board) and a
sand pit 9 m long and 2.75 m wide that begins 1.0 m beyond the line. The referee's stages, in order: take-off,
landing.
- Take-off: the robot's first contact with the sand ends a flight (nothing of it touching anything for at least
  0.05 s) whose last ground contact before lift-off was within the runway's width and during which the pelvis rose at
  least 0.05 m above its height at lift-off. Taking off before the board is allowed.
- Landing: 2 s after the first sand contact the jump is complete. The mark is the point nearest the take-off line at
  which any part of the robot touched the sand in those 2 s; since the sand begins 1.0 m beyond the line, a valid jump
  is always at least 1.0 m. The success is called then.

Fouls (each fails the attempt): before the landing, a foot on the ground with any part of it on or over the take-off
line's plane; any part touching the ground at or beyond the line outside the sand; touching the sand without such a
flight, or after a flight that took off outside the runway's width or rose less than 0.05 m; in the 2 s after the
landing, touching the ground outside the pit nearer the take-off line than the mark; leaving the venue (any part on
the ground beyond the level area). The robot may land on any part of its body: the generic fall rule is off. Time
limit: 60 s (6,000 control steps).

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
