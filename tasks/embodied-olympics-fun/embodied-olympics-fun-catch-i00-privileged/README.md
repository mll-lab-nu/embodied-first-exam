# Embodied Olympics · fly-ball catch (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-catch-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `catch`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Catch the fly ball in one hand before it touches the ground or your body, and keep it in that hand.

## Success criteria
A pitching machine 40 m in front of the robot throws a baseball at about 1.0 s, so that untouched it would come down
within 3.0 m of the robot's start. The referee's stages, in order: catch, hold.
- Catch: one hand's fingers and its thumb or palm touch the ball at the same time from opposite sides (the mean
  directions of the two contacts at least 90 degrees apart; a ball lying on an open hand is not caught), after the ball
  has passed the top of its arc and at most 0.5 s after it first touched the robot. Before the catch the ball may
  touch only the hands and forearms.
- Hold: from the catch, the ball stays enclosed in that hand for 1.0 s (breaks of at most 0.02 s allowed), touching
  nothing but that hand. The success is called when the 1.0 s are complete.

Fouls (each fails the attempt at once): before the catch, the ball touches the ground or a part other than a hand or a
forearm; the ball is touched before it has passed the top of its arc; it is not caught within 0.5 s of first touching
the robot; after the catch it is out of the hand for longer than 0.02 s, or touches anything but that hand (the other
hand, a forearm, the body, the ground). Fall (a failure at any time): the pelvis below 0.5 m, or any part other than
the feet on the ground. Time limit: 9 s (900 control steps).

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
