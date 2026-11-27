# Embodied Olympics · double dutch (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-double-dutch-i00-realtime` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | realtime, slowdown 1 |
| Instance | `double_dutch`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Jump Double Dutch: get into the two turning ropes and jump them 10 times in a row, one rope per jump, without a rope
touching you, then land on your feet.

## Success criteria
Two machines turn two ropes in opposite directions, half a turn apart, at 1.1 turns per second, so that a rope passes
under the middle every 0.45 s; they are turning at the start and never stop. The robot starts outside the ropes. The
referee's stages, in order: entry, jump 1 to jump 10, landing.
- Entry: the pelvis enters the centre zone (within 0.35 m of the middle along the ropes' plane of turning, and 0.5 m
  across it). Leaving the zone after that fails the attempt.
- A jump counts when a rope passes under both feet while nothing of the robot touches the ground and the pelvis is in
  the centre zone, if that rope has passed over the head since it last passed under, and the flight is not the one of
  the last counted jump (one rope per jump).
- Landing: after the 10th counted jump, the robot's first contact with the floor is the feet only. The success is
  called then; a landing on anything else fails.

Fouls (each fails the attempt at once): a rope touches any part of the robot (a miss); a rope passes under a foot
while the robot is on the ground, or passes through the robot; the robot touches a turning machine. Fall (a failure at
any time): the pelvis below 0.35 m, or any part other than the feet on the floor. Time limit: 25 s (2,500 control
steps).

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
