# Embodied Olympics · triple jump (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-triple-jump-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
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

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory()` writes it: an `actions` array of sim rows, one per
10 ms control step, and the task's family name. After the agent's session it is replayed once, open-loop, from the
frozen start, in a fresh process of a separate verifier container without network. Rows run one per control step
until the referee calls the attempt; rows after the call, and rows past the attempt's time limit, are not run. The
task is passed if the referee has called a success when the replay stops. If the rows run out before the referee's
call, the task is not passed. A row the robot cannot run (its first value, the mode, is not one of the robot's modes)
ends the replay at that row without a pass.

The physics diverging (a non-finite state, a bad acceleration, or the robot or a prop faster than 150 m/s) ends the
attempt as a failure, unless a success was called in an earlier control step. Only the trajectory is scored (`gen.py`
and `NOTES.md` are not). A missing file, a file that is not such an array (a link, over 64 MB, more than 40,000 rows,
the wrong row width), a file for another task, or a non-finite value in the rows that are used scores 0. An image that
no longer rebuilds the frozen start, or a replay that crashes or runs over 600 s, is an infrastructure failure, not a
score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
The Embodied Olympics robot library and running-policy port ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics)
@ `7df999b`, a private repository) is released under the MIT License (`LICENSE.roboolympics` in the image); this
benchmark's venues and referees are MIT too. Third-party parts in the image: the Unitree G1 model and meshes from MuJoCo
Menagerie (BSD-3-Clause), the Unitree H1-2 model, meshes and walking policy and the G1 walking policy from
unitree_rl_gym (BSD-3-Clause), the G1 running policy from C1801SYQ/g1_running (Apache-2.0), FALCON's G1 walking policy
from LeCAR-Lab/FALCON (MIT) and the WBC-AGILE G1 walking policy from NVIDIA (Apache-2.0). No non-commercial terms apply.
