# Embodied Olympics · pole vault (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-pole-vault-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `pole_vault`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Pole vault: run up, plant the pole in the box, swing up on it and clear the bar without knocking it off.

## Success criteria
The robot carries a rigid 2.35 m pole in its right hand (three-finger hands that hold by contact and friction only).
A runway leads to the box; the bar rests 1.0 m above the ground on two pegs 4.3 m apart, 0.2 m beyond the zero line
(the box's stop board); the landing mat begins 0.15 m beyond the zero line. The referee's stages, in order: plant,
take-off, clearance, bar stays.
- Plant: the pole's tip is in the box while a hand grips the pole.
- Take-off: the robot leaves the ground after a run-up (the pelvis' forward speed averaged over the last 0.5 s before
  lift-off at least 2.5 m/s), with the pole at least 20 degrees from vertical at lift-off; then for at least 0.15 s of
  that flight nothing of the robot touches anything but the pole and the bar while a hand grips the pole higher than
  the pelvis and the pole's tip, in the box, carries at least half of the robot's weight.
- Clearance: in that same flight the pelvis and both ankle joints cross the plane of the bar's nearer edge between the
  pegs and higher than the bar's upper side (one that comes back over the plane has not passed it), and every part of
  the robot gets beyond that plane. The robot may touch the bar.
- Bar stays: 2 s after the landing (on any part of the body, with or without the pole) the bar is still on its pegs.
  The success is called then.

Fouls (each fails the attempt): the bar drops more than 0.05 m at any time, whoever knocked it; before the clearance,
anything of the robot or the pole touches the ground or the mats beyond the zero line; the pelvis or an ankle passes
the bar's plane outside the pegs or not higher than the bar; clearing the bar without such a take-off and hang; in the
flight, a hand holding the pole more than 0.05 m farther from its tip than the upper hand did at lift-off (climbing);
the hands touching the bar for more than 0.1 s in all. A fall is not a failure by itself: the generic fall rule is
off. Time limit: 60 s (6,000 control steps).

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
