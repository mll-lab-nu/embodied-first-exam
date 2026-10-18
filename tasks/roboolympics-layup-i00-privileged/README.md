# roboolympics-layup-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-layup-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `layup` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_layup.py: positive by injection (a real arm raise and two real walking steps, a 2.6 m/s ghost take-off, a real release in flight with a 4.4 m/s toss set at the release); negatives: a third step, the same foot twice, not in the air, in the air without a take-off, too far from the ring, a miss, touched again, from below, a fall. The H1-2 has no jump; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Make a layup: with the basketball in your right hand take at most two steps towards the basket, jump, and let go of the ball in the air close to the ring so that it enters the basket from above. (RoboOlympics `layup`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Two steps and a jump have to carry a 67 kg body almost two metres with a ball in one hand, and the release comes in the air, about a metre below a ring that is 0.21 m wider than the ball. The robot has a walking gait and nothing that jumps or lands. The built-in walking gait steps on the spot even at a zero command, so while the ball is in your hand its steps are counted like any others.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a real arm raise and two real walking steps, a 2.6 m/s ghost take-off, a real release in flight with a 4.4 m/s toss set at the release); negatives: a third step, the same foot twice, not in the air, in the air without a take-off, too far from the ring, a miss, touched again, from below, a fall. The H1-2 has no jump.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The official basket: a rigid ring of 0.45 m inner diameter (0.018 m metal), its top edge 3.05 m above the floor, its centre 0.375 m in front of a backboard 1.8 m wide and 1.05 m high whose lower edge is 2.9 m above the floor. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor); it flies in air (drag and spin lift). It starts gripped in your right hand. Travelling: while the ball is in your hand you may take at most 2 steps. A step is a foot touching the floor after it has been off it for at least 0.03 s; both feet landing within 0.03 s of each other are one step; the same foot may not touch down twice in a row, and a foot on the floor may not slide more than 0.2 m from where it stood or was put down (a shuffle is travelling). After that no foot may touch the floor again until you have let go of the ball. The release: at the moment you let go you must be in the air: nothing of you has touched anything but the ball for at least 0.05 s, after a take-off at which your pelvis was moving upwards at 0.5 m/s or more; and the ball's centre must be within 1.25 m (horizontally) of the ring's centre, the radius of the no-charge semi-circle painted under the basket. You succeed when, after that release, the ball's centre goes down through the ring's plane inside the ring and on down to one ball diameter below it (off the backboard or not). You fail if you travel; if you let go of the ball with something of you on the floor, without a take-off, or further from the ring; if any part of you touches the ball more than 0.05 s after you let go of it (it cannot be gripped again); if the ball touches the floor before it is through the ring; if the ball's centre comes up through the ring from below; if you fall before the ball is through (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 15 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | basketball-and-rackets |
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court, no-charge semi-circle), Art. 3 and the Basketball Equipment appendix (backboard, ring, size-7 ball), Art. 16 (goal), Art. 25 (travelling); deviations: Art. 3 (equipment): the hand holds the ball by a grip switched on and off, not by fingers; the ball is released when the grip is switched off. · Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not slow the ball. A goal is judged at the ring: the ball's centre down through the ring's plane and on to one ball diameter below it. · Art. 25.2.1: you start standing with the ball in the hand and are judged as a player who has just ended a dribble while moving: two steps are allowed (a standing player would have a pivot foot instead), since no dribble precedes the layup here. After the two steps no foot may touch the floor again while the ball is held: pivoting after a stop is not offered. · The layup itself is not defined by the rule book: here it is a shot let go in the air (after a real take-off) with the ball inside the no-charge semi-circle's radius of the ring (1.25 m, Art. 2.4.7); a shot from further out or from the floor is not a layup. · One attempt, no opponent, no rebound: touching the ball after the release ends the attempt. |
| Stages | approach → release in the air → through the ring |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `cc352a24c80adddbfcb2fa7583b73e91a85970d8d16d068d4b3e7d30aeb2ccd2` |
| Episode | 1500 control steps (15 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
