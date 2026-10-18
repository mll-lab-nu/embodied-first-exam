# roboolympics-long-jump-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-long-jump-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `long_jump` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_long_jump.py: positive by injection (at the board, 3.6 m/s forward and 2.5 m/s up: a mark of 1.50 m in the sand); negatives: running through, landing short or beside the pit, a foot over the line, a take-off beside the board, a stride with the feet pulled up, into the sand without a flight. The running policy's strides come down 0.25 m beyond the line; nothing known jumps out of a run; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Do a long jump: run up, take off behind the take-off line, fly over the metre of runway beyond it and land in the sand pit. (RoboOlympics `long-jump`: one Unitree G1 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The sand begins a metre beyond the line: with the foot kept behind the line the robot has to fly about 1.2 m. Its running strides are in the air for less than 0.1 s and 0.4 m, its best published standing jump is 0.9 m, and no controller is known that jumps out of a run.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (at the board, 3.6 m/s forward and 2.5 m/s up: a mark of 1.50 m in the sand); negatives: running through, landing short or beside the pit, a foot over the line, a take-off beside the board, a stride with the feet pulled up, into the sand without a flight. The running policy's strides come down 0.25 m beyond the line; nothing known jumps out of a run.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: World Athletics rules for the long jump. The runway is 40.0 m long and 1.22 m wide along +x. The take-off line is x = 0, the edge of the white take-off board (0.2 m long, level with the runway) that is nearer the pit. The landing area is a pit of sand, level with the runway, that begins 1.0 m beyond the take-off line and is 9.0 m long and 2.75 m wide, centred on y = 0. Before your landing in the sand: no foot that is on the ground may have any part of it on or over the take-off line's plane (TR 30.1.1; the whole foot counts, also the parts of it that are in the air), and nothing of you may touch the ground at x >= 0 outside the sand (TR 30.1.4: the runway beyond the line and the ground beside the pit). Your jump is the flight (nothing of you touches anything, for at least 0.05 s) that ends with your first contact with the sand: its last ground contact before lift-off must have been within the runway's width (TR 30.1.2), and during it your pelvis must rise at least 0.05 m above its height at lift-off. Taking off before the board is allowed; the jump is measured from the take-off line all the same. You may land on any part of your body. The mark is the point nearest the take-off line at which any part of you touches the sand in the first 2.0 s after the first contact; in that time you may not touch the ground outside the pit nearer the take-off line than the mark (TR 30.1.5). You succeed when that time has passed after a valid jump: the mark is then at least 1.0 m. A fall is not a failure by itself. You fail on any of the faults above, when you touch the sand without such a flight, if you leave the venue (the level ground ends 8 m to each side of the runway's axis, 45 m behind the take-off line and 6 m beyond the pit), or after 60 s (the time allowed for a trial). No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Rule book | World Athletics Competition and Technical Rules, 2024 edition: TR 29 (the runway, the take-off board, the landing area), TR 30.1 (failures: 30.1.1 the take-off line, 30.1.2 the board's ends, 30.1.4 the ground between the line and the landing area, 30.1.5 the ground outside the landing area), TR 30.3 (the measurement), TR 25.17 (one minute for a trial); deviations: TR 30.1.3 (somersaulting) and TR 30.1.6 / 30.2 (how the athlete leaves the landing area) are not judged; the landing is judged for 2.0 s from the first contact with the sand · TR 29.3 (the plasticine indicator board): no imprint; the take-off line is judged geometrically: a foot on the ground with any part of it (also a part in the air) on or over the line's plane is a failure · TR 29.6 (the sand): the pit is a box with a soft, overdamped, high-friction contact (time constant 0.05 s, full stiffness only 0.04 m deep, friction 1.5); it gives under the feet but keeps no imprint, so the mark is the contact with the sand nearest the take-off line · TR 30 does not define a jump; here the flight into the pit must raise the pelvis at least 0.05 m above its height at lift-off (pulling the feet up and falling into the pit is no jump) · the rule book's wind gauge: there is no wind; the athlete alone, one trial |
| Stages | take-off → landing |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `794671b9f864c3f102835ebb88dfaa67f4e2a80c4c747fa9358ac0fa85a2ea9a` |
| Episode | 6000 control steps (60 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
