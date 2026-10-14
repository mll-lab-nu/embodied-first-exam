# roboolympics-steeplechase-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-steeplechase-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `steeplechase` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_steeplechase.py: positive by injection (a flight over the 0.914 m hurdle and the pit; a landing in the pit with a second hop out; from standing on the bar); negatives: under, round, a trailing foot, to the side of the water jump. The H1-2's open-loop squat jump raises its centre of mass 0.16 m; the walking policy does not climb the pit's slope; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Go over the steeplechase hurdle in front of you and over or through the water pit behind it, get out beyond the pit's far edge and stand on your feet. (RoboOlympics `steeplechase`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The bar is at hip height and the walking policy lifts its feet a few centimetres: the hurdle has to be jumped or climbed with whole-body joint control by a 67 kg robot whose best standing jump raises it far less than 0.914 m. Behind the bar the ground is 0.5 m lower than the track, so the landing is a drop of up to 1.4 m, and the way out is a slope.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a flight over the 0.914 m hurdle and the pit; a landing in the pit with a second hop out; from standing on the bar); negatives: under, round, a trailing foot, to the side of the water jump. The H1-2's open-loop squat jump raises its centre of mass 0.16 m; the walking policy does not climb the pit's slope.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The hurdle is fixed (it does not move or topple): its top bar is 0.127 m square, 3.66 m wide, with its top 0.914 m above the track, on a post at each end. Its near face is 10.0 m ahead of where your pelvis starts. The water jump is 3.66 m long measured from the hurdle's near face, and 3.66 m wide, centred on your line: the pit is 0.5 m deep for the first 1.2 m and then slopes up evenly to the track's level at its far edge. There is no water in it. You must go over the hurdle: every time your pelvis or the centre of either foot crosses, going forward, the vertical plane through the middle of the top bar, that point must be higher than the bar's top (0.914 m), and your pelvis must also be between the two ends of the bar; otherwise you fail. You may go over the hurdle in any manner: your hands and feet may touch it or stand on it. Once your pelvis is beyond that plane and until your whole body is beyond the pit's far edge, you fail if your pelvis is outside the pit's width or if any part of you touches the track's surface beside the pit (a contact less than 0.05 m below the track's level; the pit's side walls below that may be touched). You may land in the pit or beyond it, and any part of you may touch the pit's floor and walls and the track before and beyond the pit: there is no fall rule. You succeed when your whole body is beyond the pit's far edge and you then stand for 1.0 s without a break: only your feet on the ground, your torso within 20.0 degrees of vertical, your pelvis moving no faster than 0.35 m/s. The attempt ends after 60 s of robot time. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | parkour-apparatus-balance |
| Rule book | World Athletics Competition and Technical Rules 2024, Technical Rule 23 (steeplechase races): the men's hurdle 0.914 m high with a top bar 0.127 m square; the hurdle at the water jump 3.66 m wide and fixed; the water jump 3.66 m long including the hurdle, the pit 3.66 m wide, 0.50 m deep at the hurdle for about 1.20 m, then a uniform slope up to the level of the track at the far end; each athlete shall go over each hurdle (in any manner) and over or through the water, and is disqualified for stepping to one side of the water jump or trailing a foot or leg below the horizontal plane of the top of the hurdle at the instant of clearance; deviations: TR 23 (the race): one water jump from a 10.0 m approach instead of a 3000 m race with 28 hurdle and 7 water jumps (a single action; the family is the water jump) · TR 23 (the water jump): the water itself is not simulated; the pit is dry and its floor is the hard, sloping bottom (the simulator has no free-surface water; what remains is the pit's real geometry) · TR 23 (clearance): "foot or leg below the top of the hurdle" is judged on the centres of the two feet and the pelvis where each crosses the vertical plane through the middle of the hurdle's top bar (three points a referee can measure on a robot) · the finish: with no race to run on to, the attempt ends when the whole body is beyond the pit's far edge and the robot has stood on its feet for 1.0 s |
| Stages | hurdle → out of the water jump → stand |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `c8ea61116d7aa693fc094b0ab2821b1d89dcbe4ba3d7b1ff69258c275fa22452` |
| Episode | 6000 control steps (60 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
