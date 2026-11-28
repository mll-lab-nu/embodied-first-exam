# Embodied Olympics · alpine slalom (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-alpine-slalom-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `alpine_slalom`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Ski down the slalom course in one run, through all 32 gates in order, and cross the finish line.

## Success criteria
FIS slalom, one run, on skis bound to the feet: a groomed slope falling at 18.3 degrees, 40 m wide, with 32 open gates
(the first 12 m down the slope, then every 9.6 m; turning poles 0.8 m from the centre line, alternately left and
right, outside poles 4.0 m further out) and a finish line 320 m down the slope, 12 m wide. The referee's stages, in
order: start, gate 1 to gate 32, finish.
- Start: both feet cross the start line at the platform's edge, which must happen within 20 s of the start.
- A gate is passed when both ski tips and both feet have crossed its gate line (the line on the snow from the turning
  pole to the outside pole) going down the slope; a point that comes back up across a gate line must cross it again.
  Gates are passed in order: any of those four points going down past a later gate's line, or the finish line, while
  a gate is not passed is a missed gate and fails the run. Hitting or folding a pole is allowed.
- Finish: after every gate, both feet cross the finish line between its posts. The success is called then; a foot
  crossing it outside the posts fails the run.

Fouls (each fails the run at once): a fall (any part other than the feet and the hands touches the snow, or the pelvis
is less than 0.35 m above the snow, measured along the slope's normal); stopping after the start (the pelvis slower
than 0.1 m/s for 1.5 s); not starting within 20 s. Time limit: 90 s (9,000 control steps).

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
