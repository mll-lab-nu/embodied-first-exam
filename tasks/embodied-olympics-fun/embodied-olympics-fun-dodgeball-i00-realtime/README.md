# Embodied Olympics · dodgeball (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-dodgeball-i00-realtime` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | realtime, slowdown 1 |
| Opponent | Five ball machines in the opposing half (scripted), each aiming one dodgeball at the robot |
| Instance | `dodgeball`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Dodge the 5 balls the machines throw at you: do not let a live ball touch you, and stay on your feet inside your court.

## Success criteria
The robot stands in its own half of an 18 m by 9 m dodgeball court. Five ball machines in the opposing half, 3.0 m
beyond the centre line, each aim at the robot's pelvis (at 0.8 m height) and throw one ball at 14 m/s: the first at
2.0 s, the others 2.5 s apart. A thrown ball is live from the moment it leaves its machine until it touches the floor
or anything that is not the robot or a ball, or until 3.0 s after its throw; then it is dead, and that throw is
dodged. The referee's stages, in order: dodge 1 to dodge 5, one per ball. The success is called when the fifth ball is
dead without any live ball having touched the robot.

Fouls (each fails the attempt at once): a live ball touches any part of the robot; the robot touches a ball still in
its machine; any part of the robot touches a boundary line or the floor outside the court, or the opponents' neutral
zone line (7.0 m from their back line) or anything beyond it. Fall (a failure at any time): the pelvis below 0.35 m,
or any part other than the feet on the floor. Time limit: 15.5 s (1,550 control steps).

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
