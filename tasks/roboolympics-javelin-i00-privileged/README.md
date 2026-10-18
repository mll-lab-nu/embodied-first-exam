# roboolympics-javelin-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-javelin-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `javelin` / seed 0 |
| Oracle | `full` — Reference: a standing throw by the trunk's turn, the hand above the shoulder, from a technique found offline by CMA-ES over whole-body key poses (RoboOlympics' method, search_technique.py): 15.0 m/s at 37 degrees, head first at 21.58 m (the line is 20 m), then back 4 m behind the arc and standing. Open loop on the frozen start, not robust. Referee test negatives: an underarm release, the back turned, over the arc, off the runway early, tail first, outside the sector, short, touched after the release, out in front Measured (make_oracles.py): success after 15.33 s of the 60 s limit, live and in a fresh replay, ending in the same state. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Throw the javelin in your right hand over the shoulder from behind the arc so that its head strikes the ground first, inside the sector, at least 20.0 m from the arc, then leave the runway behind the arc and stand. (RoboOlympics `javelin`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
20.0 m asks for a release at about 14 m/s near 35 to 40 degrees with the javelin pointing along its flight, or it will not come down head first; the H1-2 has no running policy and its arm motors give 40 N m at the shoulder. The throw must come from above the shoulder on a body that has to stay on its feet behind the arc.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Reference: a standing throw by the trunk's turn, the hand above the shoulder, from a technique found offline by CMA-ES over whole-body key poses (RoboOlympics' method, search_technique.py): 15.0 m/s at 37 degrees, head first at 21.58 m (the line is 20 m), then back 4 m behind the arc and standing. Open loop on the frozen start, not robust. Referee test negatives: an underarm release, the back turned, over the arc, off the runway early, tail first, outside the sector, short, touched after the release, out in front Measured (make_oracles.py): success after 15.33 s of the 60 s limit, live and in a fresh replay, ending in the same state.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The men's javelin (0.8 kg, 2.65 m long, its centre of gravity 0.98 m from the tip, a metal head of 0.29 m) is gripped at its cord, at the centre of gravity, by your right hand. The runway is 4.0 m wide between the inner edges of its side lines and 30.0 m long; it ends at the arc, a white strip whose inner edge is a circle of 8.0 m radius round a point on the runway's centre line; short white lines run outwards from the arc's two ends at right angles to the side lines. The sector is bounded by the two lines from the arc's centre through the arc's ends (28.96 degrees between them). The throw: you let go of the javelin (once: it cannot be gripped again) while the grip's centre is at least 0.0 m higher than your right shoulder joint. It is valid only if the head touches the ground before any other part of the javelin, at a point inside the sector lines (on a line is out). It is measured from that point to the inner edge of the arc along the line through the arc's centre. You succeed when a valid throw measures at least 20.0 m and you have then left the runway correctly and stood for 1.0 s. Leaving correctly: after the javelin has landed, your first touch of a side line or of the ground outside the runway is behind the arc's end lines, or you touch the ground 4.0 m or more behind the arc's ends. Standing: only your feet on the ground, the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. You fail if, at any time before that, any part of you touches the arc, its end lines or the ground beyond them; if you touch a side line or the ground outside the runway (also behind its rear end) before the javelin has landed; if your chest is turned more than 135.0 degrees away from the throwing direction before the release (your back to the arc); if the javelin is let go lower than the shoulder; if it does not land head first, lands outside the sector or short of 20.0 m; if any part of you touches it after the release (your throwing arm may still brush it during the first 0.2 s); if you fall (your pelvis lower than 0.5 m above the ground, or any part of you other than your feet on the ground); or after 60 s. Where you touch the ground is judged on the points of contact.

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
| Rule book | World Athletics Competition and Technical Rules 2024: TR 32.9 (the javelin runway and its arc), TR 32.12 (the sector), TR 32.14, 32.16, 32.17 and 32.20 (throwing events: failures, the landing, leaving the runway, the measurement), TR 38.1 (the throw), TR 38.3-38.6 (the men's javelin); deviations: TR 38.1(a) (the cord grip): the hand holds the javelin at its cord, round its centre of gravity, by a grip switched on and off, not by fingers; it is released when the grip is switched off. "Over the shoulder or upper part of the throwing arm" is judged at the release: the grip's centre must then be at least 0.0 m higher than the throwing shoulder's joint. · TR 38.1(c): "turned completely around" is judged as the chest's heading more than 135.0 degrees away from the throwing direction at any time before the release. · TR 38.3-38.6: the javelin is one rigid body (no bending or vibration) whose head does not stick in the ground; the mark is the point where the head first touches the ground. · Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model with coefficients of the order of the published wind-tunnel data, the centre of pressure 0.25 m behind the centre of gravity), still air, no wind. The model's drag does not grow with the angle of attack as a real javelin's does: a javelin released nose-high flies up to a fifth farther here than it would. · TR 32.15 (interrupting a trial, laying the implement down): not modelled; the first release is the throw, and the javelin cannot be gripped again. · TR 32.14 names no fall: here a fall ends the trial as a failure, as in every task of this benchmark; the trial ends when the robot has left the runway correctly and stands. · TR 25.17 (one minute for a trial): the whole trial, leaving the runway included, has 60 s. · The qualifying mark of 20.0 m is this benchmark's (a boys' school standard for the 800 g javelin); the rule book only measures. |
| Stages | release → landing → exit |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `026b77df3a5941d10bb8503f7011001ad10f1352b4285acb0a14110e525defc7` |
| Episode | 6000 control steps (60 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
