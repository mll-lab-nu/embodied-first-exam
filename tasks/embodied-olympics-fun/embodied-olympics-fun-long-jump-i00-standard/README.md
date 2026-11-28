# Embodied Olympics · long jump (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-long-jump-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `long_jump`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Do a long jump: run up, take off behind the take-off line and land in the sand pit.

## Success criteria
A runway 40 m long and 1.22 m wide leads to the take-off line (x = 0, the pit-side edge of the take-off board) and a
sand pit 9 m long and 2.75 m wide that begins 1.0 m beyond the line. The referee's stages, in order: take-off,
landing.
- Take-off: the robot's first contact with the sand ends a flight (nothing of it touching anything for at least
  0.05 s) whose last ground contact before lift-off was within the runway's width and during which the pelvis rose at
  least 0.05 m above its height at lift-off. Taking off before the board is allowed.
- Landing: 2 s after the first sand contact the jump is complete. The mark is the point nearest the take-off line at
  which any part of the robot touched the sand in those 2 s; since the sand begins 1.0 m beyond the line, a valid jump
  is always at least 1.0 m. The success is called then.

Fouls (each fails the attempt): before the landing, a foot on the ground with any part of it on or over the take-off
line's plane; any part touching the ground at or beyond the line outside the sand; touching the sand without such a
flight, or after a flight that took off outside the runway's width or rose less than 0.05 m; in the 2 s after the
landing, touching the ground outside the pit nearer the take-off line than the mark; leaving the venue (any part on
the ground beyond the level area). The robot may land on any part of its body: the generic fall rule is off. Time
limit: 60 s (6,000 control steps).

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
