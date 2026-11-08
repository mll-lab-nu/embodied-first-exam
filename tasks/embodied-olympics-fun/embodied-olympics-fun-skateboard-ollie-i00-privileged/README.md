# embodied-olympics-fun-skateboard-ollie-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-skateboard-ollie-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `skateboard_ollie` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (a real ankle and hip balance controller holds the robot on the resting board, and at t = 1.2 s one upward velocity of 1.25 m/s is written to the robot's floating base and to the board's; the 6.2 cm clearance, the landing and the 1 s stand are physics under the same controller), for a stationary ollie (the board at rest; clear 5 cm, land on four wheels with both feet, stand still 1 s). No real ollie: 5291 scripted stationary ollies (IK pop, drag, level and land; parameter searches) cleared 5 cm in 565 runs (the board up to about 0.9 m), but only 6 landed and none stood 1 s; of 4810 rolling attempts none rode away; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Ollie the skateboard from a standstill: pop the tail, take the board up with your feet until all of it is at least 0.05 m off the ground, land on it and stand still on it for 1.0 s. (Embodied Olympics `skateboard-ollie`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The ollie is a timed whole-body skill on a free board: the tail has to be snapped down with the front foot unloaded, the front foot has to drag the rising board up and level it while the robot is in the air, and the robot has to land on a narrow deck that rolls and steers when it tilts. Even standing still, the board is unstable under a rigid rider (its trucks tilt and steer), so the ankles have to balance it before and after the trick.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a real ankle and hip balance controller holds the robot on the resting board, and at t = 1.2 s one upward velocity of 1.25 m/s is written to the robot's floating base and to the board's; the 6.2 cm clearance, the landing and the 1 s stand are physics under the same controller), for a stationary ollie (the board at rest; clear 5 cm, land on four wheels with both feet, stand still 1 s). No real ollie: 5291 scripted stationary ollies (IK pop, drag, level and land; parameter searches) cleared 5 cm in 565 runs (the board up to about 0.9 m), but only 6 landed and none stood 1 s; of 4810 rolling attempts none rode away.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: The skateboard: a 0.8 m deck, 0.19 m wide, with a kicktail and a nose turned up 18.0 degrees, on two trucks 0.356 m apart with four 0.026 m-radius wheels; the trucks steer when the deck tilts (pivot axis 63.0 degrees, 100.0 N m/rad of bushing stiffness, a stop at 12.0 degrees of tilt). Nothing holds your feet to it: grip tape (friction 1.0) only. The attempt, in this order: (1) pop: the board leaves the ground (no part of it touching anything but you) with a foot on its deck as it leaves; (2) clear: in the same flight of the board, every part of it (deck, trucks, wheels) is at least 0.05 m above the ground; (3) landed: then all four wheels on the ground (each within 0.005 m of it) with both feet on the deck; (4) stand: for 1.0 s without a break, both feet on the deck (contact breaks of at most 0.05 s), all four wheels on the ground, your torso within about 37 degrees of upright (the cosine of its tilt at least 0.8) and your pelvis slower than 0.35 m/s. You succeed at (4). A pop that does not clear may be followed by another. You fail if any part of you other than the feet and shins touches the board (an ollie is done without hands), if any part of you, a foot included, touches the ground or your pelvis drops below 0.3 m (a bail), if the board touches the ground upside down, after the landing if a foot stays off the deck for more than 0.2 s or your torso tilts beyond that limit, and at 8 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | World Skate, Skateboarding Technical Commission, Street & Park Competition Rules (update of April 2025): Technical Specifications of Materials, Skateboard (a deck with four wheels attached by trucks; it cannot be physically attached to the skater's feet); the Runs + Tricks format (single tricks, one attempt each); Makes versus Bails (the Head Judge decides whether a trick is landed); deviations: Runs + Tricks format: one trick, a stationary ollie on flat ground (the board at rest at the start, no obstacle), the whole board rising at least 0.05 m above the ground, instead of an ollie at speed onto or over a street course's obstacle: 0.05 m is this benchmark's round number (the robot's measured pops lift the board higher), and the stationary form is the one this robot can attempt without a push-off on one leg, which it has no balance for · Makes versus Bails: the Head Judge's call is replaced by fixed criteria (a make: the board leaves the ground with a foot on it and rises clear by 0.05 m, all four wheels come down with both feet on the deck, and the robot stands still on the board for 1.0 s; World Skate judges an ollie made when the rider lands on the board); the judges' score (difficulty, execution, style) is not given · the skateboard is rigid bodies: the deck is three boxes (no concave, no flex), the wheels cylinders, the truck a hinge about its pivot axis with a linear torsion spring for the bushings and a hard stop at 12.0 degrees of deck tilt (the bushings' progressive stiffening is not modelled) · the robot is the size of a child (1.32 m), so the deck is a 7.5 in board, the width skate shops give for that height, instead of an adult's 8 to 8.5 in |
| Stages | pop → clear → landed → stand |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `5930430815b658aa17cf828eded8ffa9fe4f41d47e91094156b6b5c704791409` |
| Episode | 800 control steps (8 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
