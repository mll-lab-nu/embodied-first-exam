# Embodied Olympics · tennis return (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-tennis-return-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Opponent | A ball machine behind the far baseline (scripted), serving one ball at 30 m/s into the right service box at about 3 s |
| Instance | `tennis_return`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Return the serve: after it bounces once, hit it with the racket in your right hand over the net into the singles court,
without letting go of the racket.

## Success criteria
An ITF singles court (23.77 m by 8.23 m, measured to the outside of the lines; the net 0.914 m high at its centre,
1.07 m at the posts, which stand 0.914 m outside the sidelines). The robot holds a free racket (0.685 m long,
0.3 kg) in its right five-finger hand by contact and friction only. About 3.0 s after the start a ball machine
behind the far baseline serves the ball at 30 m/s into the robot's right service box; the ball is served when it has
left the machine's wheels. The referee's stages, in order: bounce, racket, over the net, in.
- Bounce: the ball bounces once on the robot's side (ground contacts less than 0.02 s apart are one bounce).
- Racket: the racket, held in the hand, hits the ball (any part of the racket counts; contacts less than 0.05 s
  apart are one hit).
- Over the net: the ball's centre then passes the net's plane towards the far side, above the net's top edge or
  outside a post (touching the net or a post on the way is allowed).
- In: the ball's next ground contact is inside the far half of the singles court, the lines included (the point under
  the ball's centre decides). The success is called at that contact.

Fouls (each fails the attempt at once):
- the racket is out of the hand for more than 0.05 s (its handle not touching both the hand's fingers and its thumb
  or palm);
- the robot or the racket touches the ball before it is served; after the serve the ball touches any part of the
  robot, the hand included;
- the racket hits the ball before its bounce; the ball bounces a second time on the robot's side before the hit;
- the racket hits the ball a second time, or one contact lasts longer than 0.05 s (a carry);
- the ball passes the net's plane between the posts below the net's top edge;
- after the hit the ball's next ground contact is on the robot's side or outside the far singles court;
- any part of the robot or the racket touches the net or a post, or the ground beyond the net's plane.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part of the robot other than the feet on the
ground; the racket may touch the ground on the robot's side. Time limit: 10 s (1,000 control steps).

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
