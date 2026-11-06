# embodied-olympics-fun-dodgeball-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-dodgeball-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `dodgeball` / seed 0 |
| Oracle | `full` — Reference: the G1 turns side-on and walks back and forth on the walking policy so that it is moving at each feed; five 14.2 m/s throws from turret-aimed machines all miss; 9 of 10 perturbations (feed times, speed, gap, aim height, machine distance) succeed, the machine at 2.8 m fails. Measured: success after 13.06 s of the 15.5 s limit, live and in a fresh replay, ending in the same state. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Dodge: five cloth dodgeballs are thrown at you by ball machines that aim at you; do not let a live ball touch you, stay inside your court and on your feet. (Embodied Olympics `dodgeball`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
A ball thrown at you reaches you about 0.75 s after it leaves the machine, aimed where you were: standing still is a hit; the G1 has to be moving when each ball is thrown and keep moving, within its court, with a walking policy that makes about 0.5 m/s, and turn its narrow side to the throws.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Reference: the G1 turns side-on and walks back and forth on the walking policy so that it is moving at each feed; five 14.2 m/s throws from turret-aimed machines all miss; 9 of 10 perturbations (feed times, speed, gap, aim height, machine distance) succeed, the machine at 2.8 m fails. Measured: success after 13.06 s of the 15.5 s limit, live and in a fresh replay, ending in the same state.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: You stand in your fair territory on a WDBF cloth dodgeball court (18.0 m x 9.0 m, lines 5 cm wide drawn inside it), 5 m behind the centre line, facing it (+x). Five ball machines stand in the opponents' half, 3.0 m beyond the centre line, 1.5 m apart across the court (at 0, -3, +3, -1.5 and +1.5 m from its middle, in the order they throw), each holding one dodgeball (17.78 cm, 0.13 kg, cloth over foam, in air). Each machine's exit is 1.2 m above the floor; its turret points it at where your pelvis is at that moment, at a height of 0.8 m, allowing for the ball's drag, until it is fed; it throws at 14.0 m/s. The first is fed at 2.0 s, the others 2.5 s apart. A thrown ball is live from the moment it leaves its machine until it touches the floor or anything that is not you or a ball; then it is dead. You fail if a live ball touches any part of you (rule 15.1); if any part of you touches a boundary line or the floor outside them, the opponents' neutral zone line (7.0 m from their back line) or anything beyond it (rule 26); if you fall (your pelvis lower than 0.35 m above the floor, or any part of you other than the feet on the floor); or after 15.5 s. A throw is dodged when its ball is dead, or 3.0 s after it left the machine, without having touched you; you succeed when all five are dodged. The machines' wheels turn at 15.9 m/s at their rims (the throw's speed comes from them).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | WDBF Cloth Dodgeball Rules 2026 (World Dodgeball Federation): rule 1.1 (the playing court 18 m x 9 m), 1.3 (lines 5 cm wide, drawn inside the court; the centre line; the neutral zone lines 7 m from the back lines), 1.4 (fair territory, neutral zone), 2.1-2.3 (five balls of textured no-sting cloth over foam over a butyl bladder, 17.78 cm across, 110-125 mbar), 15.1 (a live player is out when hit by a live ball on any part of the body or clothing), 16.2 and 16.6 (a thrown ball is live from the throw until it touches a surface or a dead object that is not a ball), 26.1-26.5 (out of bounds: touching a boundary line, a surface outside them, the opponents' fair territory or the neutral zone line next to it: out); deviations: Rule 16 (the throwers): the five throws come from five two-wheel ball machines (the shared machine block, one ball each) standing in the opponents' fair territory 3.0 m beyond the centre line, their exits 1.2 m high, each on a turret (a yaw and a pitch joint driven by torque-limited servos, 20.0 and 30.0 N m) whose controller points it, until its feed, at where you are now: your pelvis, at a height of 0.8 m, with the elevation that the ball's drag needs for that distance; it does not lead a moving target. Each throws at 14.0 m/s with no spin, the first fed at 2.0 s and the others 2.5 s apart: an opposing team cannot be simulated. · Rules 20-22 (blocks and catches): you hold no ball, so you cannot block, and the robot cannot catch: any contact of a live ball with you is a hit (rule 15.1 counts every part, the head too). · Rule 2: the rules give no mass for the ball; it is 0.13 kg here (an estimate from its construction), its bounce, drag and stiffness are estimates from its pressure and build (said in the module). · The match is reduced to one player surviving five throws (rule 9: sets, players, the opening rush and the shot clock of rule 18 do not apply); you must stay on your feet, which the rules do not require. |
| Stages | dodge 1 → dodge 2 → dodge 3 → dodge 4 → dodge 5 |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `1d86ef085d9b6ebbe1a90405340a03b2dca5442ee79e996905095a593d1c8b81` |
| Episode | 1550 control steps (15.5 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
