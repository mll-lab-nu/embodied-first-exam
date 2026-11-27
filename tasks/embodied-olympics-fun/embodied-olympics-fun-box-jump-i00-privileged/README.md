# Embodied Olympics · box jump (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-box-jump-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `box_jump`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Jump onto the box in front of you from both feet, land on top with both feet and stand up straight on it.

## Success criteria
The box is a free 25 kg body, 0.61 m high, with a top 0.51 m by 0.76 m. The referee's stages, in order: take-off,
landing, stand.
- Take-off: the robot's first flight phase of at least 0.1 s. It counts only if nothing of the robot touched the box
  before it, each foot was on the floor within the last 0.1 s before lift-off, and the pelvis rose at least 0.1 m
  above its height at lift-off; otherwise the attempt fails.
- Landing: over the 0.5 s after the first contact, only the feet touch anything, and only the box's top face (each
  contact within 0.02 m of the top plane and pushing within 20 degrees of straight out of it); at the end of the 0.5 s
  both feet are on the top. Otherwise the attempt fails.
- Stand: for 2 s without a break, both feet on the top face and nothing else touching anything, the torso within 20
  degrees of vertical, the pelvis slower than 0.35 m/s and at least 1.0 m above the box's top. The success is called
  when the 2 s are complete.

Fouls (each fails the attempt at once): before the jump, any part other than the feet touching the floor, or anything
touching the box; after the take-off, any part touching the floor, or any part other than a foot touching the box. The
generic fall rule is off (no pelvis-height limit). Time limit: 20 s (2,000 control steps).

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
