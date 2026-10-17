# roboolympics-standing-long-jump-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-standing-long-jump-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `standing_long_jump` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_standing_long_jump.py: positive by injection (3.5 m/s forward and 2.5 m/s up from the stance, a perfect landing: a mark of 1.54 m, the stand is the robot's own); negatives: too short, a fall, a dive, a foot over the line, a step or shuffle before the take-off, a leg tuck. The published best for this robot is 0.90 m; a real open-loop push-off of ours takes off legally and lands on its head; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Do a standing long jump: from a standstill behind the take-off line, take off from both feet without a step, land on your feet at least your own height beyond the line, and stand. (RoboOlympics `standing-long-jump`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Neither built-in gait can jump. The take-off needs both legs' full power in one coordinated push with the body leaning well ahead of the feet, and a jump of the robot's own height comes down at more than 3 m/s: the legs have to absorb it without a hand or the pelvis going down. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-standing-long-jump-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The take-off line is x = 0; you jump towards +x. Your jump is your first flight (nothing of you touches the ground) of at least 0.1 s. Until then: no part of a foot that is on the ground may be on or over the line (the whole foot counts, also the parts of it that are in the air); no run-up and no step: every point where a foot touches the ground must lie within 0.03 m of the place where that foot's sole stood at t = 0, and neither foot may be off the ground for more than 0.05 s while the other is on it (so both feet leave the ground within 0.05 s of each other: a two-foot take-off). Rising on the toes is allowed. The flight must be a jump: your pelvis has to rise at least 0.05 m above its height at lift-off. The first contact after the flight must be with your feet only. The mark is the point nearest the take-off line at which any part of you touches the ground from that landing until you have stood; it must be at least 1.32 m beyond the line. After the landing you may step; you succeed once you stand for 1.0 s without a break: only your feet on the ground, your torso within about 20 degrees of vertical, your pelvis slower than 0.35 m/s. A fall fails the attempt at any time: your pelvis lower than 0.35 m, or any part of you other than your feet on the ground. You fail on a foot on or over the line, a step or shuffle before the take-off, a foot that leaves the ground before the other, a flight that is not a jump, a landing that is not on the feet, a mark short of 1.32 m, a fall, or after 20 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | track-and-jumps |
| Rule book | The standing long jump (standing broad jump) of school and club fitness test batteries (Eurofit, ALPHA-Fitness, the Chinese National Student Physical Health Standard): the feet side by side behind the take-off line, a two-foot take-off with no step or preliminary hop, a landing on the feet; the jump is measured from the take-off line to the nearest point of contact at the landing; deviations: the athlete cannot walk up to the line: any step before the take-off is a foul, so the robot is placed with the front ends of its feet 0.05 m behind the line (a rigid foot that pivots on its toes at the push-off swings up to 3 cm forward of where they stood) · the measurement: the mark is the contact nearest the line of any part of the robot from the landing until it has stood for 1.0 s (a step or a hand put back shortens the jump; a fall voids it), where the test measures the heels at the landing · a jump is told from a loss of contact by two numbers the test does not have: a flight of at least 0.1 s in which the pelvis rises at least 0.05 m above its height at lift-off · the qualifying mark, 1.32 m, is the robot's own standing height (FAMILIES.md); the school standards scale with the athlete: adolescent pass marks are roughly 1.0 to 1.3 times body height |
| Stages | take-off → landing → stand |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 2000 control steps (20 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
