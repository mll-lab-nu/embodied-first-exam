# Embodied Olympics · round off (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-round-off-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `round_off`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Do a round-off: go over onto your hands with a half turn, land on both feet together facing back the way you came, and
stand.

## Success criteria
The robot starts facing forwards in the middle of a 12 m by 12 m floor area. Before the hand support anything is free
(steps, a hop, a hurdle). The referee's stages, in order: hand support, landing, stand.
- Hand support: only the hands touch the floor, and the torso is upside down, its long axis (pelvis to neck) within
  45 degrees of pointing straight down.
- Landing: the feet come down together (the second foot within 0.1 s of the first; a foot off the floor again for more
  than 0.03 s before the other is down starts the landing over), the first foot down at most 0.7 s after the feet left
  the floor for the hand support; when both feet are down, no hand is on the floor and the pelvis and the torso each
  face back the way the robot came, within 45 degrees.
- Stand: for 1 s without a break, only the feet on the floor, the torso within 20 degrees of vertical, the pelvis
  slower than 0.35 m/s. The success is called when the 1 s is complete.

Fouls (each fails the attempt): after the hand support, one foot lands and the other does not follow within 0.1 s, or
no foot is down 0.7 s after the feet left the floor; a hand on the floor when both feet are down; landing not facing
back; a hand touching the floor after the landing; any part touching the floor outside the floor area. Fall (a failure
at any time, judged every physics step): the pelvis below 0.25 m, or any part other than the hands and feet on the
floor. Time limit: 30 s (3,000 control steps).

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
