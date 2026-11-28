# Embodied Olympics · breaking windmill (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-breaking-windmill-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `breaking_windmill`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Get down on the floor and do three windmills in a row, rolling over your back, shoulders and chest while your legs
circle above the floor.

## Success criteria
The referee's stages, in order: down, 1 windmill, 2 windmills, 3 windmills.
- Down: the torso or an upper arm touches the floor while no hip or leg part does. How the robot gets down is free.
- A windmill revolution is counted on the torso: its long axis (pelvis to neck) turns 360 degrees round the vertical
  while the torso rolls at least 0.85 of a full turn about that axis, both the same way round. Turning and rolling
  count only while the robot lies on the floor: the torso's long axis within 30 degrees of horizontal and the pelvis
  at most 0.45 m above the floor. The torso or an upper arm must touch the floor in each half of each revolution.
- During the windmills only the torso (with the head), upper arms, forearms and hands may touch the floor. The count
  goes back to zero when a hip or leg part (thighs, shins, feet) touches the floor, when the rotation reverses, or when
  a revolution of heading is completed without the roll or the floor touches above.
- The success is called when 3 revolutions are counted in a row.

Fouls (each fails the attempt): any part of the robot touches the floor outside the 8.0 m by 8.0 m field of play. The
generic fall rule is off. Time limit: 30 s (3,000 control steps).

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
