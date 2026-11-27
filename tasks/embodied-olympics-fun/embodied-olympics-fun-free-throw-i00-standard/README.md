# Embodied Olympics · free throw (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-free-throw-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `free_throw`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Shoot a free throw: from behind the free-throw line, shoot the ball into the basket, releasing it within 5 s.

## Success criteria
The ring (0.45 m inner diameter) has its top edge 3.05 m above the floor; the free-throw line's near edge is 4.225 m
from the point under the ring's centre. The ball starts between the robot's open hands. The referee's stages, in
order: release, through the ring.
- Release: the moment no hand is on the ball any more (gaps shorter than 0.03 s count as on it). A ball that slips
  out is released too, and the ball can be released only once. The release must come within 5 s.
- Through the ring: after the release, the ball's centre goes down through the ring's plane inside the ring and on
  down to one ball diameter below it, without coming back up in between.

Fouls (each fails the attempt): no release within 5 s; before the release, the ball touches a part of the robot other
than the hands, or touches the floor; until the ball has touched the ring or entered it, any part of the robot touches
the floor on or beyond the free-throw line's near edge or outside the 1.80 m free-throw semi-circle; any part of the
robot touches the ball more than 0.05 s after the release; the ball touches the floor before it is through; the ball's
centre comes up through the ring from below. Fall (a failure at any time): the pelvis below 0.35 m, or any part other
than the feet on the floor. Time limit: 12 s (1,200 control steps).

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
