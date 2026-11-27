# Embodied Olympics · jump rope (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-jump-rope-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `jump_rope`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Skip rope: turn the rope forwards and jump it with both feet together 17 times, then land on your feet and stand.

## Success criteria
The robot holds a skipping rope (2.13 m, 0.10 kg) by its two handles, one in each hand. The referee's stages, in
order: jump 1, jump 2, ..., jump 17, stand.
- A jump counts when the rope first passes over the head forwards (its point straight above the head crosses the
  upright plane through the head from back to front, higher than the top of the head) and then passes under both
  feet: at each foot, its point at that foot's sideways position crosses the upright plane through the foot from
  front to back, lower than the bottom of the foot plus the rope's thickness, moving backwards at 1.0 m/s or more;
  under the second foot within 0.15 s of the first. At both passes nothing of the robot touches the floor, and the
  two feet last left the floor within 0.10 s of each other (a two-foot take-off).
- A turn that does not count is not a fault: the rope must then go over the head again before the next jump. Extra
  hops do not count.
- Stand: after the 17th counted jump, the first touch of the floor is by the feet only; then the robot stands (only
  the feet on the floor, the torso within 20 degrees of vertical, the pelvis at most 0.35 m/s) for 1 s in a row.

Fouls (each fails the attempt): a handle touches the floor, or is out of its hand (not touching that hand's fingers
and its thumb or palm) for 0.05 s; the landing after the 17th jump is not on the feet only. Fall rule: on, the pelvis
below 0.35 m or any part other than the feet on the floor. Time limit: 60 s (6,000 control steps).

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
