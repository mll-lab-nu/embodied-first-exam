# roboolympics-fun-volleyball-serve-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-fun-volleyball-serve-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `volleyball_serve` / seed 0 |
| Oracle | `full` — Reference: an underarm serve (left fist tosses, straight right arm and the trunk's turn hit) from a technique found offline by CMA-ES over whole-body key poses (RoboOlympics' method, search_technique.py): 2.2 m/s in, 11.4 m/s out, over the net into the court 1.8 m beyond it. Referee test negatives: a throw brushing the fist, hit out of the hand, a still fist, the head, into the net, outside the antenna, long, a foot fault, a second touch, held The privileged twin's reference rows (328 control steps, success after 3.28 s) streamed through the client. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Serve the volleyball: from behind the end line, toss it out of your left hand and hit it with one hand or arm over the net into the opponent's court. (RoboOlympics `volleyball-serve`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The ball has to leave the hit at about 11 m/s (10.8 m/s from 2.2 m up, 11.5 m/s underarm from 1 m) to clear a 2.43 m net 9 m away and still come down inside the far court: a fist at 6 to 7 m/s, about the most a full swing of this arm gives, through a ball the robot has tossed itself, at the right instant, on a 67 kg robot whose stand has no balance feedback. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the client (`solution/rows.npz`, recorded by scripts/roboolympics/make_oracles.py). Reference: an underarm serve (left fist tosses, straight right arm and the trunk's turn hit) from a technique found offline by CMA-ES over whole-body key poses (RoboOlympics' method, search_technique.py): 2.2 m/s in, 11.4 m/s out, over the net into the court 1.8 m beyond it. Referee test negatives: a throw brushing the fist, hit out of the hand, a still fist, the head, into the net, outside the antenna, long, a foot fault, a second touch, held The privileged twin's reference rows (328 control steps, success after 3.28 s) streamed through the client.

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: You stand behind the end line of an official volleyball court (9.0 m by 9.0 m on each side of the net), facing the net, midway between the side lines; the end line's outer edge is 0.5 m ahead of your pelvis and the net is 9.0 m beyond it, its top 2.43 m high, with an antenna above each side line. A volleyball (0.21 m across, 0.27 kg, in air) starts gripped on your left fist. In order: (1) the toss: no hand grips the ball any more; for 0.1 s from the release the hand that held it may still touch it (it follows the toss up; any other touch in that time is already the hit), and the ball must be clear of that hand when that time ends. (2) the hit: the next contact of the ball, with one hand or one arm of yours (hand, forearm or upper arm of the same side), within 8.0 s of the start. The ball must have been clear of you for at least 0.1 s before the hit (counted from the end of the last touch of the toss), moving at most 5.0 m/s just before it; the hit's contacts last at most 0.1 s (it is over when the ball has been clear of you for 0.03 s), and the ball leaves the hit faster than it arrived. At the first contact of the hit no foot of yours touches the court (the end line included) or the floor beyond the extensions of the side lines; if you are in the air, this holds for where you took off. (3) the ball crosses the net's plane above the net and between the antennas; it may touch the net. (4) the ball's first contact with the floor is in the opponent's court (9.0 m by 9.0 m, lines included): that is the success. You fail if the hit does not come within 8.0 s, if after the toss the ball touches the floor or any other part of you before the hit, if it is hit before it has been clear for 0.1 s, if it moves faster than 5.0 m/s just before the hit, if the hit is made with more than one arm or another part, lasts longer than 0.1 s or does not add speed, if you touch the ball again or grip it again, at a foot fault, if the ball crosses the net's plane under the net or outside the antennas or touches an antenna, if it lands anywhere else, if you fall (your pelvis lower than 0.35 m above the floor, or any part of you other than the feet on the floor), or after 12 s.

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
| Rule book | FIVB Official Volleyball Rules 2025-2028: Rule 1 (the court 18 m x 9 m, the service zone 9 m wide behind the end line), Rule 2 (the men's net, top at 2.43 m, the antennas), Rule 3 (the ball: 65-67 cm round, 260-280 g), Rule 8 (ball in and out: the lines belong to the court; a ball that touches an antenna or crosses the net's plane outside the crossing space is out), Rule 10.2 (the ball may touch the net while crossing it), Rule 12.4 (the service: the ball is hit with one hand or any part of the arm after being tossed or released from the hands; one toss only; the server does not touch the court or the floor outside the service zone at the hit; the hit comes within 8 s of the whistle); deviations: Rule 12.4.1 (tossed or released): the robot has no fingers; the ball starts held on its left fist by the simulator's grip and is released by opening it. A referee's eye for 'tossed, then hit' is replaced by numbers: after the release the ball must be clear of the robot for at least 0.1 s before the hit, it may move at most 5.0 m/s just before the hit (the speed of a ball that has fallen about 1.3 m: a toss, not a throw), the hit's contacts last at most 0.1 s, and the ball must leave the hit faster than it arrived. · Rule 12.4.3 (the server's feet) is judged at the first contact of the hit, or at the take-off before it when the robot is in the air; the whistle is the start of the episode. · No opponents (nobody receives the serve), no wind. |
| Stages | toss → hit → over the net → in the court |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1200 control steps (12 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
