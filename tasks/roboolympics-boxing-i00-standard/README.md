# roboolympics-boxing-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-boxing-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `boxing` / seed 0 |
| Oracle | `full` — Reference: a straight right from the guard behind a trunk turn, then the walking policy to stay up: 15.7 N s on the 30 kg bag (the line is 12), a 0.07 s touch; 12 of 12 variations when it was written. The meter reads a known injected impulse 1.5 % low. The privileged twin's reference rows (404 control steps, success after 4.04 s) streamed through the client. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Punch the heavy bag once with the knuckles of your right fist, on the marked band, hard enough to give it 12.0 N s, then bring the fist back to your guard and stand. (RoboOlympics `boxing`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
12.0 N s in a tenth of a second cannot be pushed out of arm motors of 40 N m: the fist has to arrive at speed with the arm's and the trunk's mass behind it, end first, and leave again at once. The reaction must not tip a body that only stands by an open-loop stance, and the bag swings back. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the client (`solution/rows.npz`, recorded by scripts/roboolympics/make_oracles.py). Reference: a straight right from the guard behind a trunk turn, then the walking policy to stay up: 15.7 N s on the 30 kg bag (the line is 12), a 0.07 s touch; 12 of 12 variations when it was written. The meter reads a known injected impulse 1.5 % low. The privileged twin's reference rows (404 control steps, success after 4.04 s) streamed through the client.

## Verification
The sim sidecar's referee judges the live attempt, then the service replays the recorded attempt in a fresh simulator;
`tests/grade.py` reads `/data/final.json`: pass iff the live run and the replay succeed and end in the same state. The
rules: A heavy bag (30.0 kg, 1.2 m long, 0.35 m across) hangs by a 0.5 m chain from a hook, free to swing in every direction; its top is 1.75 m above the floor and its axis 0.75 m in front of you. The marked band runs round the bag from 1.2 m to 1.6 m above the floor. Your first touch of the bag is your punch. It must be made with the knuckle part of your right fist alone (the far 0.03 m of the hand's pad, the end that points along the forearm) and must first meet the bag inside the band. It is a blow, not a push: the touch lasts at most 0.1 s (it ends when fist and bag have been apart for 0.03 s), and during it the bag must receive an impulse of at least 12.0 N s, measured as the change of the bag's angular momentum about its hook divided by the depth below the hook of the lowest point the blow touched. After the blow, bring the fist back: you succeed when your right palm has been within 0.35 m of your right shoulder joint for 2.0 s without a break while you stand (only your feet on the ground, the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s). You fail if anything other than the knuckle part of the right fist touches the bag at any time; if the punch lands outside the band, is too weak or is a push; if anything touches the bag again after the punch; if you fall (your pelvis lower than 0.5 m above the floor, or any part of you other than your feet on the floor); or after 15 s.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | No rule book for a bag. The punch is judged by the scoring criterion of Olympic-style boxing (IBA Technical and Competition Rules: a scoring blow lands with the knuckle part of the closed glove on the target area, with force; a push or a slap does not score), applied to a standard heavy bag (30 kg, 1.2 m, on a chain); deviations: No opponent: the target area is a marked band on a heavy bag (1.2 m to 1.6 m above the floor, head and chest height for the robot); one punch, not a bout. · The glove is the robot's fist (the pad of the hand, 4.4 x 8 x 10 cm); its knuckle part is the pad's last 0.03 m. · "Force behind the blow" is measured: the impulse the bag receives during the touch (the change of the bag's angular momentum about its hook, divided by the depth below the hook of the lowest point the blow touched) must be at least 12.0 N s; "not a push": the touch lasts at most 0.1 s. Both numbers are this benchmark's (a light, clean punch of a trained adult on a heavy bag), not the rule book's. · The chain is rigid: the bag and its chain swing as one body about the hook (a ball joint). |
| Stages | strike → guard |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1500 control steps (15 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
