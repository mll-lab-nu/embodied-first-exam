# embodied-olympics-fun-double-dutch-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-double-dutch-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `double_dutch` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (a teleported entry and ten 1.5 m/s kicks timed to the ropes: 10 jumps, a landing, success). No controller: entering needs the whole body across 1.0 m of rope sweep in a 0.58 s clear window (1.7 m/s; the G1 walks 0.6 m/s), then hops at 2.2 Hz; the best G1 hop controller found makes 1.7 Hz, 19 hops in 11 s with 10-15 cm clearance; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Jump Double Dutch: enter the two ropes turning in opposite directions and jump them 10 times in a row, one rope per jump, without a rope ever touching you, then land on your feet. (Embodied Olympics `double-dutch`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Neither built-in gait can jump: the robot has to get in between two ropes that sweep the floor in turn every half second, then hop again and again in that rhythm, feet off the ground at the very moment each rope passes and back on balance for the next. A drift out of the middle or a toe left behind catches a rope.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a teleported entry and ten 1.5 m/s kicks timed to the ropes: 10 jumps, a landing, success). No controller: entering needs the whole body across 1.0 m of rope sweep in a 0.58 s clear window (1.7 m/s; the G1 walks 0.6 m/s), then hops at 2.2 Hz; the best G1 hop controller found makes 1.7 Hz, 19 hops in 11 s with 10-15 cm clearance.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: Two rope-turning machines stand 3.9 m apart, at y = -1.95 and +1.95 m; each turns the ends of two ropes on cranks 0.3 m long whose axles are 0.95 m above the floor, 0.4 m apart (one at x = +0.2 m, one at x = -0.2 m), at 1.1 turns per second each, the two ropes in opposite directions and half a turn apart, so that a rope passes under the middle every 0.4545 s, the two ropes taking turns: the rope at +x goes over the top towards -x and under the middle towards +x, the rope at -x the other way round. They are already turning at the start, and they never stop. You start outside the ropes and must enter them: the centre zone is within 0.35 m of x = 0 and 0.5 m of y = 0 (your pelvis decides). A jump counts when a rope passes under both your feet while nothing of you touches the ground and your pelvis is in the centre zone, if that rope has passed over your head since it last passed under you, and if it is not the same flight as the last counted jump (one rope per jump). You succeed when, after 10 counted jumps, your first contact with the floor is your feet only. You fail at once if a rope touches any part of you (a miss), if a rope passes under a foot that is on the ground or through you, if your pelvis leaves the centre zone after it has entered it, on a fall (your pelvis lower than 0.35 m, or any part of you other than your feet on the floor), on a landing after the last jump that is not on the feet, if you touch a turning machine, or after 25 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Category | track-and-jumps |
| Rule book | IJRU Rule Book 5.0.0 (International Jump Rope Union, 2026): Competition Manual, event Double Dutch Single Freestyle (DDSF: three athletes, two turners and one jumper, one set of two ropes; a 12 x 12 m field); Judging Manual, Counting: 'Double Dutch ropes must be turned counter clockwise with the right hand and clockwise with the left hand'; Violations: a space violation is any part of an athlete touching the ground outside the field; ropes may be of any length; deviations: the turners are machines, not athletes: each is a post with two motor-driven cranks of 0.3 m (its right and left hands, 0.4 m apart, their axles 0.95 m high), each crank a position servo on a 90 W geared DC motor (14.0 N m at one turn per second, its maximum-power point: its torque-speed line from twice that at stall to no torque at two turns per second) following a steady 1.1 turns per second, right hands counter-clockwise and left hands clockwise as the turner sees them, the ropes half a turn apart; the turners' axles are 3.9 m apart; they never adapt to the jumper and do not stop when a rope is caught (the motor stalls at its limit) · the routine: a freestyle is judged on its skills; here the task is the basic one every routine starts with: enter the turning ropes from outside and jump 10 rope passes in a row, one rope per jump, with no miss (the count is the benchmark's mark, a round number); any jump style is allowed · the start: the ropes are already turning at t = 0 (a freestyle routine starts with the ropes turning and an entry); the robot stands outside them, 1.5 m from the middle, facing in · a miss is any touch of a rope on the robot; a counted jump is a pass of a rope under both feet while nothing of the robot touches the ground, with the pelvis in the middle (the centre zone, 0.35 by 0.5 m each way), each rope having gone over the head since its last pass; once in the zone the robot must stay in it (instead of the field's space rule, which the robot cannot break here); the end: the first contact after the last counted jump must be the feet only · the ropes: 4.27 m (14 ft) of 0.008 m braided rope at 0.04 kg/m (a typical braided double-dutch cord), tied at both ends to the crank pins by swivels, each a chain of 24 capsules on universal joints (free to bend; it turns about its own axis at the swivels), in still air: the drag of a cylinder in cross flow (C_d 1.2) on each segment; the air's drag on the robot and the machines is left out (a few newtons at most at their speeds; the fluid model would cost the real-time twin its speed); the ropes collide with each other, the floor and the robot |
| Stages | entry → jump 1 → jump 2 → jump 3 → jump 4 → jump 5 → jump 6 → jump 7 → jump 8 → jump 9 → jump 10 → landing |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `9b9a2d4c68300189b88613b15bc42210f93b3b4b38da054416c8b2b9de96282d` |
| Episode | 2500 control steps (25 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
