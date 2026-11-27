# Embodied Olympics · handstand (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-handstand-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `handstand`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Do a handstand: get up onto your hands, hold a straight handstand still for 2 s, then come back down onto your feet and
stand.

## Success criteria
A flat 12 m x 12 m floor. The referee's stages, in order: handstand, held 2 s, on the feet, stand.
- Handstand: only the hands touch the floor; the pelvis is above the middle of the hands' support and the ankles are
  above the pelvis; the line from the hands' middle to the pelvis and the line from the pelvis to the ankles each lean
  at most 45 degrees from vertical; the knees are bent at most 20 degrees and the hips at most 25 degrees.
- Held 2 s: that handstand, with the pelvis moving at most 0.15 m/s, for 2 s in a row. A touch of the floor by any part
  other than a hand restarts the count.
- On the feet: after the hold, only the feet touch the floor.
- Stand: the robot stands (only the feet on the floor, the torso within 20 degrees of vertical, the pelvis at most
  0.35 m/s) for 1 s in a row.

Fouls (each fails the attempt): the pelvis leaves the 12 m x 12 m area. Fall rule: on, with the hands allowed on the
floor as well as the feet: the pelvis below 0.25 m, or any other part on the floor, fails the attempt; it is checked
at every physics step, not only at every control step. Time limit: 30 s (3,000 control steps).

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
