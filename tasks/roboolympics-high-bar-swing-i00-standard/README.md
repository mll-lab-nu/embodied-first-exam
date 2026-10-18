# roboolympics-high-bar-swing-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-high-bar-swing-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `high_bar_swing` / seed 0 |
| Oracle | `full` — Reference: from the dead hang a leg pump that tucks on the way up and extends elsewhere takes the extended body over the top: one full giant swing at 23.6 s; 8 of 8 parameter sets (24 to 35 s) when it was written. The privileged twin's reference rows (2362 control steps, success after 23.62 s) streamed through the client. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Hanging from the high bar by both hands, do one giant swing: take your extended body in a full circle around the bar, without letting go. (RoboOlympics `high-bar-swing`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Nothing pushes you: the swing has to be pumped up from rest by moving the legs, the waist and the shoulders in time with the pendulum, against motors of 88 N m at the hips and 25 N m in the arms, until the body goes over the top of the bar extended. A simple leg pump is known to stall a little above the horizontal. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the client (`solution/rows.npz`, recorded by scripts/roboolympics/make_oracles.py). Reference: from the dead hang a leg pump that tucks on the way up and extends elsewhere takes the extended body over the top: one full giant swing at 23.6 s; 8 of 8 parameter sets (24 to 35 s) when it was written. The privileged twin's reference rows (2362 control steps, success after 23.62 s) streamed through the client.

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The bar is a competition horizontal bar: 0.028 m thick, 2.8 m above the floor, 2.4 m long between its two uprights, along the y axis; it turns freely about its own axis. Both hands grip it from the start. Your swing angle is the angle between straight down and the line from the bar to your centre of mass, seen from the side. The giant swing is a full circle of that line: the angle must travel 360.0 degrees in one direction (forwards or backwards) without turning back; a turn back of more than 5.0 degrees starts the count again from where you turned. The body must be extended over the top: whenever your centre of mass is higher than the bar it must be at least 0.74 m from the bar (nine tenths of the 0.82 m of your dead hang: a slight pike or arch passes, a tuck or bent arms do not); if it comes closer there, the count starts again from that point. You succeed the moment the count reaches 360.0 degrees. Below the bar you may bend as you like to build up the swing. You fail the moment either hand no longer grips the bar, any part of you touches the uprights, the mats or the floor, or after 60 s.

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
| Category | parkour-apparatus-balance |
| Rule book | FIG Apparatus Norms, men's artistic gymnastics, horizontal bar: the bar 2.80 m above the floor (2.60 m above the 0.20 m landing mats), 2.40 m between the uprights, 28 mm in diameter; FIG Code of Points, horizontal bar: the giant swing (a full circle round the bar with the body extended); deviations: the grip (no fingers on this robot): each hand's grip is a rigid hold on the bar (the simulator's weld), and the bar turns freely in its bearings about its own axis in place of the hands turning round a fixed bar, because the hands cannot wrap a bar; opening a grip lets go · FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, not the norm's elastic steel bar on tensioned cables, because the simulator has rigid bodies only (the real bar's spring helps the gymnast: this is not easier) · FIG Code of Points (a routine is scored): one element is judged pass or fail from a dead hang, because the task is a single action; the mount to the hang is given |
| Stages | over the top → full circle |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
