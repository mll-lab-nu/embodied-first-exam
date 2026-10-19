# roboolympics-fun-vertical-jump-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-fun-vertical-jump-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `vertical_jump` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_vertical_jump.py: positive by injection (the arm raised by the robot's own motors, then 2.8 m/s up: the hand touches the vane 0.30 m above its standing reach, lands and stands); negatives: no touch, lifted without a jump, a step before the take-off, the stand touched, the vane touched without a jump or with another part. A balanced open-loop jump of ours raises the pelvis 0.23 m of the 0.31 m needed; an unbalanced one reaches the vane and falls; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Do a vertical jump: from a standstill, jump off both feet without a step, touch the vane above you with a hand at the top of the jump, land on your feet and stand. (RoboOlympics `vertical-jump`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Neither built-in gait can jump. The robot has to raise its hand 0.30 m beyond its reach: a take-off at more than 2 m/s straight up from legs with real torque limits, an arm that is over the right place at the top, and a landing from that height that ends standing. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-fun-vertical-jump-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: Your standing reach (the top of a hand, flat-footed, legs straight, arm stretched up) is 1.66 m. A vane hangs over you with its underside 0.3 m above that: a light plate (0.05 kg) 0.9 m long from your left to your right and 0.08 m wide, on a hinge at its left end, so that it swings away when it is touched. Your jump is your first flight (nothing of you touches the ground or the stand) of at least 0.1 s. Until then: no step and no run-up: every point where a foot touches the ground must lie within 0.03 m of the place where that foot's sole stood at t = 0, and neither foot may be off the ground for more than 0.05 s while the other is on it (so both feet leave the ground within 0.05 s of each other: a two-foot take-off). Rising on the toes is allowed. The flight must be a jump: your pelvis has to rise at least 0.05 m above its height at lift-off. The touch: during that flight a hand (the fist or the wrist beyond the forearm) touches the vane. The first contact after the flight must be with your feet only. After the landing you may step; you succeed once you stand for 1.0 s without a break: only your feet on the ground, your torso within about 20 degrees of vertical, your pelvis slower than 0.35 m/s. A fall fails the attempt at any time: your pelvis lower than 0.35 m, or any part of you other than your feet on the ground. You fail on a step or shuffle before the take-off, a foot that leaves the ground before the other, a touch of the vane that is not in the jump's flight or not with a hand, any touch of the stand (its post or its base plate on the floor, also after the landing), a jump that lands without having touched the vane, a flight that is not a jump, a landing that is not on the feet, a fall, or after 20 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | track-and-jumps |
| Rule book | The Sargent jump (the jump-and-reach vertical jump test of school and club fitness batteries; Sargent 1921): the standing reach is measured flat-footed with one arm stretched overhead; from a standstill, with no step or preliminary hop, the athlete jumps off both feet and touches a vane of the measuring stand (Vertec) at the top of the jump; the result is the height touched above the standing reach; deviations: the standing reach is not measured in the attempt: it is this robot's, 1.66 m (the top of a hand above the soles with the legs straight and the arm in its highest pose, from the robot's kinematics), and the stand has one vane, set 0.3 m above it · the athlete cannot walk up to the stand: any step before the take-off is a foul, so the vane is placed over the place where the standing robot's raised hand is · a jump is told from a loss of contact by two numbers the test does not have: a flight of at least 0.1 s in which the pelvis rises at least 0.05 m above its height at lift-off · the test ends at the touch; here the robot must also land on its feet and stand for 1.0 s (FAMILIES.md: land and stand) · the qualifying height, 0.3 m, is a round number below the adult average of the test (about 0.4 to 0.5 m for men, 0.3 to 0.4 m for women) |
| Stages | take-off → touch → landing → stand |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 2000 control steps (20 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
