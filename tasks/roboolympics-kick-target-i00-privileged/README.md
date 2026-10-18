# roboolympics-kick-target-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-kick-target-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `kick_target` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_kick_target.py: positive by injection (a stiff posed leg and the whole robot given 1.0 m/s: 26.7 N s in 0.054 s; then put back on its feet); negatives: a slower kick, a touch over the bound, the other leg, below the band, walking in, the bag swinging back onto the robot. Leg swings on servo-held joints gave 2 to 8 N s; there is no balance on one leg; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Kick the heavy bag once with your right foot or shin, on the marked band at trunk height, hard enough to give it 20.0 N s, then stand on both feet. (RoboOlympics `kick-target`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The band is higher than the robot's hip joint: the foot has to be swung above hip height, fast, while the other leg alone carries 67 kg; there is no kicking or one-leg balance policy. The bag pushes back with the same impulse, and the body has to end on both feet, still.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a stiff posed leg and the whole robot given 1.0 m/s: 26.7 N s in 0.054 s; then put back on its feet); negatives: a slower kick, a touch over the bound, the other leg, below the band, walking in, the bag swinging back onto the robot. Leg swings on servo-held joints gave 2 to 8 N s; there is no balance on one leg.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: A heavy bag (30.0 kg, 1.2 m long, 0.35 m across) hangs by a 0.5 m chain from a hook, free to swing in every direction; its top is 1.75 m above the floor and its axis 0.8 m in front of you. The marked band runs round the bag from 0.95 m to 1.25 m above the floor. Your first touch of the bag is your kick. It must be made with your right foot or right shin alone and must first meet the bag inside the band. It is a blow, not a push: the touch lasts at most 0.15 s (it ends when leg and bag have been apart for 0.03 s), and during it the bag must receive an impulse of at least 20.0 N s, measured as the change of the bag's angular momentum about its hook divided by the depth below the hook of the lowest point the blow touched. You succeed when, after the kick, you stand for 2.0 s without a break: both feet and nothing else on the floor, the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. You fail if anything other than the right foot or shin touches the bag at any time; if the kick lands outside the band, is too weak or is a push; if anything touches the bag again after the kick; if you fall (your pelvis lower than 0.5 m above the floor, or any part of you other than your feet on the floor); or after 15 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Rule book | No rule book for a bag. The kick is judged by the scoring criterion of World Taekwondo's Competition Rules (a valid point is a kick delivered with a part of the foot below the ankle bone to the trunk protector, with the required level of impact) and of kickboxing (the shin also strikes), applied to a standard heavy bag (30 kg, 1.2 m, on a chain); deviations: No opponent: the scoring area is a marked band on a heavy bag (0.95 m to 1.25 m above the floor: trunk height, 1.1 m, for the robot); one kick, not a bout. · The striking surface is the named leg's foot or shin (taekwondo scores the foot only). · "The required level of impact" is measured: the impulse the bag receives during the touch (the change of the bag's angular momentum about its hook, divided by the depth below the hook of the lowest point the blow touched) must be at least 20.0 N s; "not a push": the touch lasts at most 0.15 s. Both numbers are this benchmark's (a light, clean kick of a trained adult on a heavy bag), not a rule book's. · The chain is rigid: the bag and its chain swing as one body about the hook (a ball joint). |
| Stages | strike → stand |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `c9813e923f8e39fedfc5896829181d3fcb898a0463dda8cd31991bab01e783ef` |
| Episode | 1500 control steps (15 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
