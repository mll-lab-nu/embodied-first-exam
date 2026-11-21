# embodied-olympics-fun-alpine-slalom-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-alpine-slalom-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `alpine_slalom` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: A slalom at ICR's gentlest gradient (33 %, ICR 802.1.1) with the U16-U14 minimum vertical drop (100 m: 320 m of course, 32 open gates), a level start platform and a self-start. Positive by injection: pushed off the platform, the robot holds a slight crouch and slides straight between waypoints just outside each turning pole, re-aimed by hand at each gate; the sliding, the gate crossings and the finish are physics; deterministic. The reference skier (a carving controller after its own drop-in) passes 2 of 32 gates and falls. Negatives: nothing done (did not start), a straddle (missed gate), a stop on a flat course, a fall, a finish outside the posts.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Ski the slalom: one run down the course on your skis, both ski tips and both feet through each of the 32 gates in order, then over the finish line. (Embodied Olympics `alpine-slalom`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Skis glide and carve: to turn, the robot must roll its skis onto their edges and lean its body into the turn so that the snow's force passes through its centre of mass, with no walking or running policy to help; each change of turn shifts its whole body across the skis. Speed builds on the slope, and a lean that does not match the turn throws it on the snow. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-alpine-slalom-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: FIS alpine slalom, one run (a course of the U16-U14 minimum vertical drop). The course is a groomed slope falling at 18.3 degrees along +x (the fall line), 40.0 m wide, centred on y = 0. Each of your feet is bound to a slalom ski. You stand on your skis on the level start platform at the top of the course, your boots 0.3 m behind its edge (the start line); the start signal is given at t = 0 and you must leave the platform by your own action (nothing holds or pushes you) within 20.0 s; your run's time starts when both feet cross the start line. There are 32 open gates: gate 1's line is 12.0 m down the slope (measured along it) from x = 0, the slope's reference line, 1 m below where the brink's curve meets the slope; each next one 9.6 m further. A gate is two flexible poles across the slope, red and blue in turn: its turning pole stands 0.8 m from the centre line, on the left (y > 0) for gate 1 and then alternately right and left, its outside pole 4.0 m further out on the same side. Its gate line is the line on the snow from the turning pole to the outside pole. A gate is passed when both ski tips (the front ends of the skis) and both feet have crossed its gate line going down the slope; a point that comes back up across a gate line must cross it again. Gates are passed in order: if any of those four points goes down past the next gate's line, or the finish line, while a gate is not passed, you missed it and the run fails. Hitting or folding a pole is allowed. The finish line is 320.0 m down the slope from x = 0, 12.0 m wide and centred on y = 0: you succeed when, after every gate, both feet cross it between its posts, within 90 s. The run fails if you fall (a part of you other than your feet and your hands touches the snow, or your pelvis is less than 0.35 m above the snow, measured along the slope's normal), if you stop after the start (your pelvis slower than 0.1 m/s for 1.5 s; ICR 614.2.3), if you do not start within 20.0 s, if a foot crosses the finish line outside its posts, or at 90 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 10 GiB |
| `sim` | 4 | 5 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Category | track-and-jumps |
| Rule book | FIS International Competition Rules (ICR), Book IV, Alpine, edition 2025: Art. 614.2 (gates, no continuing after a missed gate or a stop), 661.4.1 and 661.4.1.2 (a gate is passed when both ski tips and both feet cross the gate line, the shortest line between the turning pole and the outside pole), 680 (flex poles), 801 (slalom technical data: gates of two poles, alternately red and blue, 4.0 m wide (4-6 m), turning poles of consecutive gates 6-13 m apart, direction changes 30-35 % of the vertical drop +/- 3), 802 (the slope: about 33-45 %, may be gentler); deviations: ICR 801.1 (vertical drop: men 140-220 m, U16-U14 100-160 m, at least 50 m in a three-run slalom): the course is 320.0 m long on a slope of 18.3 degrees, a vertical drop of about 100 m, the U16-U14 minimum (the category of racers the robot's size), with 32 gates: direction changes about 32 % of the vertical drop (801.2.4: 30-35 %, plus or minus 3). · ICR 802.1.1 (a slope of about 33-45 %): 18.3 degrees, 33 %, the rule's gentlest, uniform over the whole course (a real slope varies). · ICR 803.2-803.4 (a slalom sets open and vertical gates, hairpins, vertical and delayed combinations): only open gates, at a regular 9.6 m (801.2.3: 6-13 m), their turning poles alternately 0.8 m left and right of the course's centre line (the course setter's choice; ICR sets no offset). · ICR 805 (the start: the racer pushes out of the start gate with the poles, the start wand starts the clock): there is no start gate and nothing holds or releases the robot (the start of the Embodied Olympics freeski sport, MIT): it stands on its skis on a level start platform (6.0 m), its boots 0.3 m behind the platform's edge (the start line), the edge rounded (radius 6.0 m) onto the slope; the start signal is given at t = 0 and the robot must leave by its own action within 20.0 s (a DNS otherwise); the run's time starts when both boots cross the start line. · ICR 614.2.4 and 628 (a racer who falls may get up and go on): a fall ends the run here (the families' fall rule): a part of the robot other than its feet and its hands on the snow, or its pelvis less than 0.35 m above the snow. · Equipment: no ski poles (the G1's hands are its rubber fists, which do not close: nothing to hold one with), no ski boots (the feet are bound directly); the binding is rigid and never releases; each ski is three bodies, its forebody and afterbody on hinges with the ski's bending stiffness (EI 60 / 80 N m^2: estimates, as the Embodied Olympics freeski sport's skis); the skis are solid against the robot's body and each other. · Snow and air: the ski-snow contact is the freeski model of the CHIGUI0/roboolympics project (MIT, ported): kinetic friction along the ski after Wolfsperger et al. 2021, the edge's hold across it after Mossner et al. 2013 with race-piste snow, the sidecut's arc after Howe 2001, hard well-damped snow (the model's final version, PR #259); the snow keeps no ruts. Still air at a mountain venue (1.052 kg/m^3), drag and lift on every link (a normal-force model). · Gates: a flex pole is a 28 mm pole on a sprung two-axis hinge at the snow (return stiffness and mass are estimates; ICR 680 requires flex turning poles but publishes no stiffness); it can be hit and folds. |
| Stages | start → gate 1 → gate 2 → gate 3 → gate 4 → gate 5 → gate 6 → gate 7 → gate 8 → gate 9 → gate 10 → gate 11 → gate 12 → gate 13 → gate 14 → gate 15 → gate 16 → gate 17 → gate 18 → gate 19 → gate 20 → gate 21 → gate 22 → gate 23 → gate 24 → gate 25 → gate 26 → gate 27 → gate 28 → gate 29 → gate 30 → gate 31 → gate 32 → finish |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 9000 control steps (90 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
