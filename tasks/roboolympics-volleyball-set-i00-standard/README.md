# roboolympics-volleyball-set-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-volleyball-set-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `volleyball_set` / seed 0 |
| Oracle | `full` — Reference: raised fists driven up through the falling toss on the walking policy, from a technique found offline by CMA-ES (RoboOlympics' method, search_technique.py): 6.6 m/s in, 6.95 m/s out upward, up to 4.02 m, down 0.28 m from the target's centre. Open loop on the frozen start, not robust. Referee test negatives: still fists (the ball leaves slower), before the apex, leaving the front zone, not overhead, a forearm, too low, outside the target, a second touch, held The privileged twin's reference rows (587 control steps, success after 5.87 s) streamed through the client. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Set the pass: with one overhead contact of your hands, send the volleyball that comes down above you at least a metre above the net and into the outside hitter's target along the net. (RoboOlympics `volleyball-set`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The hands (rubber fists) have to meet a 7 m/s ball above the head and drive it away faster than it came, up to nearly 4 m and 5 m along the net into a 2 m circle, in a contact of a few hundredths of a second: the angle and the speed both have to be right, and arms that are only held up return the ball too slowly. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the client (`solution/rows.npz`, recorded by scripts/roboolympics/make_oracles.py). Reference: raised fists driven up through the falling toss on the walking policy, from a technique found offline by CMA-ES (RoboOlympics' method, search_technique.py): 6.6 m/s in, 6.95 m/s out upward, up to 4.02 m, down 0.28 m from the target's centre. Open loop on the frozen start, not robust. Referee test negatives: still fists (the ball leaves slower), before the apex, leaving the front zone, not overhead, a forearm, too low, outside the target, a second touch, held The privileged twin's reference rows (587 control steps, success after 5.87 s) streamed through the client.

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: You are the setter on an official volleyball court (9.0 m by 9.0 m on each side of the net; the net's top 2.43 m high). You stand in your front zone facing along the net: the net is 1.0 m to your right, the attack line 3.0 m from the centre line to your left, the side line of position 2 3.0 m behind you, the side line of position 4 ahead of you. A volleyball (0.21 m across, 0.27 kg, in air) is tossed to you from the back court 3.0 s after the start and comes down above you. The set is the ball's first contact after the toss, before it touches the floor: with your hands (the parts beyond the wrists; one or both), overhead (the ball's centre above the top of your head, which is 0.76 m above your waist joint along the trunk), after the ball has passed its highest point, all contacts within 0.1 s, over when the ball has been clear of you for 0.03 s. It must be a set, not a rebound: the ball leaves your hands moving upward and at least 1.0 times as fast as it was just before they touched it. Then the ball's centre must rise at least 1.0 m above the net's top, and the ball must come down in the outside hitter's target: its first contact with the floor is inside a circle of 1.0 m radius whose centre is 1.0 m from the net on your side and 1.0 m inside the side line ahead of you. That is the success. You fail if the ball touches the floor before your set, if any part of you other than a hand touches the ball, if the ball's centre is not above the top of your head when your hands first touch it, if you touch it before it has passed its highest point, if the contacts last longer than 0.1 s (the ball held), if the ball leaves your hands downward or slower than that, if you touch the ball again, if it does not rise that high or comes down outside the target, if before your set your pelvis is farther from the net than the attack line (you left the front zone), if you touch the net, an antenna or a post, if a foot of yours is on the floor wholly beyond the centre line, if you fall (your pelvis lower than 0.35 m above the floor, or any part of you other than the feet on the floor), or after 10 s. The ball cannot be gripped, and it cannot be touched while it waits to be tossed.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | football-and-volleyball |
| Rule book | FIVB Official Volleyball Rules 2025-2028: Rule 1 (the court 18 m x 9 m, the front zone between the centre line and the attack line 3 m from it), Rule 2 (the men's net, top at 2.43 m, the antennas), Rule 3 (the ball: 65-67 cm round, 260-280 g), Rule 9.2 (the hit: not caught or thrown, one contact), Rule 11 (no contact with the net, the foot not wholly beyond the centre line); deviations: The pass is a scripted launch: a ball tossed without spin from the back court, the same in every attempt, instead of a team-mate. · Rule 9.2 (the overhead pass with the fingers): the robot has no fingers, so the set is one contact of the hands (the parts beyond the wrists) with the ball's centre above the top of the robot's head (0.76 m above its waist joint along the trunk, about 1.80 m when it stands). 'Not caught or thrown' is a contact of at most 0.1 s (the ball cannot be gripped). · A set is judged by numbers instead of a referee's eye: the ball must leave the hands moving upward and at least 1.0 times as fast as it arrived (hands held still in the ball's path return it at no more than three quarters of its speed: that is a rebound, not a set); it must be played after it has passed its highest point, by a setter who has stayed in the front zone. · Nobody attacks the set: a good set is defined as volleyball coaching grades it, a ball that rises at least 1.0 m above the net and comes down in the outside hitter's target, a circle of 1.0 m radius at position 4, judged where the ball first touches the floor. · No team-mates or opponents, no wind. |
| Stages | set → above the net → in the target |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1000 control steps (10 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
