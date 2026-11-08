# embodied-olympics-fun-penalty-kick-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-penalty-kick-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `penalty_kick` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (a real walk-up and foot contact, the ball's velocity set at the contact to 20 m/s into the corner; also a chip over the keeper); the keeper is a board on a rail driven by a force-limited servo (at most 800 N, 3 m/s), never moved by state writes, and a 15 m/s ball pushes it 3 mm; negatives: an 8 m/s corner shot saved by the keeper, a weak kick, wide, over the bar, a second touch, in without a kick, a body contact. Beating the keeper takes about 12 m/s to a corner; a G1 foot running into the ball at 4 m/s gives 3 to 5 m/s; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Take a penalty kick: with one kick of a foot, send the ball that lies on the penalty mark into the official goal 11 m away, past the goalkeeper dummy. (Embodied Olympics `penalty-kick`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The dummy reaches any ball that needs more than about 1.45 s for the 11 m: the kick has to send a 0.43 kg ball off at about 12 m/s or more and into a corner (or over the dummy and under the bar). The robot weighs 33 kg and has no kicking skill; a foot that merely runs into the ball at the running policy's 4 m/s sends it off at 3 to 5 m/s.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a real walk-up and foot contact, the ball's velocity set at the contact to 20 m/s into the corner; also a chip over the keeper); the keeper is a board on a rail driven by a force-limited servo (at most 800 N, 3 m/s), never moved by state writes, and a 15 m/s ball pushes it 3 mm; negatives: an 8 m/s corner shot saved by the keeper, a weak kick, wide, over the bar, a second touch, in without a kick, a body contact. Beating the keeper takes about 12 m/s to a corner; a G1 foot running into the ball at 4 m/s gives 3 to 5 m/s.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: A size-5 football (0.22 m across, 0.43 kg, in air) lies at rest on the penalty mark, 3.0 m straight ahead of you; the goal line is 11.0 m beyond the mark. The goal is 7.32 m wide between the posts and 2.44 m high under the crossbar (posts and bar 0.12 m thick), centred on the line through you and the mark. A goalkeeper dummy, a board 1.9 m high, 0.6 m wide, 0.3 m thick and 80.0 kg, stands on the goal line at the centre of the goal on a carriage that runs on a rail along the line, driven by a motor of at most 800.0 N; from 0.25 s after your kick the motor drives it at up to 3.0 m/s towards the point where the ball, going on as it moves at that moment, would cross the line, and it blocks the ball (a hit pushes it along the rail). The kick is a contact of a foot or an ankle of yours with the ball (the parts below the shin); every such contact within 0.15 s of the first belongs to the one kick. You succeed at the moment the whole ball is over the goal line between the posts and under the bar; it may touch the posts, the bar, the dummy and the ground on the way. You fail if any other part of you touches the ball at any time, if a foot touches the ball again later than 0.15 s after the first contact (a second touch), if the ball is not moving towards the goal line at the end of the kick, if the whole ball crosses the goal line outside the goal, if after the kick the ball has been slower than 0.1 m/s for 1.0 s, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 15 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Category | football-and-volleyball |
| Rule book | IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m with posts and crossbar 12 cm wide, the penalty mark 11 m from the goal line, the penalty area, the goal area and the penalty arc), Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 14 (the penalty kick: the ball at rest on the mark, kicked forward, the goalkeeper on the goal line between the posts until the kick), Law 10 (kicks from the penalty mark: one kick, which is over when the ball stops moving or goes out of play; the kicker may not play the ball a second time) and the glossary (a kick is a contact with the foot or the ankle); deviations: Law 14 (the goalkeeper): the goalkeeper is a dummy, a rigid board 1.9 m high, 0.6 m wide and 80.0 kg on a carriage that runs on a rail along the goal line, driven by a linear servo motor of at most 800.0 N (at most 3.0 m/s); the rail's end stops keep it between the posts. It starts at the centre and, from 0.25 s after the kick, the motor drives it towards the point where the ball's velocity of that moment would take it over the goal line. The ball pushes it along the rail when it hits it; it neither dives, jumps nor uses hands. An opponent cannot be simulated otherwise. · Law 14 (the kick): the referee takes every contact of a foot with the ball within 0.15 s of the first as the one kick; any later contact is a second touch. A referee's eye is replaced by this number. · Law 14 says the ball is kicked; the Laws do not name the part of the leg. Here the kick is made with a foot or an ankle (the parts below the shin): a contact of the ball with a shin or any other part is a failure. · Law 1: only the goal end of the field is there (the penalty area, the goal area, the mark and the arc are painted); the goal's net is a rigid cage 2.0 m deep; there is no wind and no other player. |
| Stages | kick → goal |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `788a1a870bb9b5df82b10d1ac4df36d256ffae3a98a41f25248dca4801ffe92f` |
| Episode | 1500 control steps (15 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
