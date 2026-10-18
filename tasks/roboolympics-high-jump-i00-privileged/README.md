# roboolympics-high-jump-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-high-jump-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `high_jump` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_high_jump.py: positive by injection (one foot lifted by the robot's own motors, then 1.5 m/s forward and 5.0 m/s up: over the bar at 1.00 m with 0.28 m to spare, onto the mat); negatives: walking under or round, a two-foot take-off, the bar off its supports. No jumping controller exists for the H1-2 (its open-loop squat jump leaves the ground at 1.8 m/s); human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Do a high jump: approach the bar, take off from one foot, go over the bar between the uprights without knocking it off its supports, and come down on the landing mat. (RoboOlympics `high-jump`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The bar is at the height of the robot's hip joints: the whole 67 kg body has to be thrown over it from one leg. The robot has no running or jumping gait at all; its walking gait reaches 0.7 m/s.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (one foot lifted by the robot's own motors, then 1.5 m/s forward and 5.0 m/s up: over the bar at 1.00 m with 0.28 m to spare, onto the mat); negatives: walking under or round, a two-foot take-off, the bar off its supports. No jumping controller exists for the H1-2 (its open-loop squat jump leaves the ground at 1.8 m/s).

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: World Athletics rules for the high jump. The bar (4.0 m long, 0.03 m thick, 2.0 kg) rests with its upper side 1.0 m above the ground on two flat supports (0.04 m wide, 0.06 m long) that face each other from two uprights 4.02 m apart; pushed more than half a support's width forwards or backwards, or lifted, it falls. The bar lies across y in the plane x = 0; the plane the rules mean is that of its nearer edge, x = -0.03/2. Behind it lies the landing mat: 6.0 m wide, 4.0 m deep, 0.7 m high, soft, beginning 0.1 m behind that plane. The approach is free (any direction, any distance on the 15.0 m of level runway). A flight is a time of at least 0.05 s in which nothing of you touches anything but the bar. Your jump is the flight in which your pelvis crosses the bar's plane or which ends with your first contact beyond the plane. Its take-off must be from one foot: in the last 0.05 s before lift-off only one foot touches the ground and nothing else of you does; and in it your pelvis must rise at least 0.05 m above its height at lift-off. Before your jump nothing of you may touch the ground or the mat beyond the plane. Your pelvis and both feet (the ankle joints) must cross the plane between the uprights and higher than the bar's upper side; one that comes back over the plane has not passed it and must pass it again. You have cleared the bar when every part of you is beyond the plane; from the landing until then nothing of you may touch the ground on the take-off side. You may touch the bar, for at most 0.3 s in all (it does not carry you), and you may land on any part of your body, on the mat or not. You succeed when you have cleared the bar and landed, and 2.0 s later the bar is still on its supports. A fall is not a failure by itself. You fail if the bar drops more than 0.05 m at any time; if you are in contact with the bar for more than 0.3 s in all; if you touch the ground or the mat beyond the plane without a jump; if the take-off is not from one foot; if the flight is not a jump; if your pelvis or a foot passes the plane outside the uprights or not higher than the bar; if you touch the ground on the take-off side after the landing before you have cleared the bar; or after 60 s (the time allowed for a trial). No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | track-and-jumps |
| Rule book | World Athletics Competition and Technical Rules, 2024 edition: TR 26 (26.3-26.7 the uprights 4.00 to 4.04 m apart, the 4.00 m bar of at most 2 kg and 30 mm diameter on flat supports 4 cm wide and 6 cm long, 1 cm clear of the uprights), TR 27.1 (the take-off from one foot), TR 27.2 (failures: the bar does not remain on the supports; touching the ground or the landing area beyond the plane of the bar's nearer edge without first clearing the bar), TR 27.3 (a runway of at least 15 m), TR 27.10 (a landing area of at least 6 m x 4 m x 0.7 m), TR 25.17 (one minute for a trial); deviations: TR 27.1 (one foot) is judged by a number: in the last 0.05 s before the lift-off of the jump's flight only one foot touches the ground, and nothing else does · TR 27.2(b) is judged geometrically: before the jump's flight nothing of the robot may touch the ground or the mat beyond the plane; the robot's pelvis and feet (the ankle joints) must pass the plane between the uprights and above the height of the bar's upper side; the bar is cleared when every part of the robot is beyond the plane · TR 27.2(a): the bar is judged 2.0 s after the clearance and the landing; it is off its supports when its centre is more than 0.05 m below its resting height · TR 27.10 (the landing area): the mat is a box with a soft, overdamped contact (time constant 0.08 s, full stiffness only 0.1 m deep), not a foam body; it is 0.1 m behind the bar's plane · the bar is rigid (no sag); no wind; the athlete alone, one trial at one height, 1.0 m (FAMILIES.md: a school competition's opening height; the men's world record is 2.45 m) · TR 27 does not define a jump; here its flight lasts at least 0.05 s and raises the pelvis at least 0.05 m above its height at lift-off · the bar is rigid and its supports are fixed, so unlike a real bar it would carry a body: touching it is allowed, as in the rules, but contact with it for more than 0.3 s in all is a failure (a real bar sags and falls under any weight); a pelvis or a foot that comes back over the plane has not passed it |
| Stages | take-off → clearance → bar stays |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `1a9e311355347c115703e546b6b0d8cf81341c8f18bb08345e3a9a3967231396` |
| Episode | 6000 control steps (60 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
