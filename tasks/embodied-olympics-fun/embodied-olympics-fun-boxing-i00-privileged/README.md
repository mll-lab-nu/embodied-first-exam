# Embodied Olympics · boxing (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-boxing-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `boxing`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Punch the heavy bag once, hard, with the knuckles of your right fist on the marked band, then bring the fist back to
your guard and stand.

## Success criteria
A 30 kg heavy bag hangs by a chain in front of the robot, with a marked band from 1.2 m to 1.6 m above the floor. The
referee's stages, in order: strike, guard.
- Strike: the robot's first touch of the bag is the punch. Only the knuckle part of the right fist (the far 0.03 m of
  the hand's pad, along the forearm) may touch the bag, and the first contact must be inside the band. The touch lasts
  at most 0.1 s (it ends when fist and bag have been apart for 0.03 s), and the bag receives an impulse of at least
  12.0 N s (the change of its angular momentum about the hook, divided by the depth below the hook of the lowest point
  touched).
- Guard: after the strike, the right palm stays within 0.35 m of the right shoulder joint for 2 s without a break
  while the robot stands (only the feet on the ground, the torso within about 20 degrees of vertical, the pelvis
  slower than 0.35 m/s). The success is called when the 2 s are complete.

Fouls (each fails the attempt): anything other than the knuckle part of the right fist touches the bag; the punch
lands outside the band, is weaker than 12.0 N s, or lasts longer than 0.1 s (a push); anything touches the bag again
after the punch. Fall (a failure at any time): the pelvis below 0.5 m, or any part other than the feet on the floor.
Time limit: 15 s (1,500 control steps).

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
