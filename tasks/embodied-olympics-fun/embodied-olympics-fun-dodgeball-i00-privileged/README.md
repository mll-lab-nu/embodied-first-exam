# Embodied Olympics · dodgeball (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-dodgeball-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Opponent | Five ball machines in the opposing half (scripted), each aiming one dodgeball at the robot |
| Instance | `dodgeball`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Dodge the 5 balls the machines throw at you: do not let a live ball touch you, and stay on your feet inside your court.

## Success criteria
The robot stands in its own half of an 18 m by 9 m dodgeball court. Five ball machines in the opposing half, 3.0 m
beyond the centre line, each aim at the robot's pelvis (at 0.8 m height) and throw one ball at 14 m/s: the first at
2.0 s, the others 2.5 s apart. A thrown ball is live from the moment it leaves its machine until it touches the floor
or anything that is not the robot or a ball, or until 3.0 s after its throw; then it is dead, and that throw is
dodged. The referee's stages, in order: dodge 1 to dodge 5, one per ball. The success is called when the fifth ball is
dead without any live ball having touched the robot.

Fouls (each fails the attempt at once): a live ball touches any part of the robot; the robot touches a ball still in
its machine; any part of the robot touches a boundary line or the floor outside the court, or the opponents' neutral
zone line (7.0 m from their back line) or anything beyond it. Fall (a failure at any time): the pelvis below 0.35 m,
or any part other than the feet on the floor. Time limit: 15.5 s (1,550 control steps).

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
