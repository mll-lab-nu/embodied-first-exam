# Embodied Olympics · standing long jump (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-standing-long-jump-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `standing_long_jump`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Do a standing long jump: from both feet, without a step, jump at least your own height (1.32 m) past the line, land on
your feet and stand.

## Success criteria
The robot stands with its feet side by side, their front ends 0.05 m behind the take-off line, facing the jump
direction. The jump is the first flight (no part of the robot on the ground) of at least 0.1 s. The referee's stages,
in order: take-off, landing, stand.
- Take-off: until the jump, no part of a foot on the ground is on or over the line (the whole foot counts, also its
  parts in the air); every ground contact of a foot is within 0.03 m of where that sole stood at the start (no run-up,
  no step); neither foot is off the ground for more than 0.05 s while the other is on it, so both feet leave within
  0.05 s of each other. Rising on the toes is allowed. The pelvis rises at least 0.05 m above its height at lift-off.
- Landing: the first contact after the flight is with the feet only. The mark is the point nearest the line at which
  any part of the robot touches the ground from that landing until the stand; it must stay at least 1.32 m beyond the
  line.
- Stand: steps after the landing are allowed; then for 1 s without a break, only the feet on the ground, the torso
  within 20 degrees of vertical, the pelvis slower than 0.35 m/s. The success is called when the 1 s is complete.

Fouls (each fails the attempt): a foot on or over the line, a step or shuffle, or one foot leaving the ground more than
0.05 s before the other, before the take-off; a flight whose pelvis does not rise 0.05 m; a landing not on the feet;
a mark short of 1.32 m. Fall (a failure at any time): the pelvis below 0.35 m, or any part other than the feet on the
ground. Time limit: 20 s (2,000 control steps).

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
