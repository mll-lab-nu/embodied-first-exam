# Embodied Olympics · basketball dribble (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-basketball-dribble-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `basketball_dribble`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Dribble the basketball from the end line up the court until it bounces beyond the centre line with both your feet past
it too, without a travel, a double dribble or a carry.

## Success criteria
A FIBA court; the robot stands near one end line, holding the ball. A hand is on the ball while it touches it (gaps
shorter than 0.03 s included); the ball has left the hands once no hand has been on it for 0.03 s. The referee's
stages, in order: dribble, past the free-throw line, in the frontcourt.
- While the ball is in the hands it may touch no part of the robot but the hands, and not the floor. The first foot
  lifted makes the other the pivot foot; the pivot foot (before any lift, either foot) may not slide more than 0.2 m,
  and may not leave the floor before the ball has left the hands.
- After the ball has left the hands, the robot plays it with one hand at a time; between two hand touches (the first
  one included) the ball must touch the floor. Dribble: the first such hand touch.
- Past the free-throw line: after that touch, the ball touches the floor beyond the free-throw line (5.8 m from the
  end line).
- In the frontcourt: the ball touches the floor beyond the centre line's far edge while every point where each foot
  last touched the floor is beyond that edge. The success is called then.

Fouls (each fails the attempt at once): travelling at the start; after the ball has left the hands, both hands
touching it at once, a hand touching it twice without a floor contact between, one touch lasting longer than 0.3 s, a
hand under the ball (its lowest contact more than 0.3 of the ball's radius below the ball's centre) for longer than
0.1 s, the ball touching any part but a hand, or the ball's centre more than 2.0 m horizontally from the pelvis; the
ball or any part of the robot touching the floor on or outside a boundary line. Fall (a failure at any time): the
pelvis below 0.35 m, or any part other than the feet on the floor. Time limit: 60 s (6,000 control steps).

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
