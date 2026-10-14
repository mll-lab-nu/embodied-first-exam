# roboolympics-balance-board-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-balance-board-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `balance_board` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_balance_board.py: positive by injection (a spring-damper force on the torso, a helper's hand, for the 30 s); negatives: the do-nothing agent (the deck is down at 2.6 s), the walking policy, leaning, left alone after 20 s, off the board. A linear feedback on leg sway rides the full 30 s from the exact start but falls after 14 to 28 s when started 1 mm off, so it is not shipped as a reference solution; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Stay balanced on the roller board for 30.0 s: neither end of the deck nor any part of you may touch the floor. (RoboOlympics `balance-board`: one Unitree G1 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Two unstable motions are coupled: the deck tilts on the roller and the roller rolls away under the deck. Neither the platform's stance nor the walking policy corrects them; the legs have to shift the body's weight against the board fast enough to keep the roller between the feet for 30.0 s.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a spring-damper force on the torso, a helper's hand, for the 30 s); negatives: the do-nothing agent (the deck is down at 2.6 s), the walking policy, leaning, left alone after 20 s, off the board. A linear feedback on leg sway rides the full 30 s from the exact start but falls after 14 to 28 s when started 1 mm off, so it is not shipped as a reference solution.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The board is a rigid deck 0.76 m long (left to right), 0.38 m wide and 0.018 m thick, 2.7 kg, lying loose on a roller: a free cylinder of 0.085 m radius, 0.46 m long, 1.8 kg, whose axis points fore-aft and which rolls on the floor to your left and right. Nothing holds the deck to the roller or the roller to the floor but contact and friction (coefficient 1.0); there is no spring. A stop 0.02 m high and 0.03 m long under each end of the deck keeps the roller from rolling out from under it. You succeed when 30.0 s have passed from the start without a failure. You fail the moment any part of the deck (an end or a stop) touches the floor, any part of you touches the floor or the roller, any part of you other than a foot touches the deck (a fall on the board), or neither of your feet has touched the deck for more than 1.0 s (you have left the board). With the roller in the middle, an end of the deck meets the floor at a tilt of about 24 degrees. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Rule book | No federation rule book: the roller balance board (Indo Board style rocker-roller trainer): a rigid deck 0.76 m x 0.38 m lying loose on a free roller of 0.085 m radius, with a stop under each end of the deck; the standard is the balance trainer's: time on the board with neither end of the deck nor the rider touching the floor; deviations: the board: deck and roller are rigid bodies (a 2.7 kg box and a 1.8 kg hollow cylinder) with a friction coefficient of 1.0 between deck, roller and floor, without grip tape or a rubber-lined roller, because the simulator has rigid bodies only · the mount: the robot starts standing on the level deck, centred over the roller (an unstable equilibrium), instead of stepping onto a deck that rests on one end, because the task is the ride, a single action |
| Stages | 10 s → 20 s → 30 s |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `1155c0cb31e595b7bd2e826cdd811217e7bb47f6cd1a3b36a25b480ebdabb719` |
| Episode | 3050 control steps (30.5 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
