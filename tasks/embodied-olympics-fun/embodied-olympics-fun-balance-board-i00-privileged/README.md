# embodied-olympics-fun-balance-board-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-balance-board-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `balance_board` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: the start is just after a mount: the deck 3 degrees from level with its left end low, the robot standing square on it and tilted with it, its centre of mass 4.2 cm left of the roller's line of contact; left alone the deck is down at 0.8 s. Positive by injection (a spring-damper force on the torso, a helper's hand, for the 30 s: the deck brought level, at most 3.0 degrees); negatives: the do-nothing agent, the walking policy, the weight over one end, left alone after 20 s, off the board, lying on the deck. A feedback tuned for an exactly level start, which holds the board there without visible motion, falls at 0.85 s from this start, as does a linear ride; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Stay balanced on the roller board for 30.0 s: neither end of the deck nor any part of you may touch the floor. (Embodied Olympics `balance-board`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Two unstable motions are coupled: the deck tilts on the roller and the roller rolls away under the deck. Neither the platform's stance nor the walking policy corrects them; the legs have to shift the body's weight against the board fast enough to keep the roller between the feet for 30.0 s.

## Reference solution
None. No reference controller exists for this family yet: the start is just after a mount: the deck 3 degrees from level with its left end low, the robot standing square on it and tilted with it, its centre of mass 4.2 cm left of the roller's line of contact; left alone the deck is down at 0.8 s. Positive by injection (a spring-damper force on the torso, a helper's hand, for the 30 s: the deck brought level, at most 3.0 degrees); negatives: the do-nothing agent, the walking policy, the weight over one end, left alone after 20 s, off the board, lying on the deck. A feedback tuned for an exactly level start, which holds the board there without visible motion, falls at 0.85 s from this start, as does a linear ride.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: The board is a rigid deck 0.76 m long (left to right), 0.38 m wide and 0.018 m thick, 2.7 kg, lying loose on a roller: a free cylinder of 0.085 m radius, 0.46 m long, 1.8 kg, whose axis points fore-aft and which rolls on the floor to your left and right. Nothing holds the deck to the roller or the roller to the floor but contact and friction (coefficient 1.0); there is no spring. A stop 0.02 m high and 0.03 m long under each end of the deck keeps the roller from rolling out from under it. You succeed when 30.0 s have passed from the start without a failure. You fail the moment any part of the deck (an end or a stop) touches the floor, any part of you touches the floor or the roller, any part of you other than a foot touches the deck (a fall on the board), or neither of your feet has touched the deck for more than 1.0 s (you have left the board). With the roller in the middle, an end of the deck meets the floor at a tilt of about 24 degrees. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Category | parkour-apparatus-balance |
| Rule book | No federation rule book: the roller balance board (Indo Board style rocker-roller trainer): a rigid deck 0.76 m x 0.38 m lying loose on a free roller of 0.085 m radius, with a stop under each end of the deck; the standard is the balance trainer's: time on the board with neither end of the deck nor the rider touching the floor; deviations: the board: deck and roller are rigid bodies (a 2.7 kg box and a 1.8 kg hollow cylinder) with a friction coefficient of 1.0 between deck, roller and floor, without grip tape or a rubber-lined roller, because the simulator has rigid bodies only · the mount: a rider steps onto a deck that rests on one end and rolls it up to level; the robot does not step on: it starts standing square on the deck just after that mount, the deck 3.0 degrees from level with its left end low, resting on the roller under its middle, the robot tilted with it (feet flat on the deck), its centre of mass about 4 cm left of the roller's line of contact and everything at rest; it has to bring the board level itself. The start is the same in every trial (no random perturbation), because a trial is one frozen instance |
| Stages | 10 s → 20 s → 30 s |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `e885272e309a01725c5e503c90dda51599fe37f3b35f6975347f68be27772c75` |
| Episode | 3050 control steps (30.5 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
