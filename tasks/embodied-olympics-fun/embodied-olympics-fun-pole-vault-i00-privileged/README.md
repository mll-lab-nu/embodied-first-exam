# Embodied Olympics · pole vault (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-pole-vault-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `pole_vault`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Pole vault: run up, plant the pole in the box, swing up on it and clear the bar without knocking it off.

## Success criteria
The robot carries a rigid 2.35 m pole in its right hand (three-finger hands that hold by contact and friction only).
A runway leads to the box; the bar rests 1.0 m above the ground on two pegs 4.3 m apart, 0.2 m beyond the zero line
(the box's stop board); the landing mat begins 0.15 m beyond the zero line. The referee's stages, in order: plant,
take-off, clearance, bar stays.
- Plant: the pole's tip is in the box while a hand grips the pole.
- Take-off: the robot leaves the ground after a run-up (the pelvis' forward speed averaged over the last 0.5 s before
  lift-off at least 2.5 m/s), with the pole at least 20 degrees from vertical at lift-off; then for at least 0.15 s of
  that flight nothing of the robot touches anything but the pole and the bar while a hand grips the pole higher than
  the pelvis and the pole's tip, in the box, carries at least half of the robot's weight.
- Clearance: in that same flight the pelvis and both ankle joints cross the plane of the bar's nearer edge between the
  pegs and higher than the bar's upper side (one that comes back over the plane has not passed it), and every part of
  the robot gets beyond that plane. The robot may touch the bar.
- Bar stays: 2 s after the landing (on any part of the body, with or without the pole) the bar is still on its pegs.
  The success is called then.

Fouls (each fails the attempt): the bar drops more than 0.05 m at any time, whoever knocked it; before the clearance,
anything of the robot or the pole touches the ground or the mats beyond the zero line; the pelvis or an ankle passes
the bar's plane outside the pegs or not higher than the bar; clearing the bar without such a take-off and hang; in the
flight, a hand holding the pole more than 0.05 m farther from its tip than the upper hand did at lift-off (climbing);
the hands touching the bar for more than 0.1 s in all. A fall is not a failure by itself: the generic fall rule is
off. Time limit: 60 s (6,000 control steps).

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
