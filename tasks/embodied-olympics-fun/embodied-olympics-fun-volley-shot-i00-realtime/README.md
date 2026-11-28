# Embodied Olympics · volley shot (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-volley-shot-i00-realtime` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | realtime, slowdown 1 |
| Instance | `volley_shot`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Volley the cross into the goal: strike it with a foot before it touches the ground and send it past the goalkeeper
dummy.

## Success criteria
The robot stands on the penalty mark facing the goal, whose line is 11.0 m ahead; the goal is 7.32 m wide between
the posts and 2.44 m high under the crossbar (posts and bar 0.12 m thick). A goalkeeper dummy stands on the goal line
at the centre of the goal. A size-5 football (0.22 m across, 0.43 kg) waits in a ball machine on the left wing, 20.0
m from the robot; about 3.0 s after the start the machine crosses it: a lofted ball with backspin that comes down in
front of the robot. The referee's stages, in order: volley, goal.
- Volley: the ball's first contact after the cross is with a foot or an ankle (the parts below the shin), before the
  ball has touched the ground. Every contact within 0.15 s of the first belongs to the one strike, which is over when
  the ball has been clear of the robot for 0.03 s; the ball leaves the foot at least 1.0 times as fast as just before
  the foot touched it.
- Goal: the whole ball is then over the goal line, its centre between the posts and under the bar at that moment.
  After the strike it may touch the ground, the posts, the bar and the dummy. The success is called at that moment.

Fouls (each fails the attempt at once):
- the ball touches the ground before the strike;
- any part of the robot other than a foot or an ankle touches the ball, at any time;
- the strike's contacts last longer than 0.15 s; the ball leaves the foot slower than it came;
- a foot or an ankle touches the ball again after the strike;
- the whole ball crosses the goal line outside the goal, or crosses it before the volley;
- after the strike the ball has been slower than 0.1 m/s for 1.0 s without a goal;
- before the cross has left the machine: the pelvis comes within 9.15 m of the machine (measured along the ground),
  or the robot touches the machine or the waiting ball.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the ground. Time limit:
10 s (1,000 control steps).

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
