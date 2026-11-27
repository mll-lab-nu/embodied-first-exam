# Embodied Olympics · inline slalom (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-inline-slalom-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `inline_slalom`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Skate the speed slalom: from the start box, skate on one foot through the 20 cones, passing them alternately left and
right, and over the end line.

## Success criteria
The robot wears inline skates (four wheels in a line on each). 20 free plastic cones (0.078 m high, 0.02 kg) stand on
the line y = 0, one every 0.8 m from 12 m beyond the start line; the end line is 0.8 m beyond the last cone. The
referee's stages, in order: start, cone line, cone 5, cone 10, cone 15, cone 20, finish.
- Start: the front of the robot's body at 0.40 m above the ground (the gate beam's height) crosses the start line,
  within 5 s of the start.
- Cone line: the front wheel of either skate reaches the front edge of the first cone. If not exactly one skate is
  on the ground at that moment, that is one penalty. The first skate that is alone on the ground is the supporting
  skate; from then on the other (free) skate must not touch the ground, and a change of feet is not allowed.
- Cones: a cone is passed when the supporting skate's centre reaches the cone; it is passed on the side of the line
  where that skate is. Cone 5, 10, 15 and 20 are stages.
- Finish: the front wheel of the supporting skate crosses the end line first, with that skate on the ground, after
  all 20 cones are passed.
- Penalties, counted at the finish: each kicked cone (its base centre more than 0.0335 m from its mark, or tilted more
  than 30 degrees), each missed interval (two cones in a row passed on the same side), and the first-cone penalty
  above (not counted again if the first cone is kicked). More than 4 penalties fail the attempt.

Fouls (each fails the attempt): no start within 5 s; not on one skate when the second cone is passed; the free skate
touches the ground; the free skate's front wheel crosses the end line first; the supporting skate is in the air at
the end line; the end line is crossed before all 20 cones are passed. Fall rule: on, the pelvis below 0.45 m or any
part of the robot other than the feet on the ground (the skates' wheels and frames may touch it). Time limit: 60 s
(6,000 control steps), from the start, not from the gate beam.

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
