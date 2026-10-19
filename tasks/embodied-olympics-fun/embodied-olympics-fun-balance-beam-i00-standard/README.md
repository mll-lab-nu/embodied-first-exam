# embodied-olympics-fun-balance-beam-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-balance-beam-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `balance_beam` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_balance_beam.py: positive by injection (the robot slid along the 10 cm beam in its tandem pose, 4 mm per step); negatives: `stand` mode (off in 1.5 s), the walking policy (off in 0.5 s), stopping short, past the end, lying on it, beside it. The tandem hold on joint targets is stable; a real walk on a 10 cm beam was not attempted; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Walk along the balance beam from the end you stand on to the other end and stand there, without anything touching the floor. (Embodied Olympics `balance-beam`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The beam is 0.1 m wide and the robot's built-in stance and gait keep the feet 0.24 m apart, so neither can be used: every step is a single-leg balance on a sole 0.07 m wide, 1.25 m above the floor, for 5.0 m. No controller of this robot is known to do it. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-balance-beam-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The beam is a competition balance beam: 5.0 m long, 0.1 m wide on top and 0.16 m deep, its top 1.25 m above the floor; it runs along +x from x = 0 to x = 5.0 m, centred on y = 0, on two supports. You must get from the end you start on to the far end on your feet. The far end is the last 0.5 m of the beam. You succeed when both feet are on the beam with every point at which they touch it inside the far end, and you then stand there for 2.0 s without a break: only your feet touch the beam, your torso is within 20.0 degrees of vertical and your pelvis moves slower than 0.35 m/s. You fail the moment any part of you touches the floor or the beam's supports (a fall from the beam), the moment any part of you other than a foot touches the beam (a fall on the beam: no hands, knees or sitting), or after 90 s. Leaving the beam with both feet (a hop) is allowed as long as you come down on it on your feet. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (4090-ws1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | parkour-apparatus-balance |
| Rule book | FIG Apparatus Norms (Fédération Internationale de Gymnastique), women's artistic gymnastics, balance beam: length 5.00 m, width of the top 0.10 m, depth of the beam body 0.16 m, top 1.25 m above the floor; FIG Code of Points, women's artistic gymnastics: a beam exercise lasts at most 1 min 30 s; deviations: FIG Apparatus Norms, balance beam (padding): the beam is rigid with a friction coefficient of 1.0, without the norm's thin elastic padding and suede cover, because the simulator has rigid bodies only · FIG Apparatus Norms, landing mats: there are no 0.20 m mats round the beam; the floor is 1.25 m below the top, because anything touching the floor ends the attempt anyway · FIG Code of Points (a routine is scored, a fall costs 1.00): one pass along the beam is judged pass or fail, because the task is a single action; a hand or any part other than a foot on the beam counts as a fall here |
| Stages | half way → far end → stand |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 9000 control steps (90 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
