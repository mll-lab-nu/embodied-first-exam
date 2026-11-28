# Embodied Olympics · rugby conversion (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-rugby-conversion-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `rugby_conversion`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Kick the conversion: with one kick, send the ball from its tee over the crossbar between the posts.

## Success criteria
A rugby ball stands upright on a kicking tee in front of the robot's right foot. The goal line is 5 m beyond the ball;
the posts on it are 5.6 m apart (inner faces), centred on the ball, with the top of the crossbar 3 m above the ground.
The referee's stages, in order: kick, goal.
- Kick: the first contact of a foot with the ball (the foot below the ankle, or the lower leg where it lies over the
  foot: from 0.08 m behind to 0.15 m ahead of the ankle joint and at most 0.12 m above it). Every foot contact within
  0.15 s of the first belongs to the same kick.
- Goal: the ball's centre passes the goal line's vertical plane above the crossbar and between the posts (extended
  upwards), and goes on to 0.4 m beyond that plane. The ball may touch the bar or a post on the way. The success is
  called at that point.

Fouls (each fails the attempt): any part of the robot other than a foot touches the ball, at any time; a foot touches
the ball outside the kicking zone above; a touch of the ball more than 0.15 s after the kick; the ball touches the
ground (not the tee) after the kick before it has scored; the ball passes the goal line's plane under the crossbar or
outside the posts. Fall, judged only before the kick: the pelvis below 0.35 m, or any part other than the feet on the
ground. A fall after the kick does not end the attempt. Time limit: 60 s (6,000 control steps).

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
