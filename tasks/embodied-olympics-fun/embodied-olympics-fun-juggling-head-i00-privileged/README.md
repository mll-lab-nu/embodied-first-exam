# embodied-olympics-fun-juggling-head-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-juggling-head-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `juggling_head` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_juggling_head.py: positive by a REAL controller for the first header (a lowcmd squat timed to the fed ball: in 3.37, out 3.39 m/s, contact 0.011 s) and by injection for ten (the ball really falls on the head, sent up at 3.5 m/s after each contact); negatives: nop (one passive bounce at 0.83 of the speed, then the ground), a still head with the ball kept centred (bounces uncounted, then touched too soon), weak touches, the ball laid on the head (carried: a touch may last 0.05 s, twice a human header's 25 ms), a hand, the chest, a shoulder, nine then the ground, out of the grid, a fall. Head-ball restitution is the ball's hard-surface bounce (the G1's head is a hard shell; no measured live-head value found; a deviation). Nine controller variants (squat bob + waist head positioning, ~8k sims) reach at most 2 headers: 1 cm off the head's top sends the ball sideways at 0.3 m/s; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Juggle the football on your head: a feeder drops it onto your head; keep it in the air with ten headers in a row, touching it with nothing but your head, without it touching the ground. (Embodied Olympics `juggling-head`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Every header must give the falling 0.43 kg ball back more speed than a still head would, so the head has to meet it moving up at the right moment, ten times in a row; and the head is round and only about 15 cm across, so a contact one centimetre off its top sends the ball sideways at about 0.3 m/s and a few centimetres off it out of reach, all while the robot keeps its balance.

## Reference solution
None. No reference controller exists for this family yet: positive by a REAL controller for the first header (a lowcmd squat timed to the fed ball: in 3.37, out 3.39 m/s, contact 0.011 s) and by injection for ten (the ball really falls on the head, sent up at 3.5 m/s after each contact); negatives: nop (one passive bounce at 0.83 of the speed, then the ground), a still head with the ball kept centred (bounces uncounted, then touched too soon), weak touches, the ball laid on the head (carried: a touch may last 0.05 s, twice a human header's 25 ms), a hand, the chest, a shoulder, nine then the ground, out of the grid, a fall. Head-ball restitution is the ball's hard-surface bounce (the G1's head is a hard shell; no measured live-head value found; a deviation). Nine controller variants (squat bob + waist head positioning, ~8k sims) reach at most 2 headers: 1 cm off the head's top sends the ball sideways at 0.3 m/s.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: You stand in the middle of a square grid 4.572 m on a side (5 yards; cones at its corners) on level grass. A size-5 football (0.22 m across, 0.43 kg, in air) is held still by a feeder 2.0 m above the ground over your head; it cannot be touched until it is let go, at 1.0 s, when it falls. From then on, a touch is a contact of the ball with your head (contacts less than 0.05 s apart are one touch). A touch is a header that counts when the ball's centre has then risen at least 0.22 m above the height it had when the touch began, before anything touches it again, and when the ball left the touch with at least 0.95 of the speed it had just before it (both taken at the height where the touch began): the head must strike the ball, a ball that only bounces on a still head leaves slower; such a touch is not counted, and is not a fault. This holds for the first touch too. You succeed at the moment the 10th header counts. You fail if the ball touches the ground, if any part of you other than the head touches it (the shoulders, the chest, an arm, a hand, a leg), if one touch lasts longer than 0.05 s (the ball resting or balanced on the head), if the ball is touched again before it has risen 0.22 m, if a foot steps out of the grid (a foot's ankle joint beyond its edge), if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 60 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | football-and-volleyball |
| Rule book | Ontario Soccer Association, Technical Benchmark Exercises (2015, for U12-U13 players), exercise 1 'Head Juggling': one attempt, the player in a 5 x 5 yard grid keeps the ball up with the head, each head juggle one point, the count stopped by the ball touching the ground, by another body part, or by stepping out of the grid; the benchmark records the count and sets no pass mark, so the family's standard is 10 consecutive headers (the same standard as the family 'juggling'). IFAB Laws of the Game 2025/26 for the ball (Law 2: size 5, 68-70 cm round, 410-450 g); deviations: The start: in the benchmark the ball starts in the player's hands and the player throws it up onto the head; the robot has fists and no fingers, so a feeder drops the ball instead: it is held still 2.0 m above the ground over the robot's head and let go at 1.0 s (the same in every attempt). Until then it cannot be touched. · A counter's eye is replaced by numbers: contacts less than 0.05 s apart are one touch, a touch may last at most 0.05 s, and the ball's centre must then rise at least 0.22 m (one ball diameter) above where it was when the touch began, before anything touches it again. The limit on a touch's length is twice a measured human header's (about 25 ms: Bayly et al., IEEE EMBS 2002, the same subjects as Naunheim et al., Med Sci Sports Exerc 35:1406-1412, 2003; a size-5 ball's contact with the robot's head lasts about 11 ms), so that a ball cushioned on the head and pushed up is not a header. · The ball bounces off the robot's hard head shell as off a hard floor (the ball's own restitution from the rule book's drop test; a still head held by its motors returns about 0.83 of the speed). A human head and neck are softer: the heading model of Naunheim et al. (2003) takes a restitution of 0.4 to 0.7, but no measurement of the ball on a live head was found, and the robot's head is not a human's; the simulation keeps the robot's own contact, so a robot header needs less head speed than a human one (about 0.2 m/s up against a ball arriving at 3.4 m/s, instead of about 0.7 m/s with 0.6). · A header is a strike: so that a ball that merely bounces on a still head (it returns about 0.8 of its speed, each bounce lower) is not head juggling, a touch counts only if the ball leaves it with at least 0.95 of the speed it arrived with; the first touch too, because the ball is fed, not thrown up by the robot. A touch that does not is not counted and is not a fault. · The head: the G1's head is the upper hull of its torso link (the part 'head'); any other part of the robot touching the ball (the shoulders, the chest, an arm) is another body part. · Stepping out of the grid is judged by the feet: a foot's ankle joint beyond the grid's edge. No wind. |
| Stages | header 1 → header 2 → header 3 → header 4 → header 5 → header 6 → header 7 → header 8 → header 9 → header 10 |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `8a32425316101e4337e754ff5a7bfc6ac2ed3fdb1387918670fdb6975c2a5730` |
| Episode | 6000 control steps (60 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
