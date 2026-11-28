# Embodied Olympics · golf putt (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-golf-putt-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `golf_putt`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Hole the putt: with one stroke of the putter in your right hand, roll the ball into the hole without letting go of the
putter.

## Success criteria
The ball lies on a flat green of stimp 10; the hole (0.108 m across, 0.1016 m deep, no flagstick) is 3 m away. A
putter (0.86 m, 0.50 kg) starts in the robot's right hand, held by contact and friction only. The referee's stages, in
order: stroke, holed.
- Stroke: the putter's head (any side of it) touches the ball. Every further contact of the head must come within
  0.2 s of the first, and all the head's contacts together last at most 0.03 s. At the first contact the feet must
  not touch the green on both sides of the line of play (the line through the ball's spot and the hole's centre) or
  on it.
- Holed: after the stroke the ball comes to rest (its centre moves less than 1 mm in 1 s) inside the hole, with the
  whole ball below the surface of the green.

Fouls (each fails the attempt): the putter is out of the right hand (its grip not touched by the hand's fingers and
by its thumb or palm) for more than 0.05 s, at any time; the putter touches any part of the robot other than the
hands; anything other than the putter's head touches the ball (the shaft, the grip, any part of the robot); the stance
is astride or on the line of play at the stroke; the head's contacts last longer than 0.03 s, or the head touches the
ball more than 0.2 s after the first contact; the ball comes to rest anywhere but in the hole (the lip and the green
beyond the hole included); the ball leaves the green. Fall (a failure at any time): the pelvis below 0.35 m, or any
part other than the feet on the ground (the putter may touch the green). Time limit: 30 s (3,000 control steps).

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
