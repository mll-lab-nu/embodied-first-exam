# roboolympics-high-bar-swing-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-high-bar-swing-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `high_bar_swing` / seed 0 |
| Oracle | `full` — Reference: from the dead hang a leg pump that tucks on the way up and extends elsewhere takes the extended body over the top: one full giant swing at 23.6 s; 8 of 8 parameter sets (24 to 35 s) when it was written. Measured (make_oracles.py): success after 23.62 s of the 60 s limit, live and in a fresh replay, ending in the same state. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Hanging from the high bar by both hands, do one giant swing: take your extended body in a full circle around the bar, without letting go. (RoboOlympics `high-bar-swing`: one Unitree G1 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Nothing pushes you: the swing has to be pumped up from rest by moving the legs, the waist and the shoulders in time with the pendulum, against motors of 88 N m at the hips and 25 N m in the arms, until the body goes over the top of the bar extended. A simple leg pump is known to stall a little above the horizontal.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Reference: from the dead hang a leg pump that tucks on the way up and extends elsewhere takes the extended body over the top: one full giant swing at 23.6 s; 8 of 8 parameter sets (24 to 35 s) when it was written. Measured (make_oracles.py): success after 23.62 s of the 60 s limit, live and in a fresh replay, ending in the same state.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The bar is a competition horizontal bar: 0.028 m thick, 2.8 m above the floor, 2.4 m long between its two uprights, along the y axis; it turns freely about its own axis. Both hands grip it from the start. Your swing angle is the angle between straight down and the line from the bar to your centre of mass, seen from the side. The giant swing is a full circle of that line: the angle must travel 360.0 degrees in one direction (forwards or backwards) without turning back; a turn back of more than 5.0 degrees starts the count again from where you turned. The body must be extended over the top: whenever your centre of mass is higher than the bar it must be at least 0.74 m from the bar (nine tenths of the 0.82 m of your dead hang: a slight pike or arch passes, a tuck or bent arms do not); if it comes closer there, the count starts again from that point. You succeed the moment the count reaches 360.0 degrees. Below the bar you may bend as you like to build up the swing. You fail the moment either hand no longer grips the bar, any part of you touches the uprights, the mats or the floor, or after 60 s.

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
| Rule book | FIG Apparatus Norms, men's artistic gymnastics, horizontal bar: the bar 2.80 m above the floor (2.60 m above the 0.20 m landing mats), 2.40 m between the uprights, 28 mm in diameter; FIG Code of Points, horizontal bar: the giant swing (a full circle round the bar with the body extended); deviations: the grip (no fingers on this robot): each hand's grip is a rigid hold on the bar (the simulator's weld), and the bar turns freely in its bearings about its own axis in place of the hands turning round a fixed bar, because the hands cannot wrap a bar; opening a grip lets go · FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, not the norm's elastic steel bar on tensioned cables, because the simulator has rigid bodies only (the real bar's spring helps the gymnast: this is not easier) · FIG Code of Points (a routine is scored): one element is judged pass or fail from a dead hang, because the task is a single action; the mount to the hang is given |
| Stages | over the top → full circle |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `3af93c91e42df7f76aeca9e38572cfdbc52ff49ffe9ac556e4e3c2147f53a241` |
| Episode | 6000 control steps (60 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
