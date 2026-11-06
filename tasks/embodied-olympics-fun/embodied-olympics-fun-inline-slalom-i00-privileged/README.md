# embodied-olympics-fun-inline-slalom-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-inline-slalom-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `inline_slalom` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (the floating base written every control step along a weaving path, one skate rolling, the other lifted; cones, skates and wheels are physics); the real run-up only: a scripted swizzle (IK) skates from the start box over the 12 m run-up in 12.3 s on two feet, which the referee voids at the second cone (7.4.2.2). No one-foot controller exists for the G1: one-skate glides steered by capture point last at most 2.2 s at 2 m/s; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Skate the speed slalom: from the start box, 12 m of run-up, then on one foot through the 20 cones, passing them alternately left and right, and over the end line, as fast as you can. (Embodied Olympics `inline-slalom`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Skating is pushing against wheels that only grip sideways: the robot has no skating gait and no balance on one foot, and on one skate it stands on a line of wheels, so it can only stay up by steering the skate under its weight while weaving through cones 0.8 m apart.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (the floating base written every control step along a weaving path, one skate rolling, the other lifted; cones, skates and wheels are physics); the real run-up only: a scripted swizzle (IK) skates from the start box over the 12 m run-up in 12.3 s on two feet, which the referee voids at the second cone (7.4.2.2). No one-foot controller exists for the G1: one-skate glides steered by capture point last at most 2.2 s at 2 m/s.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: You wear inline skates (rigid boots on your feet, four wheels in a line on each, the outer ones 0.064 m and the inner ones 0.062 m in diameter, 0.064 m apart). The course runs along +x on a level sports floor: the start line at x = 0 and a second line 0.4 m behind it (the start box), 20 cones on the line y = 0 every 0.8 m from x = 12.0 m, the end line 0.8 m beyond the last cone. The cones are free plastic cups 0.078 m high, 0.074 m across the base, 0.02 kg, standing on marking stickers. Time starts when any part of your body crosses the start line at the gate beam's height, 0.4 m above the ground; you must do that within 5.0 s of t = 0. The cone line begins at the front edge of the first cone: enter it on one foot (one skate's wheels on the ground, the other skate in the air), or the first cone counts as missed (a penalty); not being on one foot when your skate passes the second cone voids the run. From then on the free skate must not touch the ground until the end line (that voids the run; so does changing feet). Pass the cones alternately on the left and the right with the supporting skate: two consecutive cones on the same side are a missed interval. A cone whose marking centre is uncovered at the finish (its base centre moved more than 0.0335 m (the base's radius less the centre point's), or tilted more than 30.0 degrees) is kicked. Each kicked cone or missed interval adds 0.2 s; more than 4 penalties void the run. The run ends when the front wheel of your supporting skate crosses the end line with a wheel of that skate on the ground (crossing first with the free skate, or in the air, voids it); every cone must have been passed. Your time is the time from the beam to the end line plus the penalties. You succeed with a valid run that ends within 60 s of t = 0. You also fail if any part of you touches the ground (the skates' wheels and frames may) or your pelvis drops below 0.45 m (a fall). No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | World Skate Inline Freestyle Regulation (update of October 2025): 3.10 official cones (7.6-8.0 cm high, base 7.2-7.5 cm, top 2.4-2.7 cm); 4.2 the cone lines and their marking stickers (7.7 cm, a 0.7 cm centre point); 7 Speed Slalom (on one foot, as fast as possible): 7.1.1 20 cones 80 cm apart, 7.1.3 the start box (two start lines 40 cm apart), 7.1.5 the first cone 12 m from the start line and the end line 80 cm beyond the last cone, 7.3.1.1 the free start of the time trials (time starts when any part of the body crosses the gate beam, 40 cm above the ground), 7.3.2 the cone line entered on one foot, 7.3.3 the end line crossed by the supporting foot with a wheel on the ground, 7.4.2 first-cone penalties, 7.4.3 the free foot and changing foot, 7.4.4 end-line penalties, 7.4.5 +0.2 s per kicked cone or missed interval, more than 4 cone penalties void the run; deviations: 7.3.1.1 the start: "Ready" is t = 0 with the robot standing in the start box on both skates; it has 5.0 s to break the gate beam; a false start's warning and restart are not modelled (one run) · 7.1.1-7.1.4 one cone line, without the second line and the divider (one skater, one time-trial run) · 7.4.5.2 a kicked cone (its marking centre revealed) is judged at the finish: the cone's base centre more than 0.0335 m (the base's radius less the centre point's) from its mark, or the cone tilted more than 30.0 degrees · the missed interval and the side of each cone are judged on the supporting skate's centre: the side of the cone line it is on when it passes each cone; two consecutive cones on the same side are one missed interval · the finish gate (20 cm above the ground) is the supporting skate's front wheel reaching the end line · the skates are rigid bodies held to the feet by a rigid boot (no ankle flex in the boot); the wheels are ellipsoids (their rounded profile) on frictionless axles · success is a valid run within 60 s, the family's own round number for this robot: the rule book only ranks times |
| Stages | start → cone line → cone 5 → cone 10 → cone 15 → cone 20 → finish |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `cd3bd6cbd26b4146d1b959efe9a017947922c7d2e1c8524a49c5fccc2281acb9` |
| Episode | 6000 control steps (60 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
