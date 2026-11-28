# Embodied Olympics · clean and jerk (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-clean-and-jerk-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `clean_and_jerk`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Clean and jerk the barbell: lift it from its blocks with both hands to your shoulders, then overhead on locked arms, and
hold it still until the down signal.

## Success criteria
A 5.0 kg technique barbell rests by its sleeves on two blocks on a 4.0 m by 4.0 m platform. A hand holds the bar while
the bar's grip section touches that hand's fingers (a break of up to 0.05 s is not letting go). The referee's stages,
in order: lift-off, clean, overhead, down signal.
- Lift-off: the bar's axis rises 0.03 m above its rest, which must happen with both hands holding it. Once the bar's
  centre has been 0.48 m above the platform the attempt has begun: from then on letting go with either hand, or any
  part of the barbell touching the platform or a block, fails.
- Clean: for 0.5 s without a break, the bar's axis is within 0.15 m of both shoulder joints, both hands hold it, both
  knees are within 10 degrees of straight, both feet are on the platform and in line (centres at most 0.05 m apart
  square to the bar), the bar and the pelvis are slower than 0.1 m/s, and the robot is under the bar (trunk upright,
  tilt cosine at least 0.94; the bar's centre within 0.25 m horizontally of the point between the shoulder joints; the
  bar within 20 degrees of the shoulder line, seen from above). The bar's centre more than 0.25 m above the centre of
  the head before the clean fails the attempt.
- Overhead: the bar's centre at least 0.25 m above the centre of the head, both hands on it, both elbows within 10
  degrees of straight.
- Down signal: the overhead position together with every condition of the clean except the shoulder distance (knees,
  feet in line, both on the platform, motionless, under the bar) held for 2.0 s without a break. Under a bar tilted
  more than 60 degrees from level the feet never count as in line. The success is called at the down signal.

Fouls (each fails the attempt at once): any part of the robot other than the feet touches the platform; any part of
the robot touches a block; any part of the robot or the barbell touches the floor beside the platform. The generic fall
rule is off. Time limit: 60 s (6,000 control steps).

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
