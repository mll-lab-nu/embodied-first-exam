# Embodied Olympics · vertical jump (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-vertical-jump-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `vertical_jump`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Jump straight up from both feet without a step, touch the vane above you with a hand, land on your feet and stand.

## Success criteria
The robot's standing reach (the top of a hand, flat-footed, legs straight, arm stretched up) is 1.66 m. A light vane
(0.05 kg, 0.9 m long from the robot's left to its right, 0.08 m wide) hangs over it with its underside 0.3 m above
that, hinged at its left end so that it swings away when touched, on a stand (a post and a base plate). The jump is
the robot's first flight (nothing of it touching the ground or the stand) of at least 0.1 s. The referee's stages,
in order: take-off, touch, landing, stand.
- Take-off: until the jump, every point where a foot touches the ground lies within 0.03 m of where that sole stood
  at t = 0, and neither foot is off the ground for more than 0.05 s while the other is on it (a two-foot take-off;
  rising on the toes is allowed). In the flight the pelvis rises at least 0.05 m above its height at lift-off.
- Touch: during that flight a hand (the fist or the wrist beyond the forearm) touches the vane.
- Landing: the first contact after the flight is with the feet only.
- Stand: afterwards (stepping is allowed) the robot stands for 1.0 s without a break: only the feet on the ground,
  the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. The success is called at the end of the
  1.0 s.

Fouls (each fails the attempt at once):
- before the take-off, a step or shuffle (a foot contact more than 0.03 m from its starting place), or one foot off
  the ground for more than 0.05 s while the other is on it;
- before the landing, a touch of the vane by any part other than a hand, or outside the jump's flight;
- any touch of the stand (its post or its base plate), also after the landing;
- a jump in which the pelvis rises less than 0.05 m, a jump that lands without having touched the vane, or a landing
  that is not on the feet only.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the ground. Time limit:
20 s (2,000 control steps).

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
