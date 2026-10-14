# robofunolympics-shuttle-run-i00-privileged

| | |
|---|---|
| Benchmark | RoboFunOlympics |
| Mode | privileged |
| Twin | `robofunolympics-shuttle-run-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `shuttle_run` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/robofunolympics/tests/test_shuttle_run.py: positive by injection (real running on all four legs, the three about-turns set by hand: 23.0 s); negatives: turning short, a foot only on the line, two legs only, arms over the finish without the torso, down, walking. With the built-in gaits a leg takes about 6 s and an about-turn on the walking policy 3.4 s: about 33 s against the 30 s limit; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Run the 4 x 10 m shuttle: to the far line, back to the start line, to the far line again and back through the start line, putting a foot on the ground beyond the line at each turn, as fast as you can. (RoboFunOlympics `shuttle-run`: one Unitree G1 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Forty metres with three reversals in 30 s: the walking gait covers 19 m in that time, and the running gait turns slowly, needs metres to stop, and falls when it is handed over to another gait at speed, so every leg has to be braked and reversed without losing seconds.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (real running on all four legs, the three about-turns set by hand: 23.0 s); negatives: turning short, a foot only on the line, two legs only, arms over the finish without the torso, down, walking. With the built-in gaits a leg takes about 6 s and an about-turn on the walking policy 3.4 s: about 33 s against the 30 s limit.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: Two lines cross the floor: the start line x = 0 and the far line x = 10.0 m (the planes meant are the edges of the painted lines that face each other). The clock starts at t = 0. You run four legs: to the far line, back to the start line, to the far line, back to the start line. At each of the three turns you must put a foot on the ground wholly beyond the line: every part of that foot at x > 10.0 m at the far line (turns 1 and 3), at x < 0 at the start line (turn 2); a foot on the line does not count. The turns count in this order only. After the third turn you finish at the moment the leading point of your torso (not the head, arms, legs or feet) reaches the start line. Which way you face and how you turn is up to you. You succeed when you finish within 30 s of robot time. A fall does not end the attempt: you are down while your pelvis is below 0.4 m, you may get up and go on, but 10.0 s down in a row end it. You fail when down for 10.0 s, or after 30 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | track-and-jumps |
| Rule book | The 4 x 10 m shuttle run of school fitness test batteries (the speed-agility test of the ALPHA-Fitness battery): two parallel lines 10 m apart, four legs, the line crossed at every turn, the time taken when the runner crosses the start line at the end of the fourth leg; deviations: the sponges the ALPHA version has the runner carry between the lines are left out (the robot has no fingers), and a turn needs one foot on the ground beyond the line where ALPHA asks for both · the start: no starter and no reaction time; the clock runs from t = 0 with the robot standing behind the start line · the finish is timed as in athletics (World Athletics TR 19): the leading point of the torso link's collision mesh on the plane of the start line, interpolated between 1 ms physics steps · a fallen runner: a robot whose pelvis is below 0.4 m is down; it may get up and go on, but 10.0 s down in a row end the attempt · the qualifying time, 30 s, is this benchmark's own round number: school norms for this test are 10 to 14 s |
| Stages | turn 1 → turn 2 → turn 3 → finish |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `573239e95518eeb5365f8dac4181710fa30f7f6b8c97fef43b0e85b2a1525efd` |
| Episode | 3000 control steps (30 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/robofunolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/robofunolympics.md) |
