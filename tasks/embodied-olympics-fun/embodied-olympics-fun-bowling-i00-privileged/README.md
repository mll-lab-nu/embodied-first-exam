# embodied-olympics-fun-bowling-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-bowling-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `bowling` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_bowling.py: positive by injection (a real release, the ball laid 0.35 m past the line at 8 m/s into the pocket: a strike); negatives: over the foul line, a gutter ball, a head-pin hit that is no strike, touched after the release, a foul after the delivery. Strikes exist from 4 m/s on (2 of 17 entry lines 1 cm apart); a swing of the H1-2 gives 3.3 m/s and it falls during the swing; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Bowl a strike: from behind the foul line, deliver the ball that hangs from your right hand down the lane so that all ten pins are knocked down. (Embodied Olympics `bowling`: one Unitree H1-2 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
A strike needs the ball in the pocket beside the head pin, a few centimetres wide, after 18 m of lane on which it slides on the oil and grips on the dry boards; a 6 lb ball is deflected by the pins more than a heavy one, so it must also arrive fast. Nothing but the release aims it, and the body may not cross the foul line.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a real release, the ball laid 0.35 m past the line at 8 m/s into the pocket: a strike); negatives: over the foul line, a gutter ball, a head-pin hit that is no strike, touched after the release, a foul after the delivery. Strikes exist from 4 m/s on (2 of 17 entry lines 1 cm apart); a swing of the H1-2 gives 3.3 m/s and it falls during the swing.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The lane is 1.0541 m wide and runs 18.288 m from the foul line to the head pin's spot, with a gutter 0.235 m wide and 0.047 m deep on each side; behind the foul line the approach, level with the lane, is 4.572 m long. Ten pins (0.381 m tall, 1.53 kg each) stand in the triangle of four rows, 0.3048 m apart, its point towards you. The ball (0.218 m across, 2.72 kg) hangs from your right hand. The lane is oiled (friction 0.04) for the first 13.5 m in its middle, less far on its outside boards, and dry (friction 0.2) beyond. A delivery: you let go of the ball (once: it cannot be gripped again) and it crosses the foul line. It is a foul if any part of you touches the lane, a gutter or anything else on or beyond the foul line, at any time. Pins count only if the ball reaches them on the lane: a ball that touches a gutter before it has touched a pin knocks down nothing. A pin is down when it is tilted more than 20.0 degrees or is no longer on the lane's surface; the pins are counted 5.0 s after the ball first touches one. You succeed with a strike: all ten pins down. You fail on a foul; on a gutter ball; if fewer than ten pins are down at the count; if any part of you touches the ball after the release (your right arm may still brush it during the first 0.2 s); if you fall before the count (your pelvis lower than 0.5 m above the approach, or any part of you other than your feet on the approach or the floor); or after 40 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (4090-ws1, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | USBC Playing Rules 2024-2025 and USBC Equipment Specifications: the lane (60 ft from the foul line to the head pin, 41.5 in wide, gutters, pin deck), the pins (15 in, 3 lb 6 oz, 12 in apart), the ball (at most 8.595 in and 16 lb); the playing rules on a strike, a legal delivery, the foul (Rule 5) and legal and illegal pinfall; deviations: Equipment (ball): the hand holds the ball by a grip switched on and off, which stands for the finger holes (the ball hangs from the end of the hand); a uniform ball, no weight block; it is released when the grip is switched off. · Equipment (pins): each pin is six stacked cylinders and capsules that follow the official profile, with the official mass, centre of gravity and the profile's moments of inertia. · Lane condition: Embodied Olympics' house pattern as friction zones (oil, friction 0.04, for 13.5 m in the middle of the lane and 3 m shorter on the outside boards; a 1.2 m transition; then dry boards, friction 0.2); the values are Embodied Olympics' assumptions after Frohlich (2004), not a measured lane. · Pinfall and the pin count: a pin is down when it is tilted more than 20.0 degrees or is off the lane's surface (Embodied Olympics' rule: a pin leaning on a wall counts as down); the count is taken 5.0 s after the ball first touches a pin. No pinsetter, no sweep; the pit is 0.1 m deep. · Rule 5: the foul is judged at any time, not only during or after the delivery; a fall also ends the attempt as a failure, as in every task of this benchmark. · One ball: the task is the first ball of a frame. |
| Stages | delivery → pins → strike |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `15b8452eef3ae4b49c91f53b81263d1c5610ba14ba3fd77ce71d56a8ab4277ff` |
| Episode | 4000 control steps (40 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
