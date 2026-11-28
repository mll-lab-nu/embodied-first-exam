# Embodied Olympics · balance beam (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-balance-beam-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `balance_beam`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Walk along the balance beam to its far, yellow end and stand there, touching the beam only with your feet.

## Success criteria
The beam is 5.00 m long and 0.10 m wide, its top 1.25 m above the floor; the robot starts on the near end. The
referee's stages, in order: half way, far end, stand.
- Half way: both feet touch the beam and every point where they touch it is at least 2.5 m from the near end.
- Far end: both feet touch the beam and every point where they touch it is inside the far end, the last 0.50 m.
- Stand: for 2 s without a break the robot stands there: both feet in the far end, only the feet touching the beam,
  the torso within 20 degrees of vertical, the pelvis slower than 0.35 m/s. The success is called when the 2 s are
  complete.

Fouls (each fails the attempt at once): any part of the robot touches the floor or the beam's supports; any part other
than a foot touches the beam. A hop off the beam with both feet is allowed if the robot lands on it on its feet. The
generic fall rule is off; these fouls replace it. Time limit: 90 s (9,000 control steps).

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
