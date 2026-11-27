# Embodied Olympics · vault (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-vault-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `vault`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Vault over the vaulting table: run up, push off it with your hands only, land on your feet on the mat and stand.

## Success criteria
A vault table, its top 1.35 m above the floor, 1.2 m long and 0.95 m wide, on a pedestal; its near edge is 25.0 m
ahead of where the pelvis starts. A hinged springboard (1.2 m by 0.6 m, rising to 0.22 m) stands 0.5 m before it;
using it is not required. The landing mat (6.0 m long, 2.5 m wide, 0.2 m thick, softer than the floor) begins at the
table's far edge. The hands are the wrist links and the palms (not the forearms). The referee's stages, in order:
hands on the table, over the table, landing, stand.
- Hands on the table: at least one hand touches the table's top surface (a contact within 0.02 m of the top plane;
  a hand against a side does not count).
- Over the table: the pelvis passes the table's far edge.
- Landing: then the feet touch the mat.
- Stand: the robot stands on the mat for 1.0 s without a break: only the feet on it, the torso within 20 degrees of
  upright, the pelvis no faster than 0.35 m/s. The success is called at the end of the 1.0 s.

Fouls (each fails the attempt at once):
- any part of the robot other than the hands touches the table or its pedestal;
- the pelvis is between the table's near and far edges without being higher than its top and within its width
  (under, beside or round it);
- the pelvis passes the far edge before a hand has touched the top;
- after the pelvis has passed the far edge, any part of the robot touches the floor, or a part other than the feet
  touches the mat before the stand is complete.
The generic fall rule is off: before the table any part may touch the floor and the springboard. Time limit: 80 s
(8,000 control steps).

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
