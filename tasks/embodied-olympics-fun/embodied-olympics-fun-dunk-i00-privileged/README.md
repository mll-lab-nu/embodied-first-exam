# Embodied Olympics · dunk (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-dunk-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `dunk`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Dunk the basketball with both hands: with at most two steps, jump and push it down through the ring with both hands on
it, then let go, land on your feet and stand.

## Success criteria
The ring's top edge is 2.39 m above the floor; the robot starts with the ball held between its hands. A hand is on the
ball while it touches it (gaps shorter than 0.03 s included). The referee's stages, in order: dunk, stand.
- The ball stays in the hands (at least one hand on it) until its centre has entered the ring: no dribble, throw or
  drop.
- Dunk: the ball's centre goes down through the ring's plane inside the ring while both hands are on the ball, and on
  down to one ball diameter below the ring without coming back up. A ball whose centre comes up through the ring from
  below fails the attempt.
- Travelling, until the dunk: at most 2 steps (a foot touching down after at least 0.03 s off the floor; both feet
  within 0.03 s are one step; never the same foot twice in a row), and a foot on the floor may not slide more than
  0.2 m from where it was put down.
- Stand: after the dunk, no hand on the ball and, for 1.0 s without a break, only the feet on the ground, the torso
  upright (tilt cosine at least 0.94), the pelvis slower than 0.35 m/s. The success is called when the 1.0 s are
  complete.

Fouls (each fails the attempt at once): the ball leaves the hands before its centre has entered the ring; the ball
touches the floor before the dunk; the ball goes through after an entry without both hands on it; the ball comes up
through the ring; travelling; the robot touching the basket (ring, plate or backboard) for more than 0.3 s in all.
Fall (a failure at any time): the pelvis below 0.35 m, or any part other than the feet on the floor. Time limit: 15 s
(1,500 control steps).

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
