# Embodied Olympics · high jump (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-high-jump-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `high_jump`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Do a high jump: run up, take off from one foot and clear the bar without knocking it off.

## Success criteria
The bar (4.00 m long, 2.0 kg) rests with its upper side 1.00 m above the ground on two flat supports between uprights
4.02 m apart; a soft landing mat lies behind it. The approach is free. A flight is a time of at least 0.05 s in which
nothing of the robot touches anything but the bar. The referee's stages, in order: take-off, clearance, bar stays.
- Take-off: the jump is the flight in which the pelvis crosses the bar's plane. It must be from one foot: in the last
  0.15 s before lift-off the other foot presses on the ground with less than 5% of the robot's weight (or is off the
  ground), and nothing else of the robot touches the ground.
- Clearance: in that one flight the pelvis and both ankle joints cross the plane between the uprights and higher than
  the bar's upper side, and every part of the robot gets beyond the plane. A point that comes back over the plane must
  cross it again. At the landing the pelvis must have risen at least 0.08 m above its height at lift-off, and the
  landing must not touch the ground on the take-off side. The landing may be on any part of the body.
- Bar stays: 2 s after the clearance and the landing the bar lies on both supports, within 0.02 m of its resting
  place along the run and 0.005 m of its resting height, slower than 0.05 m/s and turning slower than 0.5 rad/s.

Fouls (each fails the attempt): the bar drops more than 0.05 m at any time, or is not on its supports at the judgement;
the robot touches the bar for more than 0.3 s in all, or the bar pushes it with more than 2.0 N s in all; the pelvis
or an ankle crosses the plane outside the uprights or not higher than the bar; the take-off is not from one foot; the
robot touches the ground or the mat beyond the plane before clearing the bar; the jump's flight ends before the bar is
cleared; the flight was not a jump (a rise under 0.08 m); after the clearance the landing touches the ground on the
take-off side. A fall is not a failure by itself; the generic fall rule is off. Time limit: 60 s (6,000 control steps).

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
