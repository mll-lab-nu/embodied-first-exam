# Embodied Olympics · bowling (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-bowling-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `bowling`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Bowl a strike: roll the ball down the lane from behind the foul line and knock down all ten pins.

## Success criteria
The lane runs 18.288 m from the foul line to the head pin, with a gutter on each side; ten pins stand in the usual
triangle. The ball starts pressed between the robot's palms; nothing can be gripped. The referee's stages, in order:
delivery, pins, strike.
- Before the release the ball may touch no part of the robot but the hands. The release is the ball's last touch of the
  robot before 0.05 s with no touch; after it no part of the robot may touch the ball (checked until the ball first
  touches a pin).
- Delivery: the released ball crosses the foul line.
- Pins: the ball touches a pin after the delivery. A ball that touches a gutter before that fails the attempt (a
  gutter ball).
- Strike: 5.0 s after the ball's first pin contact, all ten pins are down. A pin is down when it is tilted more than
  20 degrees or is no longer on the lane's surface. Fewer than ten pins down at that count fails the attempt.

Fouls (each fails the attempt at once): any part of the robot touches the lane, a gutter or anything else on or beyond
the foul line, at any time. Fall (a failure at any time before the count): the pelvis lower than 0.5 m above the
approach, or any part other than the feet on the approach or the floor. Time limit: 40 s (4,000 control steps).

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
