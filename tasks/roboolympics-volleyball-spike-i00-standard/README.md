# roboolympics-volleyball-spike-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-volleyball-spike-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `volleyball_spike` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_volleyball_spike.py: positive by injection (a real arm, the real set onto the fist at 2.69 m, a 3.2 m/s ghost jump, the ball's velocity set, a softened landing); negatives: a leg tuck or a lift without a jump, a still fist in a jump, from the floor, before the apex, upward, into the net, long, the antenna, a second touch, a net touch, the centre line. No jump or landing controller exists for the H1-2; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Spike the set: jump and strike the volleyball that comes down near the net with a hand, above the height of the net, down into the opponent's court, and land on your feet without touching the net. (RoboOlympics `volleyball-spike`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The robot reaches 2.24 m standing: its hand has to be above 2.43 m, so it must jump at least a quarter of a metre, after an approach of about 2 m on a walking policy, and swing through a ball that falls through the reachable window in under a tenth of a second, half a metre from a net it may not touch, then land a 67 kg body on its feet. No jumping skill is built in. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-volleyball-spike-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: You are the outside hitter on an official volleyball court (9.0 m by 9.0 m on each side of the net; the net's top 2.43 m high, an antenna above each side line). You stand on your attack line facing the net, which is 3.0 m ahead of you; the left side line is 1.0 m to your left. A volleyball (0.21 m across, 0.27 kg, in air) is set from your right 3.0 s after the start: it rises to 4.5 m and comes down 0.5 m from the net, in front of you. In order: (1) the spike: the ball's first contact after the set, before it touches the floor, is with a hand of yours (the parts beyond the wrist; one or both), after the ball has passed its highest point, at points that are all higher than the net's top, while you are in the air (nothing of you touches the floor or anything else) in a jump: during that flight your pelvis rises at least 0.1 m above the height it had when your feet left the floor. All contacts lie within 0.1 s (the strike is over when the ball has been clear of you for 0.03 s), and the ball leaves your hand moving downward and at least 1.0 times as fast as it was just before the hand touched it. (2) the ball crosses the net's plane above the net and between the antennas; it may touch the net. (3) the ball's first contact with the floor is in the opponent's court (9.0 m by 9.0 m, lines included); from then on the ball is dead and what it touches is not judged. (4) after that you stand for 1.0 s without a break (only your feet on the floor, your trunk within about 20 degrees of upright, your pelvis slower than 0.35 m/s): that is the success. You fail if the ball touches the floor before the spike, if any part of you other than a hand touches it, if you touch it before it has passed its highest point, from the floor, below the height of the net's top, or in a flight in which your pelvis did not rise 0.1 m, if the contacts last longer than 0.1 s, if the ball leaves the hand upward or slower than that, if you touch the ball again, if it crosses the net's plane under the net or outside the antennas or touches an antenna, if it lands anywhere else, if you touch the net, an antenna or a post at any time, if a foot of yours is on the floor wholly beyond the centre line, if you fall (your pelvis lower than 0.35 m above the floor, or any part of you other than the feet on the floor), or after 12 s. The ball cannot be gripped, and it cannot be touched while it waits to be set. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Rule book | FIVB Official Volleyball Rules 2025-2028: Rule 1 (the court 18 m x 9 m, the attack lines), Rule 2 (the men's net, top at 2.43 m, the antennas), Rule 3 (the ball: 65-67 cm round, 260-280 g), Rule 8 (ball in and out: the lines belong to the court; a ball that touches an antenna or crosses outside the crossing space is out), Rule 9.2 (the hit: not caught or thrown, one contact), Rule 10.2 (the ball may touch the net), Rule 11.2-11.3 (the foot not wholly beyond the centre line; no contact with the net), Rule 13 (the attack hit); deviations: The set is a scripted launch from the setter's place at position 2/3: a ball without spin that rises to 4.5 m and comes down 0.5 m from the net at position 4, the same in every attempt, instead of a team-mate. · The family asks for the spike, where Rule 13 allows any attack hit: the ball is struck with a hand (the parts beyond the wrist) at a point above the height of the net's top, while the robot is in the air in a jump (its pelvis rises at least 0.1 m above where it was when the feet left the floor: drawing the legs up is not a jump), after the ball has passed its highest point, and the ball leaves the hand moving downward and at least 1.0 times as fast as it arrived (a hand held in the ball's path returns it slower). 'Not caught or thrown' is a contact of at most 0.1 s. · Rule 11 is judged for the whole attempt, until the robot has landed and stood for 1.0 s after the ball is down: there is no rally to end the play. · No blockers or defenders, no wind. |
| Stages | spike → over the net → in the court → landing |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1200 control steps (12 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
