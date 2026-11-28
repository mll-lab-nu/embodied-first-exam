# Embodied Olympics · layup (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-layup-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `layup`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Make a layup: with at most two steps, jump and let go of the ball close to the ring so that it drops into the basket.

## Success criteria
An official basket: ring 0.45 m inner diameter, top edge 3.05 m above the floor, in front of a backboard; a size-7
basketball starts in the robot's hands. The referee's stages, in order: approach, release in the air, through the ring.
- Approach: while the ball is in the robot's hands, its centre comes within 1.25 m (horizontally) of the ring's centre.
- Release in the air: the robot lets go (the last touch of a hand after which no hand has been on the ball for
  0.03 s) while it is in the air: nothing of it has touched anything but the ball for at least 0.05 s, after a take-off
  with the pelvis rising at 0.5 m/s or more, and the ball's centre is within 1.25 m (horizontally) of the ring's centre.
- Through the ring: after the release, the ball's centre goes down through the ring's plane inside the ring and on
  down to one ball diameter below it (off the backboard or not). The success is called then.

Fouls (each fails the attempt): travelling while the ball is in the robot's hands (more than 2 steps; a step is a foot
touching the floor after at least 0.03 s off it, both feet within 0.03 s count as one; the same foot twice in a row;
a foot sliding more than 0.2 m; a foot down again after the steps before the release); the ball touching the floor or
a part other than a hand while held; letting go with something on the floor, without such a take-off, or further than
1.25 m from the ring; any part touching the ball more than 0.05 s after the release; the ball touching the floor before
it is through; the ball coming up through the ring from below. Fall (a failure at any time): the pelvis below 0.35 m,
or any part other than the feet on the floor. Time limit: 15 s (1,500 control steps).

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
