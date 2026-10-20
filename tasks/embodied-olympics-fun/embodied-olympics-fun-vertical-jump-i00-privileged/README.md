# embodied-olympics-fun-vertical-jump-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-vertical-jump-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `vertical_jump` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_vertical_jump.py: positive by injection (the arm raised by the robot's own motors, then 2.8 m/s up: the hand touches the vane 0.30 m above its standing reach, lands and stands); negatives: no touch, lifted without a jump, a step before the take-off, the stand touched, the vane touched without a jump or with another part. A balanced open-loop jump of ours raises the pelvis 0.23 m of the 0.31 m needed; an unbalanced one reaches the vane and falls; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Do a vertical jump: from a standstill, jump off both feet without a step, touch the vane above you with a hand at the top of the jump, land on your feet and stand. (Embodied Olympics `vertical-jump`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Neither built-in gait can jump. The robot has to raise its hand 0.30 m beyond its reach: a take-off at more than 2 m/s straight up from legs with real torque limits, an arm that is over the right place at the top, and a landing from that height that ends standing.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (the arm raised by the robot's own motors, then 2.8 m/s up: the hand touches the vane 0.30 m above its standing reach, lands and stands); negatives: no touch, lifted without a jump, a step before the take-off, the stand touched, the vane touched without a jump or with another part. A balanced open-loop jump of ours raises the pelvis 0.23 m of the 0.31 m needed; an unbalanced one reaches the vane and falls.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: Your standing reach (the top of a hand, flat-footed, legs straight, arm stretched up) is 1.66 m. A vane hangs over you with its underside 0.3 m above that: a light plate (0.05 kg) 0.9 m long from your left to your right and 0.08 m wide, on a hinge at its left end, so that it swings away when it is touched. Your jump is your first flight (nothing of you touches the ground or the stand) of at least 0.1 s. Until then: no step and no run-up: every point where a foot touches the ground must lie within 0.03 m of the place where that foot's sole stood at t = 0, and neither foot may be off the ground for more than 0.05 s while the other is on it (so both feet leave the ground within 0.05 s of each other: a two-foot take-off). Rising on the toes is allowed. The flight must be a jump: your pelvis has to rise at least 0.05 m above its height at lift-off. The touch: during that flight a hand (the fist or the wrist beyond the forearm) touches the vane. The first contact after the flight must be with your feet only. After the landing you may step; you succeed once you stand for 1.0 s without a break: only your feet on the ground, your torso within about 20 degrees of vertical, your pelvis slower than 0.35 m/s. A fall fails the attempt at any time: your pelvis lower than 0.35 m, or any part of you other than your feet on the ground. You fail on a step or shuffle before the take-off, a foot that leaves the ground before the other, a touch of the vane that is not in the jump's flight or not with a hand, any touch of the stand (its post or its base plate on the floor, also after the landing), a jump that lands without having touched the vane, a flight that is not a jump, a landing that is not on the feet, a fall, or after 20 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (an RTX 4090 workstation, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | track-and-jumps |
| Rule book | The Sargent jump (the jump-and-reach vertical jump test of school and club fitness batteries; Sargent 1921): the standing reach is measured flat-footed with one arm stretched overhead; from a standstill, with no step or preliminary hop, the athlete jumps off both feet and touches a vane of the measuring stand (Vertec) at the top of the jump; the result is the height touched above the standing reach; deviations: the standing reach is not measured in the attempt: it is this robot's, 1.66 m (the top of a hand above the soles with the legs straight and the arm in its highest pose, from the robot's kinematics), and the stand has one vane, set 0.3 m above it · the athlete cannot walk up to the stand: any step before the take-off is a foul, so the vane is placed over the place where the standing robot's raised hand is · a jump is told from a loss of contact by two numbers the test does not have: a flight of at least 0.1 s in which the pelvis rises at least 0.05 m above its height at lift-off · the test ends at the touch; here the robot must also land on its feet and stand for 1.0 s (FAMILIES.md: land and stand) · the qualifying height, 0.3 m, is a round number below the adult average of the test (about 0.4 to 0.5 m for men, 0.3 to 0.4 m for women) |
| Stages | take-off → touch → landing → stand |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `a314a2832e1ecf27b7fa8c9c0b543c808dddbec48090d476e1c75984632c7991` |
| Episode | 2000 control steps (20 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
