# embodied-olympics-fun-round-off-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-round-off-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `round_off` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (a straight fist handstand placed with the chest facing +x, hand support with real contacts for 0.05 s, then 2.6 m/s up and 4.1 rad/s about the left-right axis: it flies, turns upright and lands on both feet facing -x, 0.64 s from the feet leaving the floor to the landing; the rotation removed at touchdown, the walk at zero command stands it). The round-off is one element through the handstand, not a held handstand (FIG CoP): the hand support, the landing and the hands after it are judged every 1 ms; a foot counts as down until it has been off for more than 0.03 s, the second foot within 0.10 s of the first; the first foot must be down at most 0.70 s after the feet left the floor for the hand support. Negatives: nop, landing facing +x (a tinsica), sideways, one foot then the other, hands down at the landing, a jumped half-turn without hands, a crouch hop on the hands (not inverted), a landing that falls, outside the area, 0.8 s on the hands (a held handstand); a model run's kick-up handstand held about 2 s, then a step down, one foot 0.15 s before the other, fails: 'not a round-off: the hand support lasted too long' at 4.34 s. Every rule above is judged in the family's own 1 ms substep hook.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Do a round-off: go from your feet onto your hands, turn half round through the handstand and come down onto both feet together facing back the way you came, then stand. (Embodied Olympics `round-off`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The round-off passes your whole weight over two small fists while the body turns half round in the air above them, and ends in a two-foot landing that must stop the rotation: there is no built-in action for any of it and the arms' motors give 25 N m.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a straight fist handstand placed with the chest facing +x, hand support with real contacts for 0.05 s, then 2.6 m/s up and 4.1 rad/s about the left-right axis: it flies, turns upright and lands on both feet facing -x, 0.64 s from the feet leaving the floor to the landing; the rotation removed at touchdown, the walk at zero command stands it). The round-off is one element through the handstand, not a held handstand (FIG CoP): the hand support, the landing and the hands after it are judged every 1 ms; a foot counts as down until it has been off for more than 0.03 s, the second foot within 0.10 s of the first; the first foot must be down at most 0.70 s after the feet left the floor for the hand support. Negatives: nop, landing facing +x (a tinsica), sideways, one foot then the other, hands down at the landing, a jumped half-turn without hands, a crouch hop on the hands (not inverted), a landing that falls, outside the area, 0.8 s on the hands (a held handstand); a model run's kick-up handstand held about 2 s, then a step down, one foot 0.15 s before the other, fails: 'not a round-off: the hand support lasted too long' at 4.34 s. Every rule above is judged in the family's own 1 ms substep hook..

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: You face +x at the start. The hand support counts when only your hands touch the floor and your torso is upside down, its long axis (from the pelvis up to the neck) within 45.0 degrees of pointing straight down. After it, the landing: your feet come down with no hand on the floor, the second foot within 0.1 s of the first (both feet together; a foot off the floor again for more than 0.03 s before the other is down starts the landing over), the first foot down at most 0.7 s after your feet left the floor for the hand support (one continuous motion, not a held handstand), and when both feet are down your pelvis and your torso face back, -x, each within 45.0 degrees (landing facing +x or sideways is a cartwheel or a Tinsica, not a round-off). Then you stand for 1.0 s without a break: only your feet on the floor, your torso within 20.0 degrees of vertical, your pelvis slower than 0.35 m/s. You fail if any part of you other than your hands and feet touches the floor or your pelvis is lower than 0.25 m (a fall); if after the hand support one foot lands and the other does not follow within 0.1 s, or no foot is down 0.7 s after your feet left the floor, or a hand is on the floor when both feet are down, or you land not facing back; if a hand touches the floor after the landing; if any part of you touches the floor outside the 12.0 m x 12.0 m floor area; or after 30 s. Before the hand support anything is free (steps, a hop, a hurdle). No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | FIG Men's Artistic Gymnastics Code of Points 2025-2028: floor exercise, Art. 10.1 (the floor area, 12 m x 12 m), Art. 10.2.1.2a (inside the floor area, the lines included), Art. 10.2.2.6l (a round-off with a 1/4 turn to land facing forward, the Tinsica, is not permitted: the round-off lands facing back), Art. 9.2.12-13 (an element through the handstand deviating more than 45 degrees from it is not recognised), Art. 9.2.17 (landings on the feet, the feet at most 10 cm apart to bring the heels together); the round-off itself as gymnastics defines it: a half turn with hand support, the legs joined over the top, both feet landing together facing the direction you came from; deviations: FIG Apparatus Norms, floor: the floor is rigid and level (friction 1.0), not the norm's sprung floor, because the simulator's ground is rigid and no sourced stiffness of the sprung floor is used here · the hands: the G1 has rubber fists without fingers; any part of the hand may touch the floor · Art. 9.2.17 (feet together at the landing): the robot's legs are 0.24 m apart in its stance and its hips are not built to close them; a two-foot landing here is both feet touching down within 0.1 s of each other (judged after every 1 ms physics step; a foot counts as down until it has been off the floor for more than 0.03 s), not the feet within 10 cm · the round-off is one continuous element, a half turn through the handstand without a stop (Art. 9.2.12-13 recognise it through the handstand; a held handstand is another element). The Code sets no time, so here the hand support, from the moment the feet leave the floor before it to the first foot's touchdown of the landing, may last at most 0.7 s (the number is this benchmark's: a gymnast's round-off spends a few tenths of a second on the hands; the G1 falling from a straight handstand, its feet over its hands, needs about 0.6 s to reach the floor with its feet); a kick-up to a handstand and a step down is not a round-off · a round-off is judged pass or fail, as one element without a run-up requirement or judges: hand support with the torso within 45.0 degrees of upside down, a two-foot landing facing back within 45.0 degrees, and a stand; height, speed and form are not scored |
| Stages | hand support → landing → stand |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `7cf9b35b629129830829122e21825e7d921311bae88f15423b85100b80c78d22` |
| Episode | 3000 control steps (30 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
