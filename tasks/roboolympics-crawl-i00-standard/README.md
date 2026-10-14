# roboolympics-crawl-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-crawl-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `crawl` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_crawl.py: positive by injection (the robot laid prone, 0.27 m high, and dragged under the 21 wires by a force on the pelvis); negatives: walking upright into a wire, on hands and knees (0.46 m: a wire touched), round, over, not under, stopping inside. No crawling controller exists; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Get under the low wires in front of you and crawl the whole course until your whole body is beyond the last wire, without touching a wire. (RoboOlympics `crawl`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Neither built-in gait works below 0.45 m, and on hands and knees this robot is about 0.46 m high, just too tall: it has to get down from standing and move 10.0 m and its own length flat on the ground with joint commands of its own, never lifting any part into a wire. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-crawl-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, then the service replays the recorded attempt in a fresh simulator;
`tests/grade.py` reads `/data/final.json`: pass iff the live run and the replay succeed and end in the same state. The
rules: The obstacle is a lane along +x, 2.0 m wide between two rows of posts, centred on y = 0. Horizontal wires cross it every 0.5 m over 10.0 m: the first is 1.0 m ahead of where your pelvis starts, the last 10.0 m further on. Each wire is 0.008 m thick with its centre 0.45 m above the ground. You succeed when your whole body (every part of you) is beyond the last wire, having passed under all of them. There is no fall rule: any part of you may touch the ground, and you need not stand up at the end. You fail the moment any part of you touches a wire; if your pelvis, while it is between the first and the last wire, is higher than 0.45 m (going over) or outside the lane (going round, beyond a row of posts); if your whole body is beyond the last wire without your pelvis having passed under the wires; or after 120 s. The posts may be touched. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | parkour-apparatus-balance |
| Rule book | No federation rule book: the low-wire crawl of military obstacle courses and obstacle-course racing (wires strung about 18 in, 0.45 m, above the ground; the athlete passes under all of them and may not go round or over). The layout is this benchmark's: wires every 0.5 m over 10 m; deviations: the wires: each wire is a rigid, fixed bar 8 mm thick between two posts, not a slack (barbed) wire, because the simulator has rigid bodies only; touching one fails the attempt, as a judge's fault for a snagged wire · the ground: level and rigid with a friction coefficient of 1.0, not sand or mud, because the simulator's ground is rigid |
| Stages | under the first wire → half way → through |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 12000 control steps (120 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
