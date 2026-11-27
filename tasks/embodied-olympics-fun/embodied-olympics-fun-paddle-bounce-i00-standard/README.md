# Embodied Olympics · paddle bounce (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-paddle-bounce-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `paddle_bounce`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Bounce the table-tennis ball on the paddle in your right hand 20 times in a row, each time back up to the height it was
dropped from, without letting go of the paddle.

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
