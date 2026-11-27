# Embodied Olympics · high jump (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-high-jump-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `high_jump`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Do a high jump: run up, take off from one foot and clear the bar without knocking it off.

## Success criteria
The bar (4.00 m long, 2.0 kg) rests with its upper side 1.00 m above the ground on two flat supports between uprights
4.02 m apart; a soft landing mat lies behind it. The approach is free. A flight is a time of at least 0.05 s in which
nothing of the robot touches anything but the bar. The referee's stages, in order: take-off, clearance, bar stays.
- Take-off: the jump is the flight in which the pelvis crosses the bar's plane. It must be from one foot: in the last
  0.15 s before lift-off the other foot presses on the ground with less than 5% of the robot's weight (or is off the
  ground), and nothing else of the robot touches the ground.
- Clearance: in that one flight the pelvis and both ankle joints cross the plane between the uprights and higher than
  the bar's upper side, and every part of the robot gets beyond the plane. A point that comes back over the plane must
  cross it again. At the landing the pelvis must have risen at least 0.08 m above its height at lift-off, and the
  landing must not touch the ground on the take-off side. The landing may be on any part of the body.
- Bar stays: 2 s after the clearance and the landing the bar lies on both supports, within 0.02 m of its resting
  place along the run and 0.005 m of its resting height, slower than 0.05 m/s and turning slower than 0.5 rad/s.

Fouls (each fails the attempt): the bar drops more than 0.05 m at any time, or is not on its supports at the judgement;
the robot touches the bar for more than 0.3 s in all, or the bar pushes it with more than 2.0 N s in all; the pelvis
or an ankle crosses the plane outside the uprights or not higher than the bar; the take-off is not from one foot; the
robot touches the ground or the mat beyond the plane before clearing the bar; the jump's flight ends before the bar is
cleared; the flight was not a jump (a rise under 0.08 m); after the clearance the landing touches the ground on the
take-off side. A fall is not a failure by itself; the generic fall rule is off. Time limit: 60 s (6,000 control steps).

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
