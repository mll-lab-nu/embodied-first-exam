# Embodied Olympics · goalkeeper save (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-goalkeeper-save-i00-realtime` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | realtime, slowdown 1 |
| Opponent | Three ball machines on the penalty mark line (scripted), each shooting one penalty at the goal |
| Instance | `goalkeeper_save`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Keep goal: stop all 3 penalty kicks, with a foot on the goal line at each kick, and stay inside the goal area.

## Success criteria
The robot is the goalkeeper, on the goal line in the middle of a goal 7.32 m wide and 2.44 m high. Three ball
machines stand 11 m in front, 0.6 m apart (the middle one over the penalty mark). Each shoots one size 5 football at
20 m/s without spin: the first is fed at 6 s, the second 9 s later, the third 9 s after that (a shot is kicked when
its ball leaves the machine's wheels, about 0.1 s after the feed). They aim at points of the goal's plane, (sideways,
height) from the goal's centre with + to the robot's left: (-0.8 m, 0.9 m), (0.8 m, 1.1 m), (-0.5 m, 0.95 m). The
referee's stages, in order: save 1, save 2, save 3.
- At each kick: the robot is on its feet (something touches the ground, and nothing but the feet), part of one foot
  is touching or above the goal line between the posts, and the robot does not touch the posts, the crossbar or the
  net. After the kick it may move as it likes, use any part of itself, and go to ground.
- Save k: 2.5 s have passed since kick k without a goal. Save 3 is success.

Opponent and loss conditions: the shots. The attempt fails at the first goal (the whole ball over the goal line
between the posts and under the bar) by any of the three balls at any time after its kick, also a ball that comes
back off the robot or the posts. Fouls (each fails the attempt): the robot's position at a kick is not as above; it
touches a ball machine, or a ball before that ball's kick; its pelvis leaves the goal area (more than 5.5 m in front
of the goal line, more than 2.0 m behind it, or more than 9.16 m to either side of the goal's centre). The generic
fall rule is off. Time limit: 27 s (2,700 control steps).

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
