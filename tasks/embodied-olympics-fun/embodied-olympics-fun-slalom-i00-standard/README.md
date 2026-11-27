# Embodied Olympics · Illinois agility run (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-slalom-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `slalom`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Run the Illinois agility course without touching a cone: round the far-left cone, back round the cone on the start line,
weave up and back through the centre cones, round the far-right cone and back over the finish line.

## Success criteria
A course 10 m long and 5 m wide on a sports floor: a free cone at each corner, and four centre cones on the centre line,
the first on the start line and then one every 3.3 m. The robot starts behind the start line, on the left half. The
path is judged on the pelvis. The referee's stages, in order:
- Far-left cone: the pelvis crosses the left side line's continuation beyond the far line, in either direction.
- Bottom cone, first time: the pelvis crosses the centre line before the start line, from left to right.
- Up 1-2, up 2-3, up 3-4: the pelvis crosses the centre line between the first and second centre cones from right to
  left, between the second and third from left to right, between the third and fourth from right to left.
- Top cone: it crosses the centre line beyond the fourth centre cone, from left to right.
- Down 3-4, down 2-3, down 1-2: between the fourth and third from right to left, the third and second from left to
  right, the second and first from right to left.
- Bottom cone, second time: before the start line, from left to right.
- Far-right cone: the pelvis crosses the right side line's continuation beyond the far line, in either direction.
- Finish: the leading point of the torso (not the head, arms, legs or feet) reaches the start line with the pelvis on
  the right half. The success is called at that moment.

Fouls (each fails the attempt): any part of the robot touching any of the eight cones; any crossing of the centre line
by the pelvis that is not the next one in this list, at any time. The generic fall rule is off: a fall does not end
the attempt, and the robot may get up and go on, but the pelvis below 0.4 m for 10 s in a row fails it. Time limit:
60 s (6,000 control steps).

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
