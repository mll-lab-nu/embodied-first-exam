# Embodied Olympics · table tennis return (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-table-tennis-return-i00-realtime` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | realtime, slowdown 1 |
| Opponent | A ball machine on the far side of the table (scripted), serving one fixed legal service at about 3 s |
| Instance | `table_tennis_return`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Return the serve: after it bounces once on your side, hit it with the paddle in your right hand onto the opponent's
side, without letting go of the paddle.

## Success criteria
An official table (2.74 m by 1.525 m, its playing surface 0.76 m above the floor, a net 0.1525 m high). The robot
holds a free racket (0.14 kg, a 0.15 m square blade on a 0.1 m handle) in its right hand by contact and friction
only. About 3.0 s after the start a ball machine on the far side serves one fixed legal service: the ball bounces on
the server's court, passes the net and bounces on the robot's court. The referee's stages, in order: bounce, strike,
opponent's court.
- Bounce: the ball bounces once on the robot's court (ball contacts with the table less than 0.02 s apart are one
  bounce).
- Strike: the ball is then struck with the racket's blade or the right hand; all such contacts within 0.05 s of the
  first are one strike.
- Opponent's court: after the strike, the ball's next table contact is on the opponent's half of the playing surface
  (directly or after touching the net; over or around the net). The success is called at that touch.

Fouls (each fails the attempt at once):
- the racket has not been held by the right hand's fingers and its thumb or palm for more than 0.05 s (dropped,
  thrown or slipped out); the racket touches any part of the robot other than the right hand, or the floor;
- the robot or the racket touches the ball before the service has left the machine, or before its bounce on the
  robot's court; the ball bounces a second time on the robot's court before the strike;
- anything other than the blade or the right hand touches the ball (the racket's handle included); the blade or the
  right hand touches the ball again more than 0.05 s after the first contact;
- after the strike the ball touches the robot's own court, the side of the table (the ball's centre below the playing
  surface) or the floor before the opponent's court; the ball touches the floor at any time;
- any part of the robot or the racket touches the net; the left hand touches the playing surface once the ball is in
  play;
- a service that touches the net or does not bounce first on the server's court and then on the robot's.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the floor. Anything
else of the robot, the racket included, may touch the table. Time limit: 8 s (800 control steps).

Graded: the live attempt, judged by the referee in the simulator service as it runs; nothing is replayed. The clock
does not stop: an attempt starts paused at the frozen start, and from the agent's first `submit` one control step runs
every 10 ms × S of wall time (slowdown S = 1) whether or not the agent sends anything; when the planned
commands run out the last ones are held. The referee's success call is an event: once it is made at some control step,
the attempt is a success. It is never shown to the agent and does not end the attempt: the physics goes on until the
agent's `/finish`, the attempt's time limit, or the end of the agent's time (2 h), and nothing after the call
undoes it. A failure the referee calls before any success (a foul, a fall, the physics diverging) ends the attempt at
once with 0. Reaching the time limit or the end of the session without a success call scores 0. The agent has
5 resets, each starting a new, paused attempt from the frozen start; only the last attempt (the one after the
last reset) is graded. After the agent's first command, a simulator error or a simulator crash inside a control step
is the agent's 0; anything before the first command, a killed service, a failed resume or a reset that does not
rebuild the scene is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 20 GiB |
| `sim` | 4 | 8 GiB | 8192 | 4 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any NVIDIA GPU with EGL (RTX 4090 / L4).

## License
The Embodied Olympics robot library and running-policy port ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics)
@ `7df999b`, a private repository) is released under the MIT License (`LICENSE.roboolympics` in the image); this
benchmark's venues and referees are MIT too. Third-party parts in the image: the Unitree G1 model and meshes from MuJoCo
Menagerie (BSD-3-Clause), the Unitree H1-2 model, meshes and walking policy and the G1 walking policy from
unitree_rl_gym (BSD-3-Clause), the G1 running policy from C1801SYQ/g1_running (Apache-2.0), FALCON's G1 walking policy
from LeCAR-Lab/FALCON (MIT) and the WBC-AGILE G1 walking policy from NVIDIA (Apache-2.0). No non-commercial terms apply.
