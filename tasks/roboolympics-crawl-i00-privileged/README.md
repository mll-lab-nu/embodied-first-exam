# roboolympics-crawl-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-crawl-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `crawl` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_crawl.py: positive by injection (the robot laid prone, 0.27 m high, and dragged under the 21 wires by a force on the pelvis); negatives: walking upright into a wire, on hands and knees (0.46 m: a wire touched), round, over, not under, stopping inside. No crawling controller exists; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Get under the low wires in front of you and crawl the whole course until your whole body is beyond the last wire, without touching a wire. (RoboOlympics `crawl`: one Unitree G1 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Neither built-in gait works below 0.45 m, and on hands and knees this robot is about 0.46 m high, just too tall: it has to get down from standing and move 10.0 m and its own length flat on the ground with joint commands of its own, never lifting any part into a wire.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (the robot laid prone, 0.27 m high, and dragged under the 21 wires by a force on the pelvis); negatives: walking upright into a wire, on hands and knees (0.46 m: a wire touched), round, over, not under, stopping inside. No crawling controller exists.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The obstacle is a lane along +x, 2.0 m wide between two rows of posts, centred on y = 0. Horizontal wires cross it every 0.5 m over 10.0 m: the first is 1.0 m ahead of where your pelvis starts, the last 10.0 m further on. Each wire is 0.008 m thick with its centre 0.45 m above the ground. You succeed when your whole body (every part of you) is beyond the last wire, having passed under all of them. There is no fall rule: any part of you may touch the ground, and you need not stand up at the end. You fail the moment any part of you touches a wire; if your pelvis, while it is between the first and the last wire, is higher than 0.45 m (going over) or outside the lane (going round, beyond a row of posts); if your whole body is beyond the last wire without your pelvis having passed under the wires; or after 120 s. The posts may be touched. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | parkour-apparatus-balance |
| Rule book | No federation rule book: the low-wire crawl of military obstacle courses and obstacle-course racing (wires strung about 18 in, 0.45 m, above the ground; the athlete passes under all of them and may not go round or over). The layout is this benchmark's: wires every 0.5 m over 10 m; deviations: the wires: each wire is a rigid, fixed bar 8 mm thick between two posts, not a slack (barbed) wire, because the simulator has rigid bodies only; touching one fails the attempt, as a judge's fault for a snagged wire · the ground: level and rigid with a friction coefficient of 1.0, not sand or mud, because the simulator's ground is rigid |
| Stages | under the first wire → half way → through |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `2e0f0f3043ba5d61df8e00eccaae82fc1ca62cd21871cab709eb36fa310448bb` |
| Episode | 12000 control steps (120 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
