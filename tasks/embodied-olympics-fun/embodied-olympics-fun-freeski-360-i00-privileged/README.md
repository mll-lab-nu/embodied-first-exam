# Embodied Olympics · freeski 360 (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-freeski-360-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `freeski_360`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Ski down the in-run, jump off the kicker and spin one full turn in the air, then land on your skis and ride away over
the finish line.

## Success criteria
One big air jump on freestyle skis. The course: the level start platform (the robot's boots 0.30 m behind its edge),
an in-run of 38 m at 35 degrees, a 5 m flat, the kicker rising to its lip at 25 degrees, a 15 m table, the knoll, a
landing of 30 m at 36 degrees and the flat outrun; the finish line is 15 m into the outrun. The trick asked is the
360: the skis turn 270 to 450 degrees about the vertical in the air, either way, and no flip. The referee's stages,
in order: start, take-off, landing, ride-away.
- Start: both skis pass the platform's edge, by the robot's own action, within 20 s.
- Take-off: a flight (no contact with the snow for 30 ms) that starts within 4 m of the lip, rising at more than 10
  degrees.
- The trick is measured in the air only. Spin: the mean of the two skis' heading changes in the horizontal plane,
  counted in half turns of 180 degrees, to the nearest one. Flip: the pelvis's rotation about the horizontal axis
  across the take-off direction, less the 61 degrees a straight air turns anyway, counted in full turns, to the
  nearest one, and only if the body went upside down. A take-off riding backwards is not this trick.
- Landing: the first contact after the flight is by the skis, on the knoll or the landing hill (past the table), with
  the jump measured as the 360 and both skis pointing within 45 degrees of forwards (down the course).
- Ride-away: from 0.5 s after the landing each ski's heading stays within 90 degrees of its heading at that moment;
  when both skis pass the finish line the pelvis is at least 0.40 m above the snow and both skis point within 30
  degrees of forwards.

Fouls (each fails the attempt): no start within 20 s; the pelvis gets 4 m past the lip without a take-off; any other
trick (more or less spin, any flip, a backwards take-off); the first contact after the flight is not by the skis, or
is on the table; a ski more than 45 degrees from forwards at the landing; a ski turning more than 90 degrees on the
snow after the landing; the pelvis lower than 0.40 m or a ski more than 30 degrees from forwards at the finish line;
slower than 0.3 m/s for 3 s after the start. Fall rule (the snow's own, the generic one is off): any part other than
the boots touches the snow, at any time; or the robot is down for 1.0 s in all (on the snow with the pelvis less than
0.40 m above it, measured along its normal, or the trunk more than 70 degrees from the normal; the time down shrinks
again at a quarter of the rate while it is up). Time limit: 40 s (4,000 control steps).

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
