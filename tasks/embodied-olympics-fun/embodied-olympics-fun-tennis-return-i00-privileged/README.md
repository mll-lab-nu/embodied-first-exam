# embodied-olympics-fun-tennis-return-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-tennis-return-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `tennis_return` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_tennis_return.py: positive by injection (the real 30 m/s serve, bounce and contact with the strings; the robot moved 2.9 m sideways and the return's velocity set at the contact: 24 m/s at 9 degrees); negatives: two bounces, the own side, outside the court, through the net, a volley, the body, a double hit, carried, a net touch. The serve reaches the baseline at 15 m/s after 1.1 s, 1.5 m from the robot, which moves 1.2 m in that time; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Return the serve: after the tennis ball has bounced once in your service box, hit it with the racket on your right hand back over the net so that it lands in the singles court on the far side. (Embodied Olympics `tennis-return`: one Unitree H1-2 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The ball crosses the whole court in about a second and is still moving at more than 15 m/s when it reaches you, so the racket has to be in a path a few centimetres wide at an instant you must predict, and a robot that only walks cannot go far to meet it. A racket merely held in the way sends the ball back at a fraction of its speed, well short of the net twelve metres away: the return needs a real swing through a 0.30 kg racket.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (the real 30 m/s serve, bounce and contact with the strings; the robot moved 2.9 m sideways and the return's velocity set at the contact: 24 m/s at 9 degrees); negatives: two bounces, the own side, outside the court, through the net, a volley, the body, a double hit, carried, a net touch. The serve reaches the baseline at 15 m/s after 1.1 s, 1.5 m from the robot, which moves 1.2 m in that time.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The court is the ITF singles court: 23.77 m long and 8.23 m wide, measured to the outside of the lines, with a service line 6.4 m from the net on each side. The net stands across the middle, 0.914 m high at its centre and rising in a straight line to 1.07 m at the posts, which stand 0.914 m outside the sidelines. The ball is the ITF ball (radius 0.0335 m, 0.0577 kg, with air drag and spin lift); the racket (0.685 m long, 0.30 kg, strung surface 0.33 m by 0.25 m) is fixed to your right hand. 3.0 s after the start the ball is served from behind the far baseline at 30.0 m/s into your right service box. In order: the ball bounces once on your side; your racket hits it (any part of the racket counts); its centre passes the net's plane from your side to the far side, above the net's top edge or outside a post (it may touch the net or a post on the way); and its first contact with the ground after that is inside the far half of the singles court, the lines included (the point under the ball's centre decides; ground contacts less than 0.02 s apart are one bounce): that is the success. You fail if the racket touches the ball before its bounce (a volley), if the ball bounces a second time on your side before your hit, if after your hit the ball touches the ground on your side or outside the far court, if the ball touches any part of you other than the racket at any time after the serve, if the racket touches the ball a second time (contacts less than 0.05 s apart are one hit) or stays on it longer than 0.05 s, if the ball passes the net's plane between the posts below the net's top edge, if any part of you or the racket touches the net or a post, or the ground beyond the net's plane, if anything of you touches the ball before it is served, if you fall, or after 10 s. A fall is: your pelvis lower than 0.35 m above the ground, or any part of you other than your feet touching the ground; the racket may touch the ground. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | basketball-and-rackets |
| Rule book | ITF Rules of Tennis 2024: Rule 1 (the court), Rule 3 and Appendix I (the ball), Rule 4 and Appendix II (the racket), Rule 12 (a ball on a line), Rules 24 and 25 (losing the point, a good return); deviations: Rules 16-21 (the service): the server is a machine: the ball appears at the server's strike point and leaves it with the serve's velocity and spin 3.0 s after the start; there is no opponent, the attempt ends when your return lands · Rule 4 (the racket in the hand): the racket is clamped to the right hand with its handle along the forearm (the hand has no fingers to change the grip); it cannot be dropped or thrown · Rule 12 (a ball touching a line is in): the ball's footprint is one point, the point under its centre at its first contact with the ground (a real ball's footprint is about 5 cm across) · Rule 24 f (deliberately touching the ball twice, carrying it): intention cannot be judged: racket contacts less than 0.05 s apart are one hit, a later one is a second hit, and a contact longer than 0.05 s is a carry · Rule 1 (the net): a 2 cm thick wall instead of a mesh of cord; a ball that meets it is stopped by a stiff, strongly damped contact · wind and weather: none; the air is still (sea level, 15 C) |
| Stages | bounce → racket → over the net → in |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `168380b08d6ad9f86956334e7641b560a53ec2dc04c5bc1e50aea9c15875291c` |
| Episode | 1000 control steps (10 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
