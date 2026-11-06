# embodied-olympics-fun-breaking-windmill-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-breaking-windmill-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `breaking_windmill` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (the pelvis pose and velocity written each control step along a windmill path, 1.25 rev/s, the torso's axis 26 degrees head-down, heading and roll together, the upper back 4 mm into the floor; the joints on the robot's own PD, legs in a V, hips following the roll; the contacts are the simulator's). Turning and rolling are counted only while the body lies on the floor (the torso's axis within 30 degrees of horizontal, the pelvis at most 0.45 m up), and the torso or an upper arm (not the head) must touch the floor in each half revolution. Negatives: nop, a backspin (no roll), a log roll (no spin), a reversed roll, hips on the floor, in the air, the same turning upside down on the head and shoulders, 2 + hips down + 2 (not consecutive), outside the field of play. Wobbles in a headstand (the heading of a near-vertical axis turning) count no windmill; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Breaking: go down to the floor and do three consecutive windmills, rolling over your upper back, shoulders and chest while your legs circle round above the floor. (Embodied Olympics `breaking-windmill`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
A windmill is a continuous rolling and spinning motion on the shoulders with nothing built in for any of it, and every revolution loses energy to the floor that has to be put back. You also have to get down to the floor from standing first.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (the pelvis pose and velocity written each control step along a windmill path, 1.25 rev/s, the torso's axis 26 degrees head-down, heading and roll together, the upper back 4 mm into the floor; the joints on the robot's own PD, legs in a V, hips following the roll; the contacts are the simulator's). Turning and rolling are counted only while the body lies on the floor (the torso's axis within 30 degrees of horizontal, the pelvis at most 0.45 m up), and the torso or an upper arm (not the head) must touch the floor in each half revolution. Negatives: nop, a backspin (no roll), a log roll (no spin), a reversed roll, hips on the floor, in the air, the same turning upside down on the head and shoulders, 2 + hips down + 2 (not consecutive), outside the field of play. Wobbles in a headstand (the heading of a near-vertical axis turning) count no windmill.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: A windmill revolution is counted on your torso. Its long axis (from your pelvis up to your neck) must turn once round the vertical (360 degrees of heading) and in the same time your torso must roll once about that axis (back, shoulder, chest, shoulder, back towards the floor: at least 0.85 of a full roll per revolution), both the same way round. The turning and the rolling are counted only while you lie on the floor: your torso's long axis within 30.0 degrees of horizontal and your pelvis at most 0.45 m above the floor (on your head or your hands, upside down, nothing is counted). Your back, chest or shoulders (your torso or upper arms; your head does not count for this) must touch the floor in each half of each revolution. While you are doing windmills only your torso (back, chest, shoulders; your head, which is fixed to it, counts with it), your upper arms, forearms and hands may touch the floor: your hips and your legs (thighs, shins, feet) may not. The count starts when you are down (your back, chest or shoulders touching the floor with no foot on it) and goes back to zero whenever your hips or a leg touch the floor or the rotation reverses. You succeed when 3 revolutions are counted without such a reset. How you get down from standing is free (any part may touch the floor then). You fail if any part of you touches the floor outside the 8.0 m x 8.0 m field of play, or after 30 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | WDSF Breaking Rules and Regulations Manual (BRRM, version 4, January 2023, the rules of the Paris 2024 qualification): 2.2 'The elements of Breaking' (power moves: spinning moves driven by centrifugal force, the windmill family among the most frequent; in a pure power move set the feet seldom touch the ground); 4.6.4 (judging, the values affecting all domains): 'Crash' (slip, crash, wipe-out: non-intentional loss of physical control); 7.1 Field of Play: a 'Fast Break System Laminate' floor, at least 6.5 m x 6.5 m, advised 8.00 m x 8.00 m, a red line on the right side and a blue line on the left side; deviations: BRRM judging (Technique, Vocabulary, Originality, Execution, Musicality, compared head to head in a battle): a single power move is judged pass or fail: 3 consecutive windmill revolutions, because the task is one element without a judging panel or an opponent; the BRRM sets no number of revolutions, 3 is this benchmark's choice (a short set) · BRRM 2.2 (a windmill): the BRRM names the move but does not define it; here a revolution is the torso's long axis turning once round the vertical and the torso rolling once about that axis, both the same way, counted only while the body lies on the floor (the long axis within 30.0 degrees of horizontal, the pelvis at most 0.45 m up: a windmill is done on the upper back, not on the head or the hands), with only the torso (the head included), the arms and the hands on the floor (no hips or legs) and the back, chest or shoulders (the torso or an upper arm, not the head) touching the floor in each half revolution · BRRM 7.1 (the laminate floor): the floor is rigid and level; the contact between the robot's shell and the floor uses the robot model's friction coefficient of 1.0 (no sourced figure for a robot's shell on laminate exists; breakers wear slippery clothes, the robot wears none: this makes sliding on the back harder, not easier) · the head: a breaker's chin is tucked and the head stays off the floor in a windmill; the G1 has no neck joint and its head's back face lies 7 mm inside the torso's, so a head touch is allowed, but only the torso's or an upper arm's touch counts as the back's, chest's or shoulders' · BRRM crash (a fall in a set is a deduction, not an end): a set is any 3 consecutive revolutions; a forbidden contact only ends the current set (the count starts again), and only the time limit ends the attempt |
| Stages | down → 1 windmill → 2 windmills → 3 windmills |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `0290d5cd0b4fbb03999997cbdb1372006a242f429efa3f6927b061b625a78e59` |
| Episode | 3000 control steps (30 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
