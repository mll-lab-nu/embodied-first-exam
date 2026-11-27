# Embodied Olympics · sumo (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-sumo-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Opponent | A second Unitree G1 (scripted): from 0.5 s it walks straight at the robot, arms forward at chest height, turning to face it |
| Instance | `sumo`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Win a sumo bout: make your opponent step out of the ring or touch down with anything but its feet before you do.

## Success criteria
One bout on a dohyo: a rigid clay mound 0.55 m high and 6.7 m square with a ring of straw bales whose inside edge is a
circle 4.55 m across. The opponent is a second Unitree G1 that starts behind the other starting line, facing the
robot. From t = 0.5 s it walks at its walking policy's largest forward command (0.8 m/s) straight at the robot,
turning at most 1.0 rad/s to face the robot's pelvis, with both arms stretched forward at chest height; it never grips
and never changes this plan. The referee's one stage is the win, and the success is called with it.

The decision is judged at every physics step (1 ms). A robot loses when any part of it touches the arena floor below
the mound, when any part touches the clay beyond the outside edge of the bales, or when any part other than its feet
touches the clay or a bale. The robot wins when the opponent loses this way first. The attempt fails:
- when the robot loses first, or when the robot's pelvis drops lower than 0.35 m above the clay;
- when both lose in the same physics step (no decision);
- when a foot of the robot touches the opponent's pelvis or torso (a forbidden kick);
- at the time limit with no decision: 30 s (3,000 control steps).
The generic fall rule is off; these rules replace it.

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
