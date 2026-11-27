# Embodied Olympics · breaking windmill (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-breaking-windmill-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `breaking_windmill`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Get down on the floor and do three windmills in a row, rolling over your back, shoulders and chest while your legs
circle above the floor.

## Success criteria
The referee's stages, in order: down, 1 windmill, 2 windmills, 3 windmills.
- Down: the torso or an upper arm touches the floor while no hip or leg part does. How the robot gets down is free.
- A windmill revolution is counted on the torso: its long axis (pelvis to neck) turns 360 degrees round the vertical
  while the torso rolls at least 0.85 of a full turn about that axis, both the same way round. Turning and rolling
  count only while the robot lies on the floor: the torso's long axis within 30 degrees of horizontal and the pelvis
  at most 0.45 m above the floor. The torso or an upper arm must touch the floor in each half of each revolution.
- During the windmills only the torso (with the head), upper arms, forearms and hands may touch the floor. The count
  goes back to zero when a hip or leg part (thighs, shins, feet) touches the floor, when the rotation reverses, or when
  a revolution of heading is completed without the roll or the floor touches above.
- The success is called when 3 revolutions are counted in a row.

Fouls (each fails the attempt): any part of the robot touches the floor outside the 8.0 m by 8.0 m field of play. The
generic fall rule is off. Time limit: 30 s (3,000 control steps).

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
