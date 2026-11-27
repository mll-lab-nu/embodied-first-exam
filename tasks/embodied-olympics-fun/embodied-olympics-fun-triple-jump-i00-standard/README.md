# Embodied Olympics · triple jump (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-triple-jump-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `triple_jump`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Do a triple jump: run up, then hop, step and jump into the sand pit, landing at least 7 m from the take-off line.

## Success criteria
A runway 40.0 m long and 1.22 m wide leads to a sand pit level with it; the take-off line is the pit-side edge of a
0.2 m take-off board, and the pit begins 7.0 m beyond it (9.0 m long, 2.75 m wide). A flight is a time of at least
0.05 s in which nothing of the robot touches anything. "On the runway" means every point of the contact within the
runway's width and before the pit. Until the hop no foot on the ground may have any part of it on or over the
take-off line's plane, and nothing of the robot may touch the ground beyond the line. The referee's stages, in
order: hop, step, jump, landing.
- Hop: the flight that ends with the first contact beyond the line. It is taken off from one foot (the other foot
  left the ground at least 0.05 s before it) within the runway's width; the pelvis rises at least 0.05 m above its
  height at lift-off; its first contact is the take-off foot alone, on the runway.
- Step: the next flight. Until it starts only the hop's landing foot touches the ground; its first contact is the
  other foot alone, on the runway.
- Jump: the next flight. Until it starts only the step's landing foot touches the ground; its first contact is in
  the sand (any part of the robot), with nothing on the ground outside the pit.
- Landing: the mark is the point nearest the take-off line at which any part of the robot touches the sand in the
  first 2.0 s after the jump's first contact. The success is called when those 2.0 s have passed; as the sand begins
  7.0 m beyond the line, the mark is at least 7.0 m.

Fouls (each fails the attempt at once):
- before the hop, a foot on the ground with any part on or over the take-off line, or any touch of the ground beyond
  the line that does not end a flight;
- a hop taken off from both feet, taken off outside the runway's width, with a pelvis rise below 0.05 m, or landing
  other than on the take-off foot alone on the runway;
- before the step or the jump, any part other than the landing foot on the ground, or the landing foot's centre more
  than 0.3 m from where it came down;
- a step landing other than on the other foot alone on the runway; a jump whose first contact is not in the sand;
- in the 2.0 s after the jump's landing, a touch of the ground outside the pit nearer the take-off line than the mark;
- leaving the venue (the level ground ends 8 m to each side of the runway's axis, 45 m behind the take-off line and
  6 m beyond the pit).
The generic fall rule is off: a fall is not a failure by itself. Time limit: 60 s (6,000 control steps).

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
