# embodied-olympics-fun-free-throw-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-free-throw-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `free_throw` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_free_throw.py: positive by injection (a real underhand swing and release at 7.4 m/s, the ball's velocity set to 8.1 m/s at 58 degrees: a real flight and ring); negatives: not released in 5 s, the floor, touched again, the line, the semi-circle, from below, a fall. The shot needs 8.06 m/s at 58 degrees; the arm reaches 11 m/s with the elbow fired late, and about 400 search evaluations came within 0.37 m of the ring's centre; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Shoot a free throw: from behind the free-throw line, throw the basketball in your right hand so that it enters the basket from above. (Embodied Olympics `free-throw`: one Unitree H1-2 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
From a hand about a metre above the floor the 0.62 kg ball needs to leave at about 8 m/s on a steep arc to reach a ring 3.05 m high and more than 4 m away, with a margin of a few centimetres in air that slows it, and within five seconds. A straight-arm swing at the shoulder's speed limit gives less than that, and the body only stands by an open-loop stance.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a real underhand swing and release at 7.4 m/s, the ball's velocity set to 8.1 m/s at 58 degrees: a real flight and ring); negatives: not released in 5 s, the floor, touched again, the line, the semi-circle, from below, a fall. The shot needs 8.06 m/s at 58 degrees; the arm reaches 11 m/s with the elbow fired late, and about 400 search evaluations came within 0.37 m of the ring's centre.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The official basket: a rigid ring of 0.45 m inner diameter (0.018 m metal), its top edge 3.05 m above the floor, its centre 0.375 m in front of a backboard 1.8 m wide and 1.05 m high whose lower edge is 2.9 m above the floor. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor); it flies in air (drag and spin lift). It starts gripped in your right hand and is at your disposal at the start. The free-throw line's edge nearest to you is 4.225 m from the point under the ring's centre; the free-throw semi-circle has a radius of 1.8 m round the middle of that edge. You succeed when, after you have let go of the ball, its centre goes down through the ring's plane inside the ring and on down to one ball diameter below it. You fail if you have not let go of the ball within 5.0 s; if, before the ball has touched the ring or entered the basket, any part of you touches the floor on or beyond the free-throw line's near edge or outside the semi-circle; if any part of you touches the ball more than 0.05 s after you let go of it (it cannot be gripped again); if the ball touches the floor before it is through the ring; if the ball's centre comes up through the ring from below; if you fall before the ball is through (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 12 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | basketball-and-rackets |
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (backboard, ring, size-7 ball), Art. 16 (goal), Art. 43 (free throws); deviations: Art. 3 (equipment): the hand holds the ball by a grip switched on and off, not by fingers; the ball is released when the grip is switched off. · Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not slow the ball. A goal is judged at the ring: the ball's centre down through the ring's plane and on to one ball diameter below it. · Art. 43.2.3: the ball is at your disposal at the start of the episode; there is no referee, no opponent and no rebound: one throw, and touching the ball after the release ends the attempt. |
| Stages | release → through the ring |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `717168dc362f3932b2b80edf6c74d09a300da1c1da687a2cd129708e0c099707` |
| Episode | 1200 control steps (12 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
