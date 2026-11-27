# Embodied Olympics · vault (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-vault-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `vault`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Vault over the vaulting table: run up, push off it with your hands only, land on your feet on the mat and stand.

## Success criteria
A vault table, its top 1.35 m above the floor, 1.2 m long and 0.95 m wide, on a pedestal; its near edge is 25.0 m
ahead of where the pelvis starts. A hinged springboard (1.2 m by 0.6 m, rising to 0.22 m) stands 0.5 m before it;
using it is not required. The landing mat (6.0 m long, 2.5 m wide, 0.2 m thick, softer than the floor) begins at the
table's far edge. The hands are the wrist links and the palms (not the forearms). The referee's stages, in order:
hands on the table, over the table, landing, stand.
- Hands on the table: at least one hand touches the table's top surface (a contact within 0.02 m of the top plane;
  a hand against a side does not count).
- Over the table: the pelvis passes the table's far edge.
- Landing: then the feet touch the mat.
- Stand: the robot stands on the mat for 1.0 s without a break: only the feet on it, the torso within 20 degrees of
  upright, the pelvis no faster than 0.35 m/s. The success is called at the end of the 1.0 s.

Fouls (each fails the attempt at once):
- any part of the robot other than the hands touches the table or its pedestal;
- the pelvis is between the table's near and far edges without being higher than its top and within its width
  (under, beside or round it);
- the pelvis passes the far edge before a hand has touched the top;
- after the pelvis has passed the far edge, any part of the robot touches the floor, or a part other than the feet
  touches the mat before the stand is complete.
The generic fall rule is off: before the table any part may touch the floor and the springboard. Time limit: 80 s
(8,000 control steps).

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
