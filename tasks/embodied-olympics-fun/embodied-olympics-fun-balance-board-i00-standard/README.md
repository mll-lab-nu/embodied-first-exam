# embodied-olympics-fun-balance-board-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-balance-board-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `balance_board` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_balance_board.py: positive by injection (a spring-damper force on the torso, a helper's hand, for the 30 s); negatives: the do-nothing agent (the deck is down at 2.6 s), the walking policy, leaning, left alone after 20 s, off the board. A linear feedback on leg sway rides the full 30 s from the exact start but falls after 14 to 28 s when started 1 mm off, so it is not shipped as a reference solution; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Stay balanced on the roller board for 30.0 s: neither end of the deck nor any part of you may touch the floor. (Embodied Olympics `balance-board`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Two unstable motions are coupled: the deck tilts on the roller and the roller rolls away under the deck. Neither the platform's stance nor the walking policy corrects them; the legs have to shift the body's weight against the board fast enough to keep the roller between the feet for 30.0 s. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-balance-board-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The board is a rigid deck 0.76 m long (left to right), 0.38 m wide and 0.018 m thick, 2.7 kg, lying loose on a roller: a free cylinder of 0.085 m radius, 0.46 m long, 1.8 kg, whose axis points fore-aft and which rolls on the floor to your left and right. Nothing holds the deck to the roller or the roller to the floor but contact and friction (coefficient 1.0); there is no spring. A stop 0.02 m high and 0.03 m long under each end of the deck keeps the roller from rolling out from under it. You succeed when 30.0 s have passed from the start without a failure. You fail the moment any part of the deck (an end or a stop) touches the floor, any part of you touches the floor or the roller, any part of you other than a foot touches the deck (a fall on the board), or neither of your feet has touched the deck for more than 1.0 s (you have left the board). With the roller in the middle, an end of the deck meets the floor at a tilt of about 24 degrees. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Rule book | No federation rule book: the roller balance board (Indo Board style rocker-roller trainer): a rigid deck 0.76 m x 0.38 m lying loose on a free roller of 0.085 m radius, with a stop under each end of the deck; the standard is the balance trainer's: time on the board with neither end of the deck nor the rider touching the floor; deviations: the board: deck and roller are rigid bodies (a 2.7 kg box and a 1.8 kg hollow cylinder) with a friction coefficient of 1.0 between deck, roller and floor, without grip tape or a rubber-lined roller, because the simulator has rigid bodies only · the mount: the robot starts standing on the level deck, centred over the roller (an unstable equilibrium), instead of stepping onto a deck that rests on one end, because the task is the ride, a single action |
| Stages | 10 s → 20 s → 30 s |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 3050 control steps (30.5 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
