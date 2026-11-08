# embodied-olympics-fun-shuttle-run-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-shuttle-run-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `shuttle_run` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (real running on all four legs, the three about-turns set by hand: 23.0 s); negatives: turning short, a foot only on the line, two legs only, arms over the finish without the torso, down, walking. With the built-in gaits a leg takes about 6 s and an about-turn on the walking policy 3.4 s: about 33 s against the 30 s limit. A turn counts only with the foot beyond the line between its cones (every ground contact point at |y| <= 3 m), the finish only where the torso's leading point crosses the start line between its cones, and the pelvis may not leave the court (|y| > 4 m or more than 10 m beyond a line fails). Positive by injection (the standing robot moved by hand beyond each line in turn, then through the start line: real foot contacts and an interpolated torso crossing); negatives: nop, a turn touch past the cones, out of the court, a finish past the cones. A model run's oval loop round the court (turns and finish on the lines' extensions, up to 8.3 m wide) fails: 'left the court' at 4.99 s. Every rule above is judged in the family's own 1 ms substep hook.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Run the 4 x 10 m shuttle: to the far line, back to the start line, to the far line again and back through the start line, putting a foot on the ground beyond the line at each turn, as fast as you can. (Embodied Olympics `shuttle-run`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Forty metres with three reversals in 30 s: the walking gait covers 19 m in that time, and the running gait turns slowly, needs metres to stop, and falls when it is handed over to another gait at speed, so every leg has to be braked and reversed without losing seconds.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (real running on all four legs, the three about-turns set by hand: 23.0 s); negatives: turning short, a foot only on the line, two legs only, arms over the finish without the torso, down, walking. With the built-in gaits a leg takes about 6 s and an about-turn on the walking policy 3.4 s: about 33 s against the 30 s limit. A turn counts only with the foot beyond the line between its cones (every ground contact point at |y| <= 3 m), the finish only where the torso's leading point crosses the start line between its cones, and the pelvis may not leave the court (|y| > 4 m or more than 10 m beyond a line fails). Positive by injection (the standing robot moved by hand beyond each line in turn, then through the start line: real foot contacts and an interpolated torso crossing); negatives: nop, a turn touch past the cones, out of the court, a finish past the cones. A model run's oval loop round the court (turns and finish on the lines' extensions, up to 8.3 m wide) fails: 'left the court' at 4.99 s. Every rule above is judged in the family's own 1 ms substep hook..

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: Two lines cross the floor: the start line x = 0 and the far line x = 10.0 m (the planes meant are the edges of the painted lines that face each other). The clock starts at t = 0. You run four legs: to the far line, back to the start line, to the far line, back to the start line. At each of the three turns you must put a foot on the ground wholly beyond the line: every part of that foot at x > 10.0 m at the far line (turns 1 and 3), at x < 0 at the start line (turn 2); a foot on the line does not count, and the foot must be between the cones at the line's ends (every point where it touches the ground at |y| <= 3.0 m). The turns count in this order only. After the third turn you finish at the moment the leading point of your torso (not the head, arms, legs or feet) reaches the start line between its cones (|y| <= 3.0 m at that point). Which way you face and how you turn is up to you. You succeed when you finish within 30 s of robot time. A fall does not end the attempt: you are down while your pelvis is below 0.4 m, you may get up and go on, but 10.0 s down in a row end it. You fail when down for 10.0 s, when your pelvis leaves the court (more than 4.0 m to either side of the centre line y = 0, or more than 10 m beyond either line), or after 30 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | The 4 x 10 m shuttle run of school fitness test batteries (the speed-agility test of the ALPHA-Fitness battery): two parallel lines 10 m apart, four legs, the line crossed at every turn, the time taken when the runner crosses the start line at the end of the fourth leg; deviations: the sponges the ALPHA version has the runner carry between the lines are left out (the robot has no fingers), and a turn needs one foot on the ground beyond the line where ALPHA asks for both · the start: no starter and no reaction time; the clock runs from t = 0 with the robot standing behind the start line · the finish is timed as in athletics (World Athletics TR 19): the leading point of the torso link's collision mesh on the plane of the start line, interpolated between 1 ms physics steps · a fallen runner: a robot whose pelvis is below 0.4 m is down; it may get up and go on, but 10.0 s down in a row end the attempt · the lane: ALPHA runs the test on a marked course between the two lines; here the turns and the finish count only between the cones at the lines' ends (/y/ <= 3.0 m), and the pelvis may not leave the court (4.0 m to either side of the centre line): a loop round the far line instead of a reversal, or a finish past the cones, is not the shuttle · the qualifying time, 30 s, is this benchmark's own round number: school norms for this test are 10 to 14 s |
| Stages | turn 1 → turn 2 → turn 3 → finish |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `573239e95518eeb5365f8dac4181710fa30f7f6b8c97fef43b0e85b2a1525efd` |
| Episode | 3000 control steps (30 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
