# Embodied Olympics · handstand (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-handstand-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `handstand`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Do a handstand: get up onto your hands, hold a straight handstand still for 2 s, then come back down onto your feet and
stand.

## Success criteria
A flat 12 m x 12 m floor. The referee's stages, in order: handstand, held 2 s, on the feet, stand.
- Handstand: only the hands touch the floor; the pelvis is above the middle of the hands' support and the ankles are
  above the pelvis; the line from the hands' middle to the pelvis and the line from the pelvis to the ankles each lean
  at most 45 degrees from vertical; the knees are bent at most 20 degrees and the hips at most 25 degrees.
- Held 2 s: that handstand, with the pelvis moving at most 0.15 m/s, for 2 s in a row. A touch of the floor by any part
  other than a hand restarts the count.
- On the feet: after the hold, only the feet touch the floor.
- Stand: the robot stands (only the feet on the floor, the torso within 20 degrees of vertical, the pelvis at most
  0.35 m/s) for 1 s in a row.

Fouls (each fails the attempt): the pelvis leaves the 12 m x 12 m area. Fall rule: on, with the hands allowed on the
floor as well as the feet: the pelvis below 0.25 m, or any other part on the floor, fails the attempt; it is checked
at every physics step, not only at every control step. Time limit: 30 s (3,000 control steps).

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
