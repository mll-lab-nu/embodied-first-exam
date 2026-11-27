# Embodied Olympics · tennis serve (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-tennis-serve-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `tennis_serve`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Serve: toss the ball with your left hand and hit it with the racket in your right hand over the net into the service box
diagonally opposite.

## Success criteria
An ITF singles court (23.77 m by 8.23 m; service lines 6.4 m from the net; the net 0.914 m high at its centre, 1.07 m
at the posts). Both hands are five-finger hands that hold things by contact and friction only: the ball starts in the
left hand, a free racket (0.685 m long, 0.30 kg) in the right. The robot serves from the right of the centre mark
into the far service box on the left of the centre line; a spare ball waits in a cup on a stand. The referee's
stages, in order: toss, strike, over the net, in.
- Toss: the ball is released, i.e. it has touched nothing at all for 0.1 s. At that moment the robot stands at rest
  in the server's position: both feet on the ground behind the baseline, between the extensions of the centre mark
  and the right sideline, neither foot having left the ground or moved more than 0.02 m in the last 0.5 s (so not
  before 0.5 s after the start).
- Strike: the racket hits the ball before it reaches the ground (any part of the racket counts), the ball having
  touched nothing of the robot for the last 0.1 s and moving at most 5.0 m/s when it reaches the racket. The hit must
  speed the ball up: 0.05 s after its last racket contact it is faster than when it reached the racket.
- Over the net: the ball's centre passes the net's plane between the posts, above the net's top edge.
- In: its first ground contact is inside the service box, the lines included (the point under the ball's centre
  decides; ground contacts less than 0.02 s apart are one). The success is called at that contact.
Let: a serve that touched the net and lands in the box does not count; the robot serves again under the same rules
with the spare ball, taken from its cup with the left hand. This happens at most once; a second let fails.

Fouls (each fails the attempt at once):
- the racket is unheld (its handle not touching both the right hand's fingers and its thumb or palm) for more than
  0.05 s, at any time;
- the racket touches the ball before it is released; the release happens when the robot is not at rest in the
  server's position;
- foot fault, from the release to the strike: a foot touches the baseline or the court, the ground beyond the
  sideline's or centre mark's extension, or the ground more than 0.3 m from where it stood at the release;
- the tossed ball touches the robot for more than 0.05 s (caught again), touches anything other than the robot and
  the racket, reaches the ground or passes the net unstruck;
- the racket strikes the ball less than 0.1 s after the robot last touched it, the ball reaches the racket faster
  than 5.0 m/s, or the hit does not speed it up;
- the racket touches the struck ball again (contacts less than 0.05 s apart are one hit) or stays on it longer than
  0.05 s;
- the served ball touches the robot (the hands included) or a net post, passes the net's plane anywhere but over the
  net, or first touches the ground on the robot's side or outside the service box;
- any part of the robot or the racket touches the net or a post; the robot or the racket touches the spare ball
  before a let.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part of the robot other than the feet on the
ground; the racket may touch the ground. Time limit: 20 s (2,000 control steps).

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
