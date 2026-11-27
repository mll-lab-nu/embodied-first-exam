# Embodied Olympics · free kick over the wall (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-free-kick-wall-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `free_kick_wall`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Take a direct free kick: with one kick, send the ball over or round the wall into the goal.

## Success criteria
The ball lies in front of the robot's right foot. The goal line is 20 m beyond it; the goal, 7.32 m wide between the
posts and 2.44 m high under the bar, has its centre 4 m to the left of the line straight ahead. A wall of four free
standing training mannequins (1.75 m tall), 9.15 m from the ball, covers the near post; there is no goalkeeper. The
referee's stages, in order: kick, goal.
- Kick: a foot touches the ball (the foot below the ankle, or the lower leg where it lies over the foot and at most
  0.12 m above the ankle joint). Every such contact within 0.15 s of the first is part of the one kick. 0.15 s after
  the first contact the ball must be moving towards the goal line.
- Goal: the whole ball crosses the goal line between the posts and under the bar. On the way it may touch the
  mannequins, the posts, the bar and the ground.

Fouls (each fails the attempt): any other part of the robot touches the ball; a foot touches it again later than
0.15 s after the first contact; the ball is not moving towards the goal line 0.15 s after the first contact; the ball
crosses the goal line outside the goal; after the kick the ball is slower than 0.1 m/s for 1 s. Fall, before the kick
only: the pelvis below 0.35 m, or any part other than the feet on the ground. After the kick a fall does not end the
attempt. Time limit: 30 s (3,000 control steps).

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
