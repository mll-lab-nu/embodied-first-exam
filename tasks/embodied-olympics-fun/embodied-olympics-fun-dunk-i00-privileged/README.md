# embodied-olympics-fun-dunk-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-dunk-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `dunk` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_dunk.py: positive by injection (a real arm raise, a 4.5 m/s ghost take-off, the gripped ball really taken down through the ring; the landing is injected too); negatives: let go before the dunk, from below, through without a hand on it, a third step, a fall. Standing, the gripped ball reaches 2.37 m; the ring is at 3.05 m; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Dunk the basketball in your right hand: jump, force it down through the ring from above with your hand on it, and land on your feet. (Embodied Olympics `dunk`: one Unitree H1-2 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
With the arm straight up the gripped ball's centre is about 2.4 m above the floor; the ring is at 3.05 m, so the whole 67 kg body has to rise more than 0.7 m with the ball over the ring, and then come down on its feet. The robot has a walking gait and nothing that jumps or lands. The built-in walking gait steps on the spot even at a zero command, so while the ball is in your hand its steps are counted like any others.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a real arm raise, a 4.5 m/s ghost take-off, the gripped ball really taken down through the ring; the landing is injected too); negatives: let go before the dunk, from below, through without a hand on it, a third step, a fall. Standing, the gripped ball reaches 2.37 m; the ring is at 3.05 m.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The official basket: a rigid ring of 0.45 m inner diameter (0.018 m metal), its top edge 3.05 m above the floor, its centre 0.375 m in front of a backboard 1.8 m wide and 1.05 m high whose lower edge is 2.9 m above the floor. The ball is a size-7 basketball (0.239 m across, 0.62 kg). It starts gripped in your right hand. The dunk: the ball's centre goes down through the ring's plane inside the ring while your hand grips the ball, and on down to one ball diameter below the ring (in the hand, or let go once its centre is inside the ring). The ball may not pass up through the ring first: a ball whose centre comes up through the ring from below is a violation. Until its centre is inside the ring the ball must stay gripped. Travelling: while the ball is in your hand you may take at most 2 steps. A step is a foot touching the floor after it has been off it for at least 0.03 s; both feet landing within 0.03 s of each other are one step; the same foot may not touch down twice in a row; a foot on the floor may not slide more than 0.2 m from where it stood or was put down; after that no foot may touch the floor again until the ball is through the ring. After the dunk let go of the ball and stand: for 1.0 s without a break only your feet touch the ground, your torso is upright (the cosine of its tilt at least 0.94) and your pelvis moves slower than 0.35 m/s. Then you have succeeded. You fail if you travel; if you let go of the ball before its centre has entered the ring; if, let go inside the ring, it touches the floor without having gone through; if the ball goes through the ring after an entry at which no hand gripped it (a shot, not a dunk); if the ball comes up through the ring from below; if you fall at any time (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 15 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (backboard, ring, size-7 ball), Art. 15 (a dunk: the ball forced downwards into the basket with one or both hands), Art. 16 (goal; a ball that passes through the basket from below is a violation), Art. 25 (travelling); deviations: Art. 3 (equipment): the hand holds the ball by a grip switched on and off, not by fingers; the ball is released when the grip is switched off. · Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not slow the ball. The ball is through the basket when its centre has gone down through the ring's plane inside the ring and on to one ball diameter below it. · Art. 25.2.1: you start standing with the ball in the hand and are judged as a player who has just ended a dribble while moving: two steps are allowed (a standing player would have a pivot foot instead). After the two steps no foot may touch the floor again while the ball is held: pivoting after a stop is not offered. · The landing (on the feet, standing 1.0 s) is this task's own requirement; the rule book asks nothing of a player after a goal. |
| Stages | dunk → stand |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `f72d2caafe7a3aac0c205cc46c5d5071bb15a6b8321688442b33b6ea643eec52` |
| Episode | 1500 control steps (15 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
