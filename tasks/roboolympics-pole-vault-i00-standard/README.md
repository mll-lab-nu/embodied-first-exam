# roboolympics-pole-vault-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-pole-vault-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `pole_vault` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_pole_vault.py: positive by injection (the run-up, the plant and the swing-up are injected: the robot is put on the planted pole 20 degrees short of vertical; from there it really hangs, passes 4 cm over the 2.00 m bar, lets go and lands on the mat); negatives: the bar off its pegs, the ground beyond the zero line before the clearance, a hand moved up the pole, a clearance without the planted pole, round or under the bar, a hand steadying the bar; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Vault over the bar with the pole you carry: plant its tip in the box, leave the ground hanging on it, go over the bar between the uprights and come down on the mat, with the bar still on its pegs. (RoboOlympics `pole-vault`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The bar is 0.2 m above the robot's head: the 67 kg body has to be carried over it hanging on a rigid pole that gives nothing back, by arms whose motors hold 18 to 40 N m, from a run-up that the robot's only gait makes at 0.7 m/s. Nothing built in grips, plants, swings or lets go. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-pole-vault-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: World Athletics rules for the pole vault. You carry the pole (4.0 m long, 0.04 m thick, 2.0 kg; rigid: it does not bend) gripped in your right hand at its middle; either hand can grip it anywhere along its length, and it can be let go and gripped again. The pole touches the ground, the box, the mats, the uprights and the bar, not your body. The runway (40.0 m, 1.22 m wide) leads along +x to the box, which is sunk into the ground: its bottom is 1.00 m long and slopes down from the runway's level at x = -1.08 m to 0.20 m below it at the foot of the stop board (x = -0.10 m); the stop board leans back to the zero line x = 0 at runway level; the box is 0.60 m wide at its front and 0.15 m at the foot of the stop board (your feet do not sink into it: for them it is covered). The bar (4.5 m long, 0.03 m thick, 2.25 kg) rests with its upper side 2.0 m above the ground on two pegs (0.055 m long, 0.013 m thick, 4.3 m apart) that point towards the landing area, 0.8 m beyond the zero line; pushed towards the landing area by half a peg's length, or lifted, it falls. The landing mat (5.0 m x 5.0 m, 0.8 m high, soft) begins 0.15 m beyond the zero line (behind the box its face slopes away at 45 degrees, so the pole can lean on over it); two front pieces of the same height flank the box for 2.0 m before it. The vault: (1) plant: the pole's tip is in the box while a hand grips the pole. (2) take-off: you hang on the planted pole: for at least 0.15 s in one flight nothing of you touches anything but the pole and the bar while a hand grips the pole and its tip rests in the box. (3) clearance: in that same flight your pelvis and both feet (the ankle joints) cross the plane of the bar's nearer edge between the pegs and higher than the bar's upper side (one that comes back over the plane has not passed it), and every part of you gets beyond that plane; you may touch the bar. (4) You come down, on any part of your body, with or without the pole. You succeed when 2.0 s after your landing the bar is still on its pegs. A fall is not a failure by itself. You fail if the bar drops more than 0.05 m at any time, whether you or the pole knocked it; if, before you have cleared the bar, anything of you or the pole touches the ground or the mats beyond the zero line; if your pelvis or a foot passes the bar's plane outside the pegs or not higher than the bar; if you clear the bar without the 0.15 s on the planted pole (a jump without the pole); if, in the flight of the vault, a hand grips the pole more than 0.05 m farther from its tip than your upper hand did at lift-off (climbing); if your hands touch the bar for more than 0.1 s in all (steadying it); or after 60 s (the time allowed for a trial). No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Rule book | World Athletics Competition and Technical Rules, 2024 edition: TR 28 (28.1 the bar may be moved up to 0.80 m from the zero line towards the landing area; 28.2 failures: (a) the bar does not remain on both pegs, (b) touching the ground or the landing area beyond the zero line with the body or the pole without first clearing the bar, (c) moving a hand up the pole after leaving the ground, (d) steadying the bar with a hand; 28.6 a runway of at least 40 m; 28.8 the box; 28.9-28.10 the uprights and pegs 4.28 to 4.37 m apart, the 4.50 m bar of at most 2.25 kg; 28.12 a landing area of at least 5 m x 5 m x 0.8 m with front pieces 2 m long), TR 25.17 (one minute for a trial); deviations: TR 28.11 (vaulting poles: any material, length and diameter, a smooth surface): the pole is rigid: a 4.0 m, 2.0 kg rod that does not bend and stores no energy (the simulator has no validated model of a bending pole) · the grip: the robot's hand holds the pole by the benchmark's grip (a weld at the palm, anywhere along the pole), not by fingers; the pole passes through the robot's own body and is stopped only by the grip · TR 28.8 (the box): it is sunk below the runway as the rule draws it, but only the pole (and the bar) can enter it; for the robot's feet it is covered at runway level; its side walls are planes · TR 28.2(b), (c), (d) are judged geometrically: any contact of the robot or the pole with the ground or the mats beyond the zero line before the bar is cleared; a hand that closes on the pole more than 0.05 m farther from its tip than the upper hand's grip was at lift-off; a hand on the bar for more than 0.1 s in all · a vault is told from a jump by a number: in the flight that clears the bar the robot must hang on the pole (a hand gripping it, its tip in the box, nothing of the robot on the ground) for at least 0.15 s; the pelvis and the feet (the ankle joints) must pass the bar's plane between the pegs and above the bar; the bar is cleared when every part of the robot is beyond its plane · TR 28.2(a): the bar is judged 2.0 s after the landing; it is off its pegs when its centre is more than 0.05 m below its resting height; the pegs are square in section, the bar rigid · TR 28.12 (the landing area): the mats are boxes with a soft, overdamped contact (time constant 0.08 s, full stiffness only 0.1 m deep); the mat's face behind the box slopes away at 45 degrees as the rule asks, the front pieces' faces beside the box are vertical, and the uprights stand in the mat without a recess; no wind; one trial at one height, 2.0 m (FAMILIES.md; the men's world record is 6.30 m) · TR 28.1 (the athlete chooses where the bar stands, 0 to 0.80 m beyond the zero line): it stands 0.8 m beyond it |
| Stages | plant → take-off → clearance → bar stays |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
