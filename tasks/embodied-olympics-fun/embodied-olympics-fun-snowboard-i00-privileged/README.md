# embodied-olympics-fun-snowboard-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-snowboard-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `snowboard` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: A parallel slalom run with the minimum vertical drop (80 m: 256 m at 33 %, 18 gates), a level start platform and a self-start. Positive by injection: pushed off the platform, straight runs re-aimed by hand 0.8 m outside each turning pole; sliding, crossings and finish are physics; deterministic. Negatives: did not start, a stop on a flat course, a fall, a finish outside the posts.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Ride the parallel slalom on your snowboard: one run down the course, the board and both feet through each of the 18 gates in order, then over the finish line. (Embodied Olympics `snowboard`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
A snowboard turns on its toe edge and its heel edge: the robot must tip the board by leaning forwards or back over it, its feet locked to one plank, with no walking policy; toe-side turns ask it to balance over the narrow board's front edge at speed, heel-side turns to sit back without falling.

## Reference solution
None. No reference controller exists for this family yet: A parallel slalom run with the minimum vertical drop (80 m: 256 m at 33 %, 18 gates), a level start platform and a self-start. Positive by injection: pushed off the platform, straight runs re-aimed by hand 0.8 m outside each turning pole; sliding, crossings and finish are physics; deterministic. Negatives: did not start, a stop on a flat course, a fall, a finish outside the posts..

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: FIS snowboard parallel slalom, one run on one course (of the minimum vertical drop). The course is a groomed slope falling at 18.3 degrees along +x (the fall line), 40.0 m wide, centred on y = 0. Both your feet are bound to one snowboard, the left foot forward (regular), across the board. You stand on your board on the level start platform at the top of the course, sideways to the fall line with the board's nose pointing down it, your front boot 0.3 m behind the platform's edge (the start line); the start signal is given at t = 0 and you must leave the platform by your own action (nothing holds or pushes you) within 20.0 s; your run's time starts when both feet cross the start line. There are 18 gates: gate 1's line is 12.0 m down the slope (measured along it) from x = 0, the slope's reference line, 1 m below where the brink's curve meets the slope; each next one 13.5 m further. A gate is two flexible poles across the slope, red and blue in turn: its turning pole stands 1.0 m from the centre line, on the left (y > 0) for gate 1 and then alternately right and left, its outside pole 4.0 m further out on the same side; its gate line is the line on the snow between them. A gate is passed when the board's nose and tail and both feet have crossed its gate line going down the slope; a point that comes back up across a gate line must cross it again. Gates are passed in order: if any of those four points goes down past the next gate's line, or the finish line, while a gate is not passed, you missed it and the run fails. Hitting or folding a pole is allowed. The finish line is 256.0 m down the slope from x = 0, 12.0 m wide and centred on y = 0: you succeed when, after every gate, both feet cross it between its posts, within 90 s. The run fails if you fall (a part of you other than your feet and your hands touches the snow, or your pelvis is less than 0.35 m above the snow, measured along the slope's normal), if you stop after the start (your pelvis slower than 0.1 m/s for 1.5 s), if you do not start within 20.0 s, if a foot crosses the finish line outside its posts, or at 90 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | FIS International Competition Rules (ICR), Snowboard, edition 2024/25, parallel slalom (PSL): Art. 2507.2 (turning poles of consecutive gates 10-14 m apart; vertical drop 80-120 m, at least 18 gates), the gate passed when the board and both feet pass outside the gate's turning pole in the direction of the turn (as alpine ICR 661.4.2 for parallel events), flex turning poles (alpine ICR 680), no continuing after a missed gate, a fall; deviations: Parallel format: one rider on one course against the clock (no opponent, no heats, no blue and red courses side by side). · Vertical drop and gates (80-120 m, at least 18 gates): the course is 256.0 m long on a slope of 18.3 degrees (33 %, the alpine slalom's gentlest, ICR 802.1.1: the snowboard ICR gives none we could cite), a vertical drop of about 80 m with 18 gates, the minimum of both. · Gates: a turning pole and an outside pole 4.0 m further out (PSL gates carry a panel on their poles; drawn as plain poles here); a flex pole is a 28 mm pole on a sprung two-axis hinge at the snow (stiffness and mass are estimates). The gate is judged like an alpine gate: the board's nose and tail and both feet must cross the gate line from the turning pole to the outside pole. · Snowboard ICR (the start gate: the rider pushes out of it, the gate starts the clock): there is no start gate and nothing holds or releases the robot (the start of the Embodied Olympics freeski sport, MIT): it stands on its board on a level start platform (6.0 m), its front boot 0.3 m behind the platform's edge (the start line), the edge rounded (radius 6.0 m) onto the slope; the start signal is given at t = 0 and the robot must leave by its own action within 20.0 s (a DNS otherwise); the run's time starts when both boots cross the start line. · A rider who falls may get up and go on: a fall ends the run here (the families' fall rule): a part of the robot other than its feet and its hands on the snow, or its pelvis less than 0.35 m above the snow. · Snow and air: the board-snow contact is the freeski ski-snow model of the CHIGUI0/roboolympics project (MIT, ported): kinetic friction along the board after Wolfsperger et al. 2021, the edge's hold across it after Mossner et al. 2013 with race-piste snow, the sidecut's arc after Howe 2001, hard well-damped snow (the model's final version, PR #259); the snow keeps no ruts. Still air at a mountain venue (1.052 kg/m^3), drag and lift on every link (a normal-force model). · Equipment: a children's all-mountain board (not a hard-boot race board); bindings at 0 / 0 degrees with a 0.4 m stance, rigid (no boots: the feet are bound directly; a binding never releases); the board is rigid (no bending: freeski's flexing ski has no snowboard counterpart) and solid against the robot's body. |
| Stages | start → gate 1 → gate 2 → gate 3 → gate 4 → gate 5 → gate 6 → gate 7 → gate 8 → gate 9 → gate 10 → gate 11 → gate 12 → gate 13 → gate 14 → gate 15 → gate 16 → gate 17 → gate 18 → finish |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `ab824f25a7fea965e3bb62dd365d3ea731932b8604e1c134efcc29d55e410d0d` |
| Episode | 9000 control steps (90 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
