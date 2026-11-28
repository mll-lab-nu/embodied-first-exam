# Embodied Olympics · keepie-uppie (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-juggling-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `juggling`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Drop the football from your hands and keep it up for ten counted touches with your feet, legs or head, without it
touching the ground.

## Success criteria
A size 5 football starts held between the robot's palms. The referee's stages, in order: touch 1, touch 2, ...,
touch 10.
- Drop: the ball leaves the hands (clear of them for 0.03 s). Before the drop, only the hands may touch the ball.
- A touch is contact by a foot, shin, thigh or the head; contacts less than 0.05 s apart are one touch. A touch lasts
  at most 0.15 s. It counts when the ball's centre then rises at least 0.22 m above its height at the start of the
  touch before it is touched again. From the second touch on, the ball must also leave at no less than 0.95 times
  the speed it came in with; a touch that sends it off slower is not counted, and is not a fault.
- Touch 10 is the tenth counted touch.

Fouls (each fails the attempt): the ball touches the ground; a hand or arm touches the ball later than 0.15 s after
the drop (handball); the trunk touches the ball; a touch lasts longer than 0.15 s (carrying); the ball is touched
again before it has risen 0.22 m. Fall rule: on, the pelvis below 0.35 m or any part other than the feet on the
ground. Time limit: 30 s (3,000 control steps).

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
