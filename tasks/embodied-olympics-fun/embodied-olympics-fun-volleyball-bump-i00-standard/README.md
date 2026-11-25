# embodied-olympics-fun-volleyball-bump-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-volleyball-bump-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `volleyball_bump` / seed 0 |
| Oracle | `full` — Reference, on Unitree's actuator data (H2-class legs, rotor inertia, joint friction): a walk forward and to the left, then a forearm platform held through the contact; the walk, key times and the platform's joint offsets from CMA-ES, with penalties for the arms coming within 5 cm of each other and for any arm passing into the body. The serve comes from the ball machine behind the far end line; the ball meets the right forearm (it also brushes the wrist-pitch link by 2 mm), comes in at 11.3 m/s, leaves at 8.0 m/s, rises to 3.30 m and lands 0.13 m from the target centre; success after 5.85 s. The arms stay at least 2.9 cm apart and no arm passes into the body (at most 0.4 mm). It is open loop on the one serve: 4 of 6 perturbations succeed (servo gains x0.97 / x1.03 and the timing 10 ms earlier / later pass; a machine launch speed 0.5 % lower or higher fails, because the ball misses the platform). The privileged twin's reference rows (584 control steps, success after 5.84 s) streamed through the client. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Pass the serve: with one forearm pass, send the ball up above net height and down onto the setter's target. (Embodied Olympics `volleyball-bump`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The arms have to be made into a platform 0.7 m to the side and in front of where the robot stands, within about four seconds of a walking policy that manages half a metre per second sideways, and angled so that an 11 m/s ball rebounds 2 m up and 5 m forward into a 2 m circle: a few degrees of platform angle are a metre at the target. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the client (`solution/rows.npz`, recorded at generation time). Reference, on Unitree's actuator data (H2-class legs, rotor inertia, joint friction): a walk forward and to the left, then a forearm platform held through the contact; the walk, key times and the platform's joint offsets from CMA-ES, with penalties for the arms coming within 5 cm of each other and for any arm passing into the body. The serve comes from the ball machine behind the far end line; the ball meets the right forearm (it also brushes the wrist-pitch link by 2 mm), comes in at 11.3 m/s, leaves at 8.0 m/s, rises to 3.30 m and lands 0.13 m from the target centre; success after 5.85 s. The arms stay at least 2.9 cm apart and no arm passes into the body (at most 0.4 mm). It is open loop on the one serve: 4 of 6 perturbations succeed (servo gains x0.97 / x1.03 and the timing 10 ms earlier / later pass; a machine launch speed 0.5 % lower or higher fails, because the ball misses the platform). The privileged twin's reference rows (584 control steps, success after 5.84 s) streamed through the client.

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: You stand in your own half of an official volleyball court (9.0 m by 9.0 m on each side of the net), facing the net, 6.0 m from it, midway between the side lines. The net's top is 2.43 m high. A volleyball (0.21 m across, 0.27 kg, in air) is served over the net from behind the far end line 3.0 s after the start: a float serve, without spin, that comes down in your part of the court. The pass is the ball's first contact after the serve, on your side of the net and before it touches the floor: with your forearms or hands (one arm or both; the arm from the elbow down), all contacts within 0.1 s, over when the ball has been clear of you for 0.03 s. After it the ball's centre must rise above the height of the net's top, and the ball must come down in the setter's target: its first contact with the floor is inside a circle of 1.0 m radius whose centre is 1.0 m from the net on your side and 1.5 m to the right of the court's middle (to your right as you face the net). That is the success. You fail if you touch the ball machine or the ball waiting in it, if the ball touches the floor before your pass, if any part of you other than a forearm or a hand touches the ball, if the pass's contacts last longer than 0.1 s (the ball held), if you touch the ball again after the pass, if you touch the ball before it has crossed the net, if the ball comes down outside the target or without having risen above the net's height, if you touch the net, an antenna or a post, if a foot of yours is on the floor wholly beyond the centre line, if you fall (your pelvis lower than 0.35 m above the floor, or any part of you other than the feet on the floor), or after 10 s. The ball cannot be gripped.

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
| Category | football-and-volleyball |
| Rule book | FIVB Official Volleyball Rules 2025-2028: Rule 1 (the court 18 m x 9 m, the attack lines 3 m from the centre line), Rule 2 (the men's net, top at 2.43 m, the antennas), Rule 3 (the ball: 65-67 cm round, 260-280 g), Rule 9.2 (the hit: the ball may touch any part of the body, it must not be caught or thrown), Rule 11 (no contact with the net, the foot not wholly beyond the centre line), Rule 14.5 (the serve may not be blocked); deviations: Rule 12 (the service): the serve is played by a two-wheel volleyball machine on a stand 0.6 m behind the far end line instead of an opponent, the same in every attempt: its wheels, at equal speeds, drive the ball out 2.6 m above the floor at about 14 m/s without spin (a float serve); the ball follows MuJoCo's drag model, without a float serve's sideways wobble. · Rule 9.2 lets a team-mate play the ball next; here nobody does, and a good reception is defined as volleyball coaching grades it: the pass rises above the net's height and comes down in the setter's target, a circle of 1.0 m radius 1.0 m from the net between positions 2 and 3, judged where the ball first touches the floor. · The family asks for the forearm pass: only the forearms and the hands (the arm from the elbow down) may touch the ball, where Rule 9.2.1 allows any part of the body. 'Not caught or thrown' is a contact of at most 0.1 s (the ball cannot be gripped). · Rule 2: the net is a rigid panel 1 m deep and the posts and antennas are rigid (a real net is a mesh under tension that gives); a robot touching any of them commits the Rule 11 fault all the same. · No team-mates or opponents, no wind. |
| Stages | pass → above the net height → in the target |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1000 control steps (10 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
