# roboolympics-wall-ball-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-wall-ball-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `wall_ball` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_wall_ball.py: positive by injection (a real release, the ball's velocity set to 20 m/s: the target hit, the rebound's last 0.8 m replaced as in `catch`); negatives: over the line, outside the target, a bounce before the wall, the rebound onto the body or the floor, taken back before the wall, dropped. An arm swing gives 6.9 m/s; the throw needs 16 to 20 m/s; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Throw the tennis ball in your right hand at the target circle on the wall and catch the rebound with a hand before it touches the ground, and keep hold of it. (RoboOlympics `wall-ball`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
To come back five metres through the air the ball has to hit the wall at about 16 m/s or more, inside a circle half a metre across, and it then returns in under half a second at about 10 m/s. The palm must be on its line within a few centimetres with the grip closing as it arrives.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a real release, the ball's velocity set to 20 m/s: the target hit, the rebound's last 0.8 m replaced as in `catch`); negatives: over the line, outside the target, a bounce before the wall, the rebound onto the body or the floor, taken back before the wall, dropped. An arm swing gives 6.9 m/s; the throw needs 16 to 20 m/s.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The tennis ball (0.067 m across, 0.0577 kg, it keeps 0.745 of its speed in a bounce, it flies in air with drag) starts gripped against your right palm. A wall stands 5.0 m beyond the line you stay behind; the target is a circle 0.5 m across painted on it, its centre 1.5 m above the ground and 0.0 m to the left of the point straight ahead of you. Let go of the ball (the throw, once); the first thing it touches must be the wall, at a point inside the target circle. Then catch the rebound: a hand's grip closing on the ball in the air (the grip holds a ball whose surface is within 3.5 cm of the palm and that moves no faster than 6 m/s relative to it); either hand may catch, and before the grip the rebound may touch only your hands and forearms. You succeed when the ball has been gripped after the rebound and kept for 1.0 s without a break. You fail if any part of you touches the ground on or beyond the line at any time; if the ball touches the ground at any time before it is caught; if it hits the wall outside the circle; if any part of you touches it after the release and before the wall (your throwing arm may still brush it during the first 0.15 s; it cannot be gripped then); if the rebound touches any part of you other than a hand or a forearm before it is gripped; if you let go of it after the catch; if you fall (your pelvis lower than 0.5 m above the ground, or any part of you other than your feet on the ground); or after 15 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | No rule book: a wall-ball drill (throw and catch against a wall, as used in baseball, cricket and handball training) with this benchmark's numbers. The ball is the ITF's (Rules of Tennis 2024, Rule 3 and Appendix I: size, mass, rebound); deviations: The hand throws and catches by a grip switched on and off: it holds a ball whose surface is within 3.5 cm of the palm and that moves no faster than 6 m/s relative to it; the ball is released when the grip is switched off. · The wall is rigid and smooth; the ball's rebound from it is the ITF ball's rebound from a hard floor (0.745 of the speed across the wall). · Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air. |
| Stages | release → target → catch → hold |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `66de17566b13f569397b0f109d8f85817d2e2b106800a223541b56c509123ab4` |
| Episode | 1500 control steps (15 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
