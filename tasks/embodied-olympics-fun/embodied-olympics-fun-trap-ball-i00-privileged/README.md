# Embodied Olympics · trapping the ball (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-trap-ball-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `trap_ball`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Trap the pass: take the ball rolling past you with a foot and bring it to rest close to you within three seconds.

## Success criteria
A size-5 football (0.22 m across, 0.43 kg) waits in a ball machine 15.0 m ahead of the robot and 0.5 m to its
right. About 3.2 s after the start the machine plays it along the ground at about 9.6 m/s, parallel to the way the
robot faces, past 0.5 m to the right of where the robot stands. The referee's stages, in order: first touch,
control.
- First touch: the first part of the robot that the ball touches is a foot or an ankle (the parts below the shin),
  and nothing else of the robot touches it at that moment.
- Control: within 3.0 s of the first touch the ball is slower than 0.2 m/s for 0.5 s without a break, its centre all
  that time within 1.0 m of the pelvis (measured along the ground). The success is called at the end of the 0.5 s.
After the first touch the ball may be played as often as wished with any part except the hands and arms.

Fouls (each fails the attempt at once):
- the ball's first touch is not with a foot or an ankle alone;
- a hand or an arm touches the ball at any time (handball);
- 3.0 s after the first touch the ball is not under control;
- before the pass has left the machine: the pelvis comes within 9.15 m of the machine (measured along the ground), or
  the robot touches the machine or the waiting ball.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the ground. Time limit:
10 s (1,000 control steps).

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
