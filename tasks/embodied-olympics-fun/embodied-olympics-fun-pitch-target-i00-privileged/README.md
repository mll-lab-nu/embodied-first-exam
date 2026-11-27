# Embodied Olympics · pitch target (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-pitch-target-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `pitch_target`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Pitch a strike: with a foot on the pitcher's plate, throw the baseball through the strike zone over home plate on the
fly.

## Success criteria
A baseball starts held in the robot's right hand (by contact and friction only). The robot stands on the pitcher's
plate on a mound whose top is 0.254 m above home plate; the plate's front edge is 18.44 m from the back point of home
plate. The strike zone is the rectangle above home plate's front edge, 0.432 m wide and from 0.46 m to 1.07 m above
home plate. The referee's stages, in order: release, strike.
- Release: the moment the ball last touched the robot, once it has then touched nothing of the robot for 0.02 s. It
  must come within 15 s of the start, with at least one foot in contact with the pitcher's plate (touching the mound
  with part of its sole over the plate).
- Strike: the ball's centre then crosses the plane of the zone inside the zone, before the ball has touched the
  ground. The success is called then.

Fouls (each fails the attempt): no release within 15 s; no foot on the plate at the release; the ball touches the
ground (the mound included) before home plate, also before the release; it crosses the plane outside the zone (a
ball); after the release the right hand holds it again, a part other than the right arm touches it, or the right arm
touches it later than 0.2 s after the release, or the right arm's touches in those 0.2 s change its velocity by more
than 0.5 m/s in all. Fall (a failure at any time before the call): the pelvis below 0.75 m above home plate's level,
or any part other than the feet on the ground or the mound. Time limit: 20 s (2,000 control steps).

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
