# Embodied Olympics · sweeper jump (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-sweeper-jump-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `sweeper_jump`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Jump the sweeping boom 3 times in a row without being hit, then land on your podium and stand still before it comes
round again.

## Success criteria
The robot stands on a round podium 0.90 m across and 0.40 m high. A 50 kg foam boom 0.20 m thick, its axis 0.20 m
above the podium's top, turns counter-clockwise (seen from above) round a motion base at 8 rpm, once every 7.5 s,
driven by a motor of at most 450 N m; it reaches over the whole podium and is already turning at the start. The
referee's stages, in order: jump 1, jump 2, jump 3, landing, stand.
- A jump counts when the boom passes under both feet, and at the moment it passes each foot the sole of that foot is
  above the boom's top (0.30 m above the podium's top) and nothing of the robot touches anything. A foot the boom
  passes that is not above it, or a pass while the robot touches something, fails the attempt; so does the boom
  passing one foot and not the other within half a turn.
- Landing: after the third jump, the robot's first contact is made by the feet only; otherwise the attempt fails.
- Stand: the robot then stands for 1 s without a break with only its feet on the podium, the torso within about 20
  degrees of vertical, the pelvis slower than 0.35 m/s. The success is called when the 1 s is complete.

Fouls (each fails the attempt at once): the boom touches any part of the robot (a hit; grabbing it counts); any part
of the robot touches the bed round the podium, the motion base or another podium. Fall (a failure at any time): the
pelvis lower than 0.35 m above the podium's top, or any part other than the feet on the ground. Time limit: 30 s
(3,000 control steps).

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
