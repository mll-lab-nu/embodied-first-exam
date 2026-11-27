# Embodied Olympics · backflip (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-backflip-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `backflip`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Do a standing backflip: jump, turn a full backward somersault in the air, land on your feet and stand still.

## Success criteria
The referee's stages, in order: take-off, full turn, landing, stand.
- Take-off: the robot's first flight phase of at least 0.2 s (nothing of the robot touches anything). At lift-off the
  last parts on the ground must be the feet alone; otherwise the attempt fails. Shorter hops are ignored.
- Full turn: during that flight the pelvis turns at least 300 degrees backwards about the horizontal axis that was its
  left-right axis at lift-off. Only rotation while airborne counts.
- Landing: the first touch after the flight is made by the feet only. Landing with less than 300 degrees turned, or
  touching down with any other part, fails.
- Stand: after the landing, the robot stands for 2 s without a break: only the feet on the ground, the torso within
  20 degrees of vertical, the pelvis slower than 0.35 m/s. The success is called when the 2 s are complete.

Fall (a failure at any time): any part other than a foot touches the ground, or the pelvis is below 0.20 m. Time
limit: 20 s (2,000 control steps).

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
