# Embodied Olympics · 10 m platform dive (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-platform-10m-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `platform_10m`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Dive from the 10 m platform: take off from both feet, do a forward half somersault with your body straight, and go into
the water head first, straight and vertical.

## Success criteria
The robot stands on the front end of a 10 m platform facing the water; the water is not simulated (its surface is
the plane z = 0, passed without resistance). The dive is a forward dive straight. The referee's stages, in order:
take-off, entry, under water.
- Take-off: the robot is in the air (both feet stayed on the platform until then) and its centre of mass has risen at
  least 0.1 m above its height at the start.
- Entry: the first part to reach the water surface is a hand or the head; by then the body line (ankles' middle to
  shoulders' middle) has turned 180 degrees forwards, within 45 degrees, from the upright start; the middle of the
  palms at that moment is 0.5 m to 3.0 m in front of the platform's front edge and within 0.5 m to either side of the
  line the robot faced at the start.
- Under water: the whole robot is below the surface, with the entry kept clean until then (below). The success is
  called then.

Through the entry: when the pelvis reaches the surface the body line is within 15 degrees of vertical, head down; the
shoulders' axis stays within 20 degrees of the platform's width direction (no twist); both palms are at least 0.15 m
beyond the centre of the head along the body line, at most 0.2 m apart and each within 0.15 m of the body line. From
the moment the body line passes the horizontal until the dive is complete the robot is straight: hips and knees each
bent less than 20 degrees, the ankles at most 0.12 m apart, each ankle pitched at least 0.3 rad towards the toes.

Fouls (each fails the attempt): before the take-off, any part above the ankles touching the platform, anything
touching the railings, a foot off the platform for more than 0.1 s while the other is on it, or a flight that lands on
the platform again; after the take-off, any touch of the platform or its railings; reaching the water without a
take-off, feet first, outside the distances, or outside any limit above. The generic fall rule is off. Time limit:
20 s (2,000 control steps).

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
