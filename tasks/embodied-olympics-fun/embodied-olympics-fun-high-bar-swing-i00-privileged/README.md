# Embodied Olympics · high bar giant swing (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-high-bar-swing-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `high_bar_swing`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Jump from the block, catch the high bar with both hands and swing one full circle round it with your body straight,
without letting go.

## Success criteria
The bar is 0.028 m thick, 2.80 m above the floor, fixed (it does not turn). The robot starts standing on a 1.1 m block
behind it, hands open; its three-finger hands hold the bar by contact and friction only. The referee's stages, in
order: jumped, caught the bar, over the top, full circle.
- Jumped: the robot leaves the block without holding the bar. It may land back on the block and jump again.
- Caught the bar: both hands grasp the bar (the bar touches the hand's index or middle finger and its thumb or palm)
  after the robot has left the block.
- Over the top and full circle: the swing angle is the angle between straight down and the line from the bar to the
  robot's centre of mass, seen from the side. After the catch it must travel 360 degrees in one direction. A turn back
  of more than 5 degrees starts the count again from there. Whenever the centre of mass is higher than the bar it must
  be at least 0.59 m from the midpoint of the two wrists; closer, and the count starts again. "Over the top" latches
  when the counted travel passes straight up; the success is called when it reaches 360 degrees.

Fouls (each fails the attempt): both hands grasp the bar before the robot has left the block; before the catch, any
part of the robot touches the mats or the floor; any part other than the hands touches the bar; after the catch, a
hand is off the bar (touching it with no part) for more than 0.05 s, with no regrip; after the catch, the robot touches
the block, the uprights, the mats or the floor. The generic fall rule is off; these rules replace it. Time limit: 60 s
(6,000 control steps).

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
