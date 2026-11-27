# Embodied Olympics · hurdles (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-hurdles-freestanding-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `hurdles_freestanding`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Run the 50 m hurdles: go over each of the four hurdles in your lane and reach the finish line, leaving at least one
hurdle standing.

## Success criteria
A 50 m lane, 1.22 m wide, with four loose hurdles (1.067 m high, 1.19 m wide, 10.9 kg, tipping over under about 3.8 kg
of push on the top bar): the first 13.72 m from the start line, then one every 9.14 m. Each hurdle is judged at the
place where it stands at the start, wherever it is later. The referee's stages, in order: hurdle 1, hurdle 2,
hurdle 3, hurdle 4, finish.
- A hurdle is gone over when the pelvis and both ankle joints cross the plane of its top bar forwards, each between
  the bar's ends, the pelvis higher than the hurdle's top and each foot higher than the lower edge of the top bar, in
  one flight: from the first of these crossings to the last, nothing of the robot touches anything but that hurdle's
  top bar. A point that comes back over the plane must cross it again. The hurdles are gone over in order.
- Finish: the leading point of the torso (trunk and head, not the arms or legs) reaches the finish line, with all four
  hurdles gone over.
- Knocking a hurdle over with a leg during the clearance (in the air, or with the pelvis over its plane) is allowed,
  but at least one hurdle must stay in its standing pose (no point of its top bar more than 0.10 m from where it
  stood).

Fouls (each fails the attempt): the pelvis or a foot crosses the next hurdle's plane beside it or too low; the robot
touches anything but the top bar between the first and the last crossing (stepping over); part of a leg is beside the
next hurdle (within 0.10 m of its plane, beyond the bar's ends) lower than its top; a hurdle leaves its standing pose
within 0.5 s of a touch by a hand, an arm, the trunk or the pelvis; a hurdle not yet gone over leaves its standing
pose other than by a leg during the clearance; the robot climbs on a standing hurdle (it pushes the robot up by more
than 100 N for longer than 0.15 s, or a part other than a leg on its top bar touches it at a crossing); every hurdle
has left its standing pose; the pelvis is more than 0.61 m from the lane's centre line; the torso reaches the finish
line before all hurdles are gone over; the pelvis is below 0.40 m for 10 s in a row. A fall by itself does not end the
race; the generic fall rule is off. Time limit: 140 s (14,000 control steps).

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
