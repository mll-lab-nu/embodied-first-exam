# Embodied Olympics · juggling on the head (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-juggling-head-i00-realtime` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | realtime, slowdown 1 |
| Instance | `juggling_head`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Keep the football in the air with 10 headers in a row, touching it only with your head and never letting it touch the
ground.

## Success criteria
The robot stands in the middle of a 4.572 m x 4.572 m grid on grass. A ball machine 1.0 m in front of it opens its
gate at 1.0 s and lobs a size 5 football onto the robot's head. The referee's stages, in order: header 1, header 2,
..., header 10.
- A touch is contact of the ball with the head; contacts less than 0.05 s apart are one touch. A touch lasts at most
  0.05 s.
- A touch counts as a header when, before anything touches the ball again, its centre has risen at least 0.22 m above
  its height at the start of the touch, and it left the touch with at least 0.95 times the speed it came in with
  (the first touch too). A slower touch is not counted, and is not a fault.

Fouls (each fails the attempt): the robot touches the ball or the machine before the ball has left the machine; the
ball touches the ground or the machine; any part other than the head touches the ball; a touch lasts longer than
0.05 s; the ball is touched again before it has risen 0.22 m; an ankle leaves the grid. Fall rule: on, the pelvis
below 0.35 m or any part other than the feet on the ground. Time limit: 60 s (6,000 control steps).

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
