# embodied-olympics-fun-wall-ball-realgrasp-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-wall-ball-realgrasp-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `wall_ball_realgrasp` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_wall_ball_realgrasp.py: positive by injection around a real release and a real catch: the right Dex1-1 opens and the tennis ball falls free behind the line (its velocity set to 20 m/s; a straight-arm swing of the H1-2 gives about half), real flight, target bounce and rebound; the last 0.8 m of the rebound injected at 3 m/s into the waiting jaws, which close and clamp it by friction (the real 12 m/s rebound closes on it and loses it again); the start grasp holds the whole episode, a light grasp loses the ball in an arm swing; negatives: nop, over the line, off the target, a bounce before the wall, a rebound onto the body, nobody catches, taken back before the wall, let go after the catch, cradled on half-open jaws, a fall; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Throw the tennis ball held in your right gripper at the target circle on the wall and catch the rebound in a gripper before it touches the ground, and keep hold of it. (Embodied Olympics `wall-ball-realgrasp`: one Unitree H1-2 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
To come back five metres through the air the ball has to hit the wall at about 16 m/s or more, inside a circle half a metre across, and it then returns in under half a second at about 10 m/s. The ball, 67 mm across, has to arrive between two jaws that open at most 90 mm and are 80 mm long, and the jaws have to close on it in the few milliseconds it spends between them.

## Reference solution
None. No reference controller exists for this family yet: positive by injection around a real release and a real catch: the right Dex1-1 opens and the tennis ball falls free behind the line (its velocity set to 20 m/s; a straight-arm swing of the H1-2 gives about half), real flight, target bounce and rebound; the last 0.8 m of the rebound injected at 3 m/s into the waiting jaws, which close and clamp it by friction (the real 12 m/s rebound closes on it and loses it again); the start grasp holds the whole episode, a light grasp loses the ball in an arm swing; negatives: nop, over the line, off the target, a bounce before the wall, a rebound onto the body, nobody catches, taken back before the wall, let go after the catch, cradled on half-open jaws, a fall.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The tennis ball (0.067 m across, 0.0577 kg, it keeps 0.745 of its speed in a bounce, it flies in air with drag) starts held between the jaws of your right gripper. Both your hands are two-jaw grippers that hold things only by the friction of their jaws; nothing else holds the ball, and it can slip or drop. A gripper holds the ball while both of its jaws touch it and its centre is between the two jaws' pads (not resting on top of them). A wall stands 5.0 m beyond the line you stay behind; the target is a circle 0.5 m across painted on it, its centre 1.5 m above the ground and 0.0 m to the left of the point straight ahead of you. The throw: the ball is released when it has touched no part of you for 0.05 s (it is released at its last touch; once). The first thing it touches after that must be the wall, at a point inside the target circle. Then catch the rebound: a gripper holding the ball (both jaws on it) before it has touched the ground; either gripper may catch, and before the catch the rebound may touch only your hands (the grippers) and forearms. You succeed when the ball has been held for 1.0 s from the catch, never losing a jaw's touch for more than 0.05 s. You fail if any part of you touches the ground on or beyond the line at any time; if the ball touches the ground at any time before the end; if it hits the wall outside the circle; if any part of you touches it after the release and before the wall (your right arm may still brush it during the first 0.15 s, but not hold it); if the rebound touches any part of you other than a hand or a forearm before the catch; if the ball goes unheld for more than 0.05 s after the catch; if you fall (your pelvis lower than 0.5 m above the ground, or any part of you other than your feet on the ground); or after 15 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (an RTX 4090 workstation, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | No rule book: a wall-ball drill (throw and catch against a wall, as used in baseball, cricket and handball training) with this benchmark's numbers. The ball is the ITF's (Rules of Tennis 2024, Rule 3 and Appendix I: size, mass, rebound); deviations: The hands: the H1-2's hands are Unitree's Dex1-1 two-jaw grippers (sold for the G1, the H2 and the R1, not for the H1-2; mounted on the wrist where the H1-2's palm ends): 90 mm stroke, 80 mm jaws with rubber pads, at most 120 N of grip, each jaw closing at most 187.5 mm/s; they hold the ball by friction only, and it can slip, turn and drop. One closure command per hand (the real one also takes a speed and a force setting), no 5 N minimum force; two pads at friction 1.0 and 120 N hold about 240 N of shear, some five times the device's rated 5 kg friction-grasp load. · The throw and the catch: the ball is released when it has touched no part of you for 0.05 s (at its last touch); it is held while both jaws of one gripper touch it with its centre between the jaws' pads, and a catch is the ball held after the rebound. A held ball may lose a jaw's touch for at most 0.05 s. · The wall is rigid and smooth; the ball's rebound from it is the ITF ball's rebound from a hard floor (0.745 of the speed across the wall). · Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air. The world has elliptic friction cones and an impedance ratio of 100 (the grippers' setting, which makes a clamped ball stay put); they apply to every contact. |
| Stages | release → target → catch → hold |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `25a078534293b8bf40524a364bcb8d1673ea6e0a00da134a10c896a2129404a1` |
| Episode | 1500 control steps (15 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
