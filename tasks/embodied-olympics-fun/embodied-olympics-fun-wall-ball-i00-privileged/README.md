# Embodied Olympics · wall ball (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-wall-ball-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `wall_ball`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
From behind the line, throw the ball at the target circle on the wall, then catch the rebound in a hand before it lands
and hold it.

## Success criteria
A wall stands 5.0 m beyond the line the robot stays behind; the target is a circle 0.5 m across painted on it, its
centre 1.5 m above the ground, straight ahead of the robot. A tennis ball (0.067 m across, 0.0577 kg) starts in the
right hand; both hands are five-finger hands that hold things by contact and friction only. A hand holds the ball
while the ball touches its fingers and its thumb or palm, with the ball's centre on the palm's side of the hand and
within 0.12 m of the hand's grasp point. The referee's stages, in order: release, target, catch, hold.
- Release: the ball has touched no part of the robot for 0.05 s (it is released at its last touch; once).
- Target: the first thing it touches after that is the wall, at a point inside the target circle.
- Catch: a hand then holds the ball (either hand), before the ball has touched the ground; before the catch the
  rebound may touch only the hands and forearms.
- Hold: the ball has been held for 1.0 s from the catch, never unheld for more than 0.05 s. The success is called at
  the end of the 1.0 s.

Fouls (each fails the attempt at once):
- any part of the robot touches the ground on or beyond the line, at any time;
- the ball touches the ground, at any time;
- the ball hits the wall outside the circle;
- after the release and before the wall, any part of the robot touches the ball or a hand holds it (the right arm
  may still brush it during the first 0.15 s after the release);
- before the catch the rebound touches a part other than a hand or a forearm;
- after the catch the ball is unheld for more than 0.05 s.
Fall (a failure at any time): the pelvis lower than 0.5 m, or any part other than the feet on the ground. Time limit:
15 s (1,500 control steps).

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
