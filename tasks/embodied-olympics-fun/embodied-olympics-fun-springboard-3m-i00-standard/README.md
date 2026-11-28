# Embodied Olympics · 3 m springboard dive (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-springboard-3m-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `springboard_3m`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Dive from the 3 m springboard: take off from both feet, do a forward half somersault with your body straight, and go
into the water head first, straight and vertical.

## Success criteria
The robot stands at the end of a 3 m springboard facing the water; the board bends and springs back under it. The water
is not simulated (its surface is the plane z = 0, passed without resistance). The dive is a forward dive straight. The
referee's stages, in order: take-off, entry, under water.
- Take-off: the robot is in the air (both feet stayed on the board until then) and its centre of mass has risen at
  least 0.1 m above its height at the start.
- Entry: the first part to reach the water surface is a hand or the head; by then the body line (ankles' middle to
  shoulders' middle) has turned 180 degrees forwards, within 45 degrees, from the upright start; the middle of the
  palms at that moment is 0.5 m to 3.0 m in front of the board's tip (at rest) and within 0.5 m to either side of the
  line the robot faced at the start.
- Under water: the whole robot is below the surface, with the entry kept clean until then (below). The success is
  called then.

Through the entry: when the pelvis reaches the surface the body line is within 15 degrees of vertical, head down; the
shoulders' axis stays within 20 degrees of the board's width direction (no twist); both palms are at least 0.15 m
beyond the centre of the head along the body line, at most 0.2 m apart and each within 0.15 m of the body line. From
the moment the body line passes the horizontal until the dive is complete the robot is straight: hips and knees each
bent less than 20 degrees, the ankles at most 0.12 m apart, each ankle pitched at least 0.3 rad towards the toes.

Fouls (each fails the attempt): before the take-off, any part above the ankles touching the board or its stand,
anything touching the railings, a foot off the board for more than 0.1 s while the other is on it, or a flight of
0.1 s or more that lands on the board again (a double bounce); after the take-off, any touch of the board, its stand
or the railings; reaching the water without a take-off, feet first, outside the distances, or outside any limit
above. The generic fall rule is off. Time limit: 20 s (2,000 control steps).

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
