# Embodied Olympics · javelin (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-javelin-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `javelin`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Throw the javelin over your shoulder from behind the arc so that it lands point first inside the sector at least 20 m
out, then leave the runway behind the arc's end lines, or step back at least 4 m behind them, and stand still for 1 s.

## Success criteria
A javelin (0.6 kg, 2.21 m) starts held at its cord in the right hand. The runway is 4 m wide and ends at the arc, a
circle of 8 m radius; the sector is bounded by the lines from the arc's centre through the arc's ends (28.96 degrees
between them). The referee's stages, in order: release, landing, exit.
- Held: the cord touches the right hand's fingers and its thumb or palm (breaks up to 0.02 s are ignored). After the
  hold ends, only the right arm and hand may touch the javelin, for at most 0.20 s.
- Release: the javelin's last contact with the robot, once it has touched nothing of the robot for 0.02 s. At that
  last contact its centre of gravity is at least as high as the right shoulder joint.
- Landing: the javelin's head touches the ground before any other part of it, inside the sector lines (on a line is
  out), at least 20 m from the arc's inner edge (measured along the line through the arc's centre).
- Exit: after the landing, the robot touches the ground outside the runway behind the arc's end lines, or at least
  4 m behind the arc's ends.
- Then the robot stands (only the feet on the ground, the torso within 20 degrees of vertical, the pelvis at most
  0.35 m/s) for 1 s in a row.

Fouls (each fails the attempt): any part of the robot touches the arc, its end lines or the ground beyond them; the
robot touches a side line or the ground outside the runway (or behind its rear end) before the landing; the chest
turns more than 135 degrees away from the throwing direction before the release; the javelin touches the left arm or
hand before the release; after the hold ends it touches a part other than the right arm, or stays on the right arm
for more than 0.20 s; the release is lower than the shoulder; after the release the javelin is held again, touched
by a part other than the right arm, or touched by the right arm later than 0.20 s after the release or hard enough
to change its velocity by more than 0.5 m/s in all; it does not land head first, lands outside the sector, or lands
short of 20 m. Fall rule: on, the pelvis below 0.50 m or any part other than the feet on the ground. Time limit:
60 s (6,000 control steps).

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
