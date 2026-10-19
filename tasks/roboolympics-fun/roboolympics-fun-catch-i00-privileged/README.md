# roboolympics-fun-catch-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | privileged |
| Twin | `roboolympics-fun-catch-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `catch` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_catch.py: positive by injection (the real launch and flight; below 3 m the ball is put 0.12 m above the upturned palm at 3 m/s and really gripped); negatives: onto the trunk, touched while rising, dropped after the catch, a fall. The ball comes down 1.25 m from the robot after 3 s at 16.6 m/s: the walk and a palm placed within centimetres are the task; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Catch the fly ball: grip the baseball with a hand before it touches the ground or your body, and keep hold of it. (RoboOlympics `catch`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The ball is in the air for three seconds and comes down at about 17 m/s more than a metre away: the body has to walk there at 0.6 m/s and put a palm on the ball's line to within a few centimetres, facing it, with the grip closing in the few milliseconds in which the ball is against the palm.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (the real launch and flight; below 3 m the ball is put 0.12 m above the upturned palm at 3 m/s and really gripped); negatives: onto the trunk, touched while rising, dropped after the catch, a fall. The ball comes down 1.25 m from the robot after 3 s at 16.6 m/s: the walk and a palm placed within centimetres are the task.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: A baseball (0.073 m across, 0.145 kg, it flies in air with drag) rests on a launcher 40.0 m in front of you, 1.0 m above the ground, and is launched at t = 1.0 s at 21.35 m/s, 45.0 degrees above the horizon, 1.18 degrees to the left of the line from the launcher to you, so that untouched it would come down within 3.0 m of where you stand at the start. A catch is a hand's grip closing on the ball in flight after it has passed the top of its arc: the grip holds a ball whose surface is within 3.5 cm of the palm and that moves no faster than 6 m/s relative to it. Before the grip the ball may touch only your hands and forearms. You succeed when a hand has gripped the ball and kept it for 1.0 s without a break. You fail if the ball touches the ground, or any part of you other than a hand or a forearm, before it is gripped; if you let go of it after the catch; if you fall (your pelvis lower than 0.5 m above the ground, or any part of you other than your feet on the ground) before the end; or after 9 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | Official Baseball Rules (MLB, 2024 edition): 3.01 (the ball), Definitions of Terms: "catch" (secure possession in the hand before the ball touches the ground, held long enough to show control), "in flight"; deviations: Definitions (catch): no glove; the hand catches by a grip that closes on a ball whose surface is within 3.5 cm of the palm and that moves no faster than 6 m/s relative to it (the platform's grip). "Held long enough" is 1.0 s without letting go and without falling. A ball that touches the body (any part other than the hands and forearms) before it is gripped is not a catch here (the rule would allow it). · The fly ball is not batted: a launcher 40.0 m away sends it at 21.35 m/s, 45.0 degrees above the horizon, 1.0 s after the start, without spin; where it comes down (within 3.0 m of where you stand) is this instance's draw. · Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air. |
| Stages | catch → hold |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `0180a9c95dcc1568d8a495934e62add95fd9186eb549d851f7a43d93c472cf5f` |
| Episode | 900 control steps (9 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/roboolympics-fun-files/, built from embodied_first_exam/roboolympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
