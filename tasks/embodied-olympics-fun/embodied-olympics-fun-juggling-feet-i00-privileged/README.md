# Embodied Olympics · juggling with the feet (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-juggling-feet-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `juggling_feet`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Drop the football from your hands and juggle it with your feet for ten touches in a row, each sending it above your
knees, without it touching the ground.

## Success criteria
A size 5 football starts pressed between the robot's open palms, in the middle of a 5 m x 5 m grid on grass. The
referee's stages, in order: touch 1, touch 2, ..., touch 10.
- Drop: the ball has touched nothing of the robot for 0.03 s. Before the drop only the hands may touch it. A hand or
  arm may still touch it for 0.15 s after the drop.
- A touch is contact with a foot: the part below the ankle joint, or the lower leg where it lies over the foot (from
  0.08 m behind to 0.15 m ahead of the ankle joint along the foot, and at most 0.12 m above it). Contacts less than
  0.05 s apart are one touch; a touch lasts at most 0.05 s.
- A touch counts when, before anything touches the ball again, its centre has risen at least 0.22 m above its height
  at the start of the touch and its lowest point is above 0.36 m (knee height), and it left the touch with at least
  0.95 times the speed it came in with. A slower touch is not counted, and is not a fault.

Fouls (each fails the attempt): the ball touches the ground (also before the drop); a part other than the hands
touches it before the drop; a hand or arm touches it later than 0.15 s after the drop, or while a touch is going on
or not yet judged; any other part touches it (the lower leg above or beside the foot area above included); both feet
touch it at once; a touch lasts longer than 0.05 s; it is touched again before the last touch is judged; an ankle
leaves the grid. Fall rule: on, the pelvis below 0.35 m or any part other than the feet on the ground. Time limit:
60 s (6,000 control steps).

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
