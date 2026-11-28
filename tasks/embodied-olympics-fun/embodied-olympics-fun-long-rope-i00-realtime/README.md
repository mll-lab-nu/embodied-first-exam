# Embodied Olympics · long rope (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-long-rope-i00-realtime` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | realtime, slowdown 1 |
| Instance | `long_rope`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Jump the long rope 10 times in a row without the rope touching you, then land on your feet and stand still.

## Success criteria
Two rope-turning machines, 3.6 m apart, turn a 6 m rope over and under the robot at a steady 1 revolution per second
from the start; they never stop. The referee's stages, in order: jump 1 to jump 10, landing, stand.
- Jump: the rope passes under both feet while nothing of the robot touches the ground (at the moment it passes under
  each foot), after it has passed over the head since the last counted jump. One jump per turn of the rope.
- Landing: after the 10th jump, the robot's first contact with the floor is made by the feet only.
- Stand: after the landing, the robot stands still for 0.5 s without a break: only the feet on the floor, the torso
  within about 20 degrees of vertical, the pelvis slower than 0.35 m/s. The success is called when the 0.5 s are
  complete. The rope keeps turning, so it must not touch the robot until then.

Fouls (each fails the attempt at once): the rope touches any part of the robot (a miss); the rope passes under a foot
that is on the ground, under only one foot before passing over the head again, or through the robot; the pelvis
leaves the centre zone (more than 0.5 m from the rope's axis forwards or backwards, or from the middle between the
machines sideways); the landing after the 10th jump is not on the feet only. Fall (a failure at any time): the pelvis
below 0.35 m, or any part other than the feet on the floor. Time limit: 20 s (2,000 control steps).

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
