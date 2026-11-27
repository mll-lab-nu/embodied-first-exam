# Embodied Olympics · badminton serve (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-badminton-serve-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `badminton_serve`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Serve the shuttle: from your right service court, let it go from your left hand and hit it, cork first and below 1.15 m,
with the racket in your right hand over the net into the service court diagonally opposite.

## Success criteria
A BWF court, singles. The shuttle starts held by its feathers in the left hand; the racket is held in the right hand
by contact and friction. The robot serves from its right service court into the receiver's right service court,
diagonally opposite. The referee's stages, in order: release, hit, over the net, in.
- Racket, at all times: it stays in the right hand (a break of more than 0.05 s is a fault) and never touches the
  floor, the net or a post.
- Release: the left hand lets the shuttle go; it is let go once it has touched nothing of the robot for 0.03 s. Before
  that the racket may not touch it; after it nothing of the robot but the racket may touch it.
- Hit: the racket hits the shuttle before it reaches the floor, the net or the net's plane. At the first instant of
  contact the cork base touches the racket, the whole shuttle is lower than 1.15 m, the shuttle moves at most 4.0 m/s,
  and the racket head is in a forward movement (its speed towards the net rose above 0.5 m/s and has not fallen below
  0.1 m/s). The service starts at the earlier of the release and the start of that movement; a forward movement that
  starts after the release and stops before the hit is a fault. From the start of the service to the hit, both feet
  stand inside the server's service court, touching neither its lines nor anything outside it, each foot on the floor
  all the time (gaps of at most 0.02 s) and moving at most 0.03 m. The hit is one contact (contacts less than 0.03 s
  apart are one), lasts at most 0.02 s, and when it is over the shuttle is faster than when it reached the racket and
  rising.
- Over the net: the shuttle passes the net's plane above the net's top edge, between the posts (it may touch the net).
- In: its first contact with the floor is inside the receiver's right service court, lines included. The success is
  called then.

Fouls (each fails the attempt at once): any rule above broken; a second hit; the shuttle touching the robot after the
hit, touching a post, passing through or under the net or outside the posts, or landing on the robot's side or
outside that service court; any part of the robot touching the net or a post. Fall (a failure at any time): the pelvis
below 0.35 m, or any part other than the feet on the floor. Time limit: 15 s (1,500 control steps).

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
