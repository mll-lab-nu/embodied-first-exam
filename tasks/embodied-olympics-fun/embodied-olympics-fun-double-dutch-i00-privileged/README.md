# Embodied Olympics · double dutch (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-double-dutch-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `double_dutch`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Jump Double Dutch: get into the two turning ropes and jump them 10 times in a row, one rope per jump, without a rope
touching you, then land on your feet.

## Success criteria
Two machines turn two ropes in opposite directions, half a turn apart, at 1.1 turns per second, so that a rope passes
under the middle every 0.45 s; they are turning at the start and never stop. The robot starts outside the ropes. The
referee's stages, in order: entry, jump 1 to jump 10, landing.
- Entry: the pelvis enters the centre zone (within 0.35 m of the middle along the ropes' plane of turning, and 0.5 m
  across it). Leaving the zone after that fails the attempt.
- A jump counts when a rope passes under both feet while nothing of the robot touches the ground and the pelvis is in
  the centre zone, if that rope has passed over the head since it last passed under, and the flight is not the one of
  the last counted jump (one rope per jump).
- Landing: after the 10th counted jump, the robot's first contact with the floor is the feet only. The success is
  called then; a landing on anything else fails.

Fouls (each fails the attempt at once): a rope touches any part of the robot (a miss); a rope passes under a foot
while the robot is on the ground, or passes through the robot; the robot touches a turning machine. Fall (a failure at
any time): the pelvis below 0.35 m, or any part other than the feet on the floor. Time limit: 25 s (2,500 control
steps).

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
