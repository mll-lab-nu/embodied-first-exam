# Embodied Olympics · steeplechase (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-steeplechase-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `steeplechase`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Go over the steeplechase barrier and across the water pit behind it, then stand beyond the pit.

## Success criteria
The hurdle is fixed: a bar 0.127 m square and 3.66 m wide, its top 0.914 m above the track, its near face 10 m ahead
of the robot's start. Behind it lies a dry water pit 3.66 m long (from the hurdle's near face) and 3.66 m wide, 0.50 m
deep for its first 1.20 m, then sloping up to track level at the far edge. The referee's stages, in order: hurdle,
out of the water jump, stand.
- Hurdle: each time the pelvis or the centre of either foot crosses, going forward, the vertical plane through the
  middle of the bar, that point is higher than 0.914 m, and the pelvis is between the two ends of the bar; otherwise
  the attempt fails. The stage latches when all three points have crossed this way and the whole robot is past the
  bar. Hands and feet may touch or stand on the hurdle.
- Out of the water jump: the whole robot is beyond the pit's far edge.
- Stand: after that, still beyond the far edge, the robot stands for 1 s without a break: only the feet on the ground,
  the torso within 20 degrees of vertical, the pelvis slower than 0.35 m/s. The success is called when the 1 s is
  complete.

Fouls (each fails the attempt at once), from the moment the pelvis passes the bar until the robot is out of the water
jump: the pelvis outside the pit's width (more than 1.83 m to either side of the centre line); any part of the robot
touches the track's surface beside the pit (a contact less than 0.05 m below track level; the pit's side walls lower
down may be touched). The generic fall rule is off: any part may touch the pit's floor and walls and the track before
and beyond the pit. Time limit: 60 s (6,000 control steps).

Graded: the live attempt, judged by the referee in the simulator service as it runs; nothing is replayed. The referee's
success call is an event: once it is made at some control step, the attempt is a success. It is never shown to the
agent and does not end the attempt: the physics goes on until the agent's `/finish`, the attempt's time limit, or the
end of the agent's time (2 h), and nothing after the call undoes it. A failure the referee calls before any
success (a foul, a fall, the physics diverging) ends the attempt at once with 0. Reaching the time limit or the end of
the session without a success call scores 0. The agent has 5 resets, each starting a new attempt from the
frozen start; only the last attempt (the one after the last reset) is graded, and a success in an earlier attempt does
not count. A simulator error raised by the agent's own call ends the attempt with 0. An attempt that does not start
from the frozen instance, or a service crash outside the agent's calls, is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 10 GiB |
| `sim` | 4 | 5 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## License
The Embodied Olympics robot library and running-policy port ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics)
@ `7df999b`, a private repository) is released under the MIT License (`LICENSE.roboolympics` in the image); this
benchmark's venues and referees are MIT too. Third-party parts in the image: the Unitree G1 model and meshes from MuJoCo
Menagerie (BSD-3-Clause), the Unitree H1-2 model, meshes and walking policy and the G1 walking policy from
unitree_rl_gym (BSD-3-Clause), the G1 running policy from C1801SYQ/g1_running (Apache-2.0), FALCON's G1 walking policy
from LeCAR-Lab/FALCON (MIT) and the WBC-AGILE G1 walking policy from NVIDIA (Apache-2.0). No non-commercial terms apply.
