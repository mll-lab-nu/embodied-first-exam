# embodied-olympics-fun-giant-slalom-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-giant-slalom-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `giant_slalom` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: A giant slalom with the U16-U14 minimum vertical drop (200 m: 640 m at 33 %, 26 open gates with panels), a level start platform and a self-start. Positive by injection: pushed off the platform, straight runs re-aimed by hand at each gate; sliding, crossings and finish are physics; deterministic. Negatives: did not start, a stop on a flat course, a fall, a finish outside the posts.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Ski the giant slalom: one run down the course on your skis, both ski tips and both feet through each of the 26 gates in order, then over the finish line. (Embodied Olympics `giant-slalom`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Giant-slalom skis carve long arcs: to turn, the robot must roll them onto their edges and lean its body into the turn so that the snow's force passes through its centre of mass, with no walking or running policy to help. The gates are far apart, so speed builds between them, and a lean that does not match the turn throws it on the snow.

## Reference solution
None. No reference controller exists for this family yet: A giant slalom with the U16-U14 minimum vertical drop (200 m: 640 m at 33 %, 26 open gates with panels), a level start platform and a self-start. Positive by injection: pushed off the platform, straight runs re-aimed by hand at each gate; sliding, crossings and finish are physics; deterministic. Negatives: did not start, a stop on a flat course, a fall, a finish outside the posts..

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: FIS alpine giant slalom, one run (a course of the U16-U14 minimum vertical drop). The course is a groomed slope falling at 18.3 degrees along +x (the fall line), 40.0 m wide, centred on y = 0. Each of your feet is bound to a giant-slalom ski. You stand on your skis on the level start platform at the top of the course, your boots 0.3 m behind its edge (the start line); the start signal is given at t = 0 and you must leave the platform by your own action (nothing holds or pushes you) within 20.0 s; your run's time starts when both feet cross the start line. There are 26 open gates: gate 1's line is 15.0 m down the slope (measured along it) from x = 0, the slope's reference line, 1 m below where the brink's curve meets the slope; each next one 24.0 m further. A gate is two pairs of flexible poles across the slope, each pair joined by a panel, red and blue in turn: the inner pole of its turning pair stands 2.0 m from the centre line, on the left (y > 0) for gate 1 and then alternately right and left; the inner pole of its outside pair stands 5.0 m further out on the same side. Its gate line is the line on the snow between the two inner poles. A gate is passed when both ski tips (the front ends of the skis) and both feet have crossed its gate line going down the slope; a point that comes back up across a gate line must cross it again. Gates are passed in order: if any of those four points goes down past the next gate's line, or the finish line, while a gate is not passed, you missed it and the run fails. Hitting a pole or a panel is allowed. The finish line is 640.0 m down the slope from x = 0, 14.0 m wide and centred on y = 0: you succeed when, after every gate, both feet cross it between its posts, within 150 s. The run fails if you fall (a part of you other than your feet and your hands touches the snow, or your pelvis is less than 0.35 m above the snow, measured along the slope's normal), if you stop after the start (your pelvis slower than 0.1 m/s for 1.5 s; ICR 614.2.3), if you do not start within 20.0 s, if a foot crosses the finish line outside its posts, or at 150 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | FIS International Competition Rules (ICR), Book IV, Alpine, edition 2025: Art. 614.2 (gates, no continuing after a missed gate or a stop), 661.4.1 and 661.4.1.1 (a gate is passed when both ski tips and both feet cross the gate line, the shortest line on the snow between the inner poles of its two pole pairs), 680 (flex turning poles), 690 and 901.2.2 (panels of about 75 x 50 cm, their lower edge at least 1 m above the snow), 901 (giant slalom technical data: a gate of four poles and two panels, alternately red and blue, 4-8 m wide, at least 10 m between the nearest poles of consecutive gates, direction changes 11-15 % of the vertical drop), 902-903 (the course); deviations: ICR 901.1 (vertical drop 250-450 m, U16-U14 200-350 m): the course is 640.0 m long on a slope of 18.3 degrees, a vertical drop of about 200 m, the U16-U14 minimum (the category of racers the robot's size), with 26 gates: direction changes about 13 % of the vertical drop (901.2.4: 11-15 %). · ICR 902 (the terrain, a course about 40 m wide; the ICR gives the giant slalom no gradient): a uniform groomed slope of 18.3 degrees, 33 %, the slalom's gentlest (ICR 802.1.1), 40.0 m wide. · ICR 903 (the course setter's free choice of long, medium and short turns): open gates at a regular 24.0 m, their turning poles alternately 2.0 m left and right of the centre line. · ICR 805 / 905 (the start: the racer pushes out of the start gate with the poles, the start wand starts the clock): there is no start gate and nothing holds or releases the robot (the start of the Embodied Olympics freeski sport, MIT): it stands on its skis on a level start platform (6.0 m), its boots 0.3 m behind the platform's edge (the start line), the edge rounded (radius 6.0 m) onto the slope; the start signal is given at t = 0 and the robot must leave by its own action within 20.0 s (a DNS otherwise); the run's time starts when both boots cross the start line. · ICR 614.2.4 and 628 (a racer who falls may get up and go on): a fall ends the run here (the families' fall rule): a part of the robot other than its feet and its hands on the snow, or its pelvis less than 0.35 m above the snow. · Snow and air: the ski-snow contact is the freeski model of the CHIGUI0/roboolympics project (MIT, ported): kinetic friction along the plank after Wolfsperger et al. 2021, the edge's hold across it after Mossner et al. 2013 with race-piste snow, the sidecut's arc after Howe 2001, hard well-damped snow (the model's final version, PR #259); the snow keeps no ruts. Still air at a mountain venue (1.052 kg/m^3), drag and lift on every link (a normal-force model). · Equipment: no ski poles (the G1's hands are its rubber fists, which do not close: nothing to hold one with), no ski boots (the feet are bound directly); the binding is rigid and never releases; each ski is three bodies, its forebody and afterbody on hinges with the ski's bending stiffness (EI 60 / 80 N m^2: estimates, as the Embodied Olympics freeski sport's skis); the skis are solid against the robot's body and each other. · Gates: each pole pair and its panel is one body on a sprung two-axis hinge at the snow (a real pair has a flex hinge per pole and a panel that tears off in a collision; ICR 690.1); stiffness and mass are estimates. |
| Stages | start → gate 1 → gate 2 → gate 3 → gate 4 → gate 5 → gate 6 → gate 7 → gate 8 → gate 9 → gate 10 → gate 11 → gate 12 → gate 13 → gate 14 → gate 15 → gate 16 → gate 17 → gate 18 → gate 19 → gate 20 → gate 21 → gate 22 → gate 23 → gate 24 → gate 25 → gate 26 → finish |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `889c256f86e34f81a08b23588716a0aaf440e3b8f01c8f93a565a1699fb7dd10` |
| Episode | 15000 control steps (150 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
