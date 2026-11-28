# Embodied Olympics · paddle bounce (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-paddle-bounce-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `paddle_bounce`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Bounce the table-tennis ball on the paddle in your right hand 20 times, each a hit that sends it back up to the height
it was dropped from, without letting go of the paddle.

## Success criteria
A table tennis paddle starts closed in the robot's right hand; it is a separate body held by contact and friction
only. The ball rests in a dropper's cup, its centre 1.2 m above the floor, and falls at 2.0 s. The referee's stages, in
order: bounce 1 to bounce 20. The success is called at the 20th bounce.
- Bounce: a touch of the blade (either face) after which, before the ball touches the blade again, its centre rises
  at least 0.15 m above the height at which it left the blade and reaches at least 1.2 m above the floor, and which the
  ball leaves with at least 0.98 of the speed it reached the blade with (both taken at the height where the touch
  began). A rebound that rises enough but leaves slower is not counted and is not a fault.

Fouls (each fails the attempt): the paddle leaves the right hand (its handle not touching both the fingers and the
thumb or palm for more than 0.05 s); the paddle touches any part of the robot other than the right hand, or the floor;
the robot or the paddle touches the ball before it is dropped; after the drop the ball touches the floor, the robot,
the paddle's handle, or the dropper (from 0.1 s after the drop on); the ball comes back to the blade without having
risen that much; one touch lasts longer than 0.02 s. Fall (a failure at any time): the pelvis below 0.35 m, or any part
other than the feet on the floor. Time limit: 20 s (2,000 control steps).

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
