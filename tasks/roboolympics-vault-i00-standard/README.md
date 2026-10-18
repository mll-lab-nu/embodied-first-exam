# roboolympics-vault-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-vault-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `vault` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_vault.py: positive by injection (a ballistic handspring: 3.5 m/s forward, 5.3 m/s up, 6.2 rad/s; both hands really on the 1.35 m table; stopped at touchdown); negatives: not over the table, another part on the table, no hand on it, not on the feet, off the mat; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Vault over the vault table at the end of the run-up: go over it with only your hands touching it, land on your feet on the landing mat and stand. (RoboOlympics `vault`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The table is 1.35 m high and the robot has no running policy: its walk reaches about 0.65 m/s and its best standing jump lifts it far less than a metre, so the 67 kg body has to be carried over the table by a take-off and arm support that nobody has built for it. It must then come down feet first from above 1.35 m and absorb the landing without a hand on the mat. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-vault-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The vault table's top is 1.35 m above the floor, 1.2 m long (along +x, the way you face) and 0.95 m wide, on a pedestal; its near edge is 25.0 m ahead of where your pelvis starts, centred on your line. A springboard stands before it: a board 1.2 m long and 0.6 m wide (20.0 kg), hinged at its low near end and rising to 0.22 m at its high end, which is 0.5 m before the table; it rests on a spring of 120000.0 N m/rad about the hinge (damping 300.0 N m s/rad) and gives way under load down to the floor. The landing mat begins at the table's far edge: 6.0 m long, 2.5 m wide, 0.2 m thick, softer than the floor (contact time constant 0.04 s). A valid vault, in order: at least one hand touches the table's top surface (a contact within 0.02 m of the top plane; a hand against a side of the table does not count); your pelvis passes the table's far edge; your feet touch the mat; you stand on the mat for 1.0 s without a break (only your feet on it, your torso within 20.0 degrees of vertical, your pelvis moving no faster than 0.35 m/s). You fail the moment: any part of you other than your hands (the wrist links and the palms; not the forearms) touches the table or its pedestal; your pelvis is between the table's near and far edges without being higher than its top and within its width (you went under, beside or round it); your pelvis passes the far edge before a hand has touched the top; after your pelvis has passed the far edge, any part of you touches the floor, or a part other than your feet touches the mat before the stand is complete. Before the table there is no fall rule: any part of you may touch the floor and the springboard, and using the springboard is not required. The attempt ends after 80 s of robot time. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Rule book | FIG Apparatus Norms (men's vault): the vault table 1.35 m high, its top 1.20 m long and 0.95 m wide; a run-up of 25 m, 1 m wide; a springboard 1.20 m by 0.60 m, 0.22 m high at its high end; landing mats 6 m by 2.5 m, 0.20 m thick. FIG Code of Points for Men's Artistic Gymnastics, the vault section, for what makes a vault invalid: no support of a hand on the table, a foot on the table, not landing feet first; deviations: Apparatus Norms (springboard): the board is a rigid plate hinged at its low end on one spring of 120000.0 N m/rad (83 kN/m at its high end with the default) with light damping, not a leaf-spring board with coil springs; its elasticity is not FIG-tested (the norm is a drop test on the real board) · Code of Points (springboard position): the board stands at a fixed place, its high end 0.5 m before the table, instead of where the gymnast puts it (nobody sets up the venue for the robot) · Code of Points (the vault): any passage over the table with hand support counts, with no vault number, no required take-off from the board and no execution score: the family asks whether the vault is valid, not how well it is done · Code of Points (landing): judged to a stand of 1.0 s on the mat with nothing but the feet on it; the landing mat's corridor lines are not judged · Apparatus Norms (run-up): the robot starts at the far end of the 25.0 m run-up (the gymnast may start nearer); the table's safety collar and the mat around the board are left out |
| Stages | hands on the table → over the table → landing → stand |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 8000 control steps (80 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
