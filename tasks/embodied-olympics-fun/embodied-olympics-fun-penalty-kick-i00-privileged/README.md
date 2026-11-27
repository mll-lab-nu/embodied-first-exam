# Embodied Olympics · penalty kick (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-penalty-kick-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Opponent | Goalkeeper dummy on a rail (scripted): after the kick it moves along the goal line to block the ball |
| Instance | `penalty_kick`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Take a penalty kick: with one kick, send the ball past the goalkeeper dummy into the goal.

## Success criteria
A size-5 football lies on the penalty mark, 3.0 m ahead of the robot; the goal (7.32 m wide, 2.44 m high) is 11 m
beyond it. A goalkeeper dummy (a board 1.9 m high, 0.6 m wide, 80 kg) stands on the goal line at the centre of the goal
on a carriage that runs on a rail. From 0.25 s after the kick its motor (at most 800 N) drives it at up to 3.0 m/s
towards the point where the ball, going on as it moves at that moment, would cross the line; it blocks the ball, and a
hit pushes it along the rail. The referee's stages, in order: kick, goal.
- Kick: the first contact of a foot or an ankle (the parts below the shin) with the ball. Every such contact within
  0.15 s of the first belongs to the one kick.
- Goal: the whole ball is over the goal line between the posts and under the bar. It may touch the posts, the bar,
  the dummy and the ground on the way. The success is called at that moment.

Fouls (each fails the attempt): any other part of the robot touches the ball at any time; a foot touches the ball
again more than 0.15 s after the first contact; the ball is not moving towards the goal line at the end of the kick;
the whole ball crosses the goal line outside the goal; after the kick, the ball is slower than 0.1 m/s for 1.0 s
without a goal. Fall (a failure at any time): the pelvis below 0.35 m, or any part other than the feet on the ground.
Time limit: 15 s (1,500 control steps).

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
