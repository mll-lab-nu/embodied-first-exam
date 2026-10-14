# roboolympics-trap-ball-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-trap-ball-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `trap_ball` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_trap_ball.py: positive by injection (the real 8 m/s pass onto the foot of the standing robot, the ball's speed set to 0.3 m/s as it comes off); negatives: a planted foot (the ball is 7 m away after 3 s), rolling away, first touch a shin, a handball, too close before the pass. The pass arrives at 6 m/s; a still foot sends it off at 5 m/s; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Trap the pass: take the football that is passed along the ground past you with a foot, and bring it to rest within a metre of you inside three seconds. (RoboOlympics `trap-ball`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
A foot has to be in the way of a 6 m/s ball at the right hundredth of a second, half a metre to the side, and it has to take the pace off: a ball that hits a planted foot bounces a few metres away, far outside the metre, and the walking policy cannot catch a ball that is faster than it.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (the real 8 m/s pass onto the foot of the standing robot, the ball's speed set to 0.3 m/s as it comes off); negatives: a planted foot (the ball is 7 m away after 3 s), rolling away, first touch a shin, a handball, too close before the pass. The pass arrives at 6 m/s; a still foot sends it off at 5 m/s.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: A size-5 football (0.22 m across, 0.43 kg) waits on the ground 15.0 m ahead of you and 0.5 m to your right; 3.0 s after the start it is passed along the ground, rolling at 8.0 m/s, parallel to the way you face, so that it goes by 0.5 m to the right of where you stand. Your first touch must be with a foot or an ankle (the parts below the shin). After it you may play the ball as often as you like with any part of you except the hands and the arms. You succeed when, within 3.0 s of the first touch, the ball is under control: slower than 0.2 m/s for 0.5 s without a break, its centre all that time within 1.0 m of your pelvis (measured along the ground), you on your feet. You fail if the first part of you that the ball touches is not a foot or an ankle, if a hand or an arm touches the ball at any time (handball), if 3.0 s after the first touch the ball is not under control, if your pelvis comes within 9.15 m of the waiting ball before it is passed, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 10 s. The waiting ball cannot be touched. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | football-and-volleyball |
| Rule book | IFAB Laws of the Game 2025/26: Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 12 (handball: the hand or the arm), Law 13 (9.15 m from the ball until it is in play) and the glossary (a kick is a contact with the foot or the ankle). Receiving a pass is a skill, not a rule-book event: the pass and the control standard (first touch with a foot, the ball at rest within 1 m inside 3 s) are the benchmark's; deviations: The pass is a scripted launch: a ball that rolls without slipping at 8.0 m/s from 15.0 m, the same in every attempt, instead of a team-mate; the pitch is level and uniform (the official ball's rolling resistance, no bobble), no wind. · Law 13's distance is applied to the robot itself: until the pass is played it stays 9.15 m from the ball, so that the pass is played, not met at the passer. |
| Stages | first touch → control |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `c9f6feba816000025bd2e59d58cdaf2115615d644a337c4e7647e084a8ddc9a1` |
| Episode | 1000 control steps (10 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
