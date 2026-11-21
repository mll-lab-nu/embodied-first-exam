# embodied-olympics-fun-dodgeball-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-dodgeball-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `dodgeball` / seed 0 |
| Oracle | `full` — Reference: the G1 turns side-on and walks back and forth on the walking policy so that it is moving at each feed; five 14.2 m/s throws from turret-aimed machines all miss; 9 of 10 perturbations (feed times, speed, gap, aim height, machine distance) succeed, the machine at 2.8 m fails. The privileged twin's reference rows (1306 control steps, success after 13.06 s) streamed through the client. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Dodge: five cloth dodgeballs are thrown at you by ball machines that aim at you; do not let a live ball touch you, stay inside your court and on your feet. (Embodied Olympics `dodgeball`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
A ball thrown at you reaches you about 0.75 s after it leaves the machine, aimed where you were: standing still is a hit; the G1 has to be moving when each ball is thrown and keep moving, within its court, with a walking policy that makes about 0.5 m/s, and turn its narrow side to the throws. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the client (`solution/rows.npz`, recorded at generation time). Reference: the G1 turns side-on and walks back and forth on the walking policy so that it is moving at each feed; five 14.2 m/s throws from turret-aimed machines all miss; 9 of 10 perturbations (feed times, speed, gap, aim height, machine distance) succeed, the machine at 2.8 m fails. The privileged twin's reference rows (1306 control steps, success after 13.06 s) streamed through the client.

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: You stand in your fair territory on a WDBF cloth dodgeball court (18.0 m x 9.0 m, lines 5 cm wide drawn inside it), 5 m behind the centre line, facing it (+x). Five ball machines stand in the opponents' half, 3.0 m beyond the centre line, 1.5 m apart across the court (at 0, -3, +3, -1.5 and +1.5 m from its middle, in the order they throw), each holding one dodgeball (17.78 cm, 0.13 kg, cloth over foam, in air). Each machine's exit is 1.2 m above the floor; its turret points it at where your pelvis is at that moment, at a height of 0.8 m, allowing for the ball's drag, until it is fed; it throws at 14.0 m/s. The first is fed at 2.0 s, the others 2.5 s apart. A thrown ball is live from the moment it leaves its machine until it touches the floor or anything that is not you or a ball; then it is dead. You fail if a live ball touches any part of you (rule 15.1); if any part of you touches a boundary line or the floor outside them, the opponents' neutral zone line (7.0 m from their back line) or anything beyond it (rule 26); if you fall (your pelvis lower than 0.35 m above the floor, or any part of you other than the feet on the floor); or after 15.5 s. A throw is dodged when its ball is dead, or 3.0 s after it left the machine, without having touched you; you succeed when all five are dodged. The machines' wheels turn at 15.9 m/s at their rims (the throw's speed comes from them).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 10 GiB |
| `sim` | 4 | 5 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | WDBF Cloth Dodgeball Rules 2026 (World Dodgeball Federation): rule 1.1 (the playing court 18 m x 9 m), 1.3 (lines 5 cm wide, drawn inside the court; the centre line; the neutral zone lines 7 m from the back lines), 1.4 (fair territory, neutral zone), 2.1-2.3 (five balls of textured no-sting cloth over foam over a butyl bladder, 17.78 cm across, 110-125 mbar), 15.1 (a live player is out when hit by a live ball on any part of the body or clothing), 16.2 and 16.6 (a thrown ball is live from the throw until it touches a surface or a dead object that is not a ball), 26.1-26.5 (out of bounds: touching a boundary line, a surface outside them, the opponents' fair territory or the neutral zone line next to it: out); deviations: Rule 16 (the throwers): the five throws come from five two-wheel ball machines (the shared machine block, one ball each) standing in the opponents' fair territory 3.0 m beyond the centre line, their exits 1.2 m high, each on a turret (a yaw and a pitch joint driven by torque-limited servos, 20.0 and 30.0 N m) whose controller points it, until its feed, at where you are now: your pelvis, at a height of 0.8 m, with the elevation that the ball's drag needs for that distance; it does not lead a moving target. Each throws at 14.0 m/s with no spin, the first fed at 2.0 s and the others 2.5 s apart: an opposing team cannot be simulated. · Rules 20-22 (blocks and catches): you hold no ball, so you cannot block, and the robot cannot catch: any contact of a live ball with you is a hit (rule 15.1 counts every part, the head too). · Rule 2: the rules give no mass for the ball; it is 0.13 kg here (an estimate from its construction), its bounce, drag and stiffness are estimates from its pressure and build (said in the module). · The match is reduced to one player surviving five throws (rule 9: sets, players, the opening rush and the shot clock of rule 18 do not apply); you must stay on your feet, which the rules do not require. |
| Stages | dodge 1 → dodge 2 → dodge 3 → dodge 4 → dodge 5 |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1550 control steps (15.5 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
