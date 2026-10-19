# roboolympics-fun-shuttle-run-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-fun-shuttle-run-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `shuttle_run` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_shuttle_run.py: positive by injection (real running on all four legs, the three about-turns set by hand: 23.0 s); negatives: turning short, a foot only on the line, two legs only, arms over the finish without the torso, down, walking. With the built-in gaits a leg takes about 6 s and an about-turn on the walking policy 3.4 s: about 33 s against the 30 s limit; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Run the 4 x 10 m shuttle: to the far line, back to the start line, to the far line again and back through the start line, putting a foot on the ground beyond the line at each turn, as fast as you can. (RoboOlympics `shuttle-run`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Forty metres with three reversals in 30 s: the walking gait covers 19 m in that time, and the running gait turns slowly, needs metres to stop, and falls when it is handed over to another gait at speed, so every leg has to be braked and reversed without losing seconds. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-fun-shuttle-run-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: Two lines cross the floor: the start line x = 0 and the far line x = 10.0 m (the planes meant are the edges of the painted lines that face each other). The clock starts at t = 0. You run four legs: to the far line, back to the start line, to the far line, back to the start line. At each of the three turns you must put a foot on the ground wholly beyond the line: every part of that foot at x > 10.0 m at the far line (turns 1 and 3), at x < 0 at the start line (turn 2); a foot on the line does not count. The turns count in this order only. After the third turn you finish at the moment the leading point of your torso (not the head, arms, legs or feet) reaches the start line. Which way you face and how you turn is up to you. You succeed when you finish within 30 s of robot time. A fall does not end the attempt: you are down while your pelvis is below 0.4 m, you may get up and go on, but 10.0 s down in a row end it. You fail when down for 10.0 s, or after 30 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | track-and-jumps |
| Rule book | The 4 x 10 m shuttle run of school fitness test batteries (the speed-agility test of the ALPHA-Fitness battery): two parallel lines 10 m apart, four legs, the line crossed at every turn, the time taken when the runner crosses the start line at the end of the fourth leg; deviations: the sponges the ALPHA version has the runner carry between the lines are left out (the robot has no fingers), and a turn needs one foot on the ground beyond the line where ALPHA asks for both · the start: no starter and no reaction time; the clock runs from t = 0 with the robot standing behind the start line · the finish is timed as in athletics (World Athletics TR 19): the leading point of the torso link's collision mesh on the plane of the start line, interpolated between 1 ms physics steps · a fallen runner: a robot whose pelvis is below 0.4 m is down; it may get up and go on, but 10.0 s down in a row end the attempt · the qualifying time, 30 s, is this benchmark's own round number: school norms for this test are 10 to 14 s |
| Stages | turn 1 → turn 2 → turn 3 → finish |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 3000 control steps (30 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
