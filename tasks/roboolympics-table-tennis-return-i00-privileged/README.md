# roboolympics-table-tennis-return-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-table-tennis-return-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `table_tennis_return` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_table_tennis_return.py: positive by injection (a real waist-turn stroke with the robot put at the end line in its pre-stroke pose; the contact, the flight and the landing are real); negatives: two bounces, the return on the own court (a real still-blade block), obstruction, another part, struck twice, the table's side, the floor, the net, the free hand on the table. The drawn serve is short: the ball is in reach for 0.14 s, and the stroke returns it in 11 of 25 nearby variants; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Return the service: after the table tennis ball has bounced once on your court, strike it with the paddle on your right hand so that it touches the opponent's court. (RoboOlympics `table-tennis-return`: one Unitree G1 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The served ball is over your court for a few tenths of a second, low above a table that is as high as your hips, and may have to be met far inside the end line: the blade, a rigid extension of a 0.5 m arm, has to be there at the right instant and angle while the body leans over the table without touching the net. The return must clear a 15 cm net and still come down on a court 1.37 m long, off a ball that carries spin.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a real waist-turn stroke with the robot put at the end line in its pre-stroke pose; the contact, the flight and the landing are real); negatives: two bounces, the return on the own court (a real still-blade block), obstruction, another part, struck twice, the table's side, the floor, the net, the free hand on the table. The drawn serve is short: the ball is in reach for 0.14 s, and the stroke returns it in 11 of 25 nearby variants.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The table is the official one: 2.74 m long, 1.525 m wide, its playing surface 0.76 m above the floor, with a net 0.1525 m high across its middle that reaches 0.1525 m beyond each side line. Your court is the half of the playing surface on your side of the net, the opponent's court the other half; the top edges belong to the playing surface, the sides of the table top do not (a ball that touches the table with its centre below the level of the playing surface has hit the side). The ball is the official one (40 mm, 2.7 g) and flies in air: drag and the lift of its spin act on it. A racket (a rigid square blade 0.15 m wide, 0.015 m thick, 0.14 kg with its handle) is fixed to your right hand, the racket hand; your left hand is the free hand. The service is struck 3.0 s after the start: a legal service, so the ball bounces first on the server's court, passes the net and bounces on your court. Then you must make a good return (Law 2.7): strike the ball, after that one bounce on your court, with the blade or with the racket hand below the wrist, so that it touches the opponent's court, directly or after touching the net; it may pass over or around the net. You succeed at the moment the ball touches the opponent's court after your strike. All contacts of the blade or the racket hand with the ball within 0.05 s of the first are one strike. You fail if you touch the ball before the service, or before it has bounced on your court (obstruction); if the ball bounces a second time on your court before you strike it (ball contacts with the table less than 0.02 s apart are one bounce); if anything of yours other than the blade or the racket hand touches the ball (the racket's handle, an arm, the body); if the blade or the racket hand touches the ball again later than 0.05 s after the first contact (struck twice, or carried); if after your strike the ball touches your own court, the side of the table or the floor before the opponent's court; if the ball touches the floor at any time; if any part of you or the racket touches the net; if your free hand touches the playing surface while the ball is in play (from the service on); if you fall; or after 8 s. Anything else of you, the racket included, may touch the table. A fall is your pelvis lower than 0.35 m above the floor, or any part of you other than your feet touching the floor (the racket on the floor is a fall). No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | basketball-and-rackets |
| Rule book | ITTF Handbook 2024, The Laws of Table Tennis: 2.1 (the table), 2.2 (the net assembly), 2.3 (the ball), 2.4 (the racket), 2.5 (definitions: struck, obstruction, racket hand, free hand), 2.6 (the service), 2.7 (the return), 2.10 (a point); deviations: 2.6.1-2.6.3 (the service): there is no server and no toss: the ball waits at the server's strike point and is launched at 3.0 s with the position, velocity and spin it has at the strike of a legal service of RoboOlympics' serve library (a service a Franka arm made under its real limits; entry 221, the draw of this instance's seed, not chosen for being returnable), because the task is one return, not a match · 2.1.3 (the table's bounce): the playing surface is Google DeepMind's system-identified table, on which a ball dropped from 30 cm rebounds 26 cm, not the Law's about 23 cm; it is the only identified model of the ball's bounce with spin there is · 2.2 (the net): the net is a rigid wall 1 cm thick, 0.1525 m high, reaching 0.1525 m beyond each side line, without separate posts or a cord (DeepMind's model); a soft net is not simulated · 2.4 (the racket): the blade is a rigid 15 cm square, 1.5 cm thick, 0.14 kg with its handle (legal: the Laws set no size, shape or weight); its covering is one contact law on both faces (RoboOlympics' ball-paddle pair, hand-picked, not identified), and it is fixed to the right hand, because the robot's fist cannot hold a handle · 2.10.1.7 (deliberately striking the ball twice): intent cannot be judged: every contact of the blade or the racket hand within 0.05 s of the first is the same strike, a later one is a second strike · 2.10.1.8 (moving the playing surface): the table is fixed and this is not judged: a competition table weighs three times the robot and more, and the robot's push on it is limited by the grip of its own feet · 2.5.8 and 2.10.1 (the ball touching the player): any touch of the ball by anything but the blade or the racket hand loses the point, also after the ball has bounced on the robot's court (stricter than the Laws, which then only require that the return be struck) |
| Stages | bounce → strike → opponent's court |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `2c9fa33de509ae5ea70d2008408f411038954baa80b963e9ea19cd510e82fa05` |
| Episode | 800 control steps (8 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
