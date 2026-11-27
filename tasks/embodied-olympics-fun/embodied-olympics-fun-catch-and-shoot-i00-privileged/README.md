# Embodied Olympics · catch and shoot (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-catch-and-shoot-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `catch_and_shoot`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Catch the pass with both hands, then shoot it into the basket from where you stand, without travelling.

## Success criteria
The official basket (ring top 3.05 m above the floor); about 2.0 s after the start a passing machine 4.0 m away sends
the robot a chest pass of about 9 m/s. A hand is on the ball while it touches it (gaps shorter than 0.03 s included).
The referee's stages, in order: catch, release, through the ring.
- Catch: before the ball touches the floor, both hands are on it together for 0.1 s without a break. Earlier touches
  of one hand or both are allowed.
- Release: from the catch the ball stays in the hands until no hand is on it (a slip or drop is a release too). From
  the catch to the release no travelling: with both feet on the floor at the catch, the first foot lifted makes the
  other the pivot foot, the pivot foot (before any lift, either foot) may not slide more than 0.2 m, and once it has
  left the floor no foot may touch the floor again before the release; with a foot off the floor at the catch, at most
  2 steps (never the same foot twice in a row), and no foot down again after them before the release.
- Through the ring: the ball's centre goes down through the ring's plane inside the ring and on down to one ball
  diameter below it. The success is called then.

Fouls (each fails the attempt at once): the robot touches the ball before the pass; from the pass to the release, the
ball touches a part other than the hands; the ball touches the floor before the catch, or at any time before it is
through the ring; travelling; the robot touches the ball more than 0.05 s after the release; the ball's centre comes
up through the ring from below. Fall (a failure at any time): the pelvis below 0.35 m, or any part other than the feet
on the floor. Time limit: 15 s (1,500 control steps).

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
