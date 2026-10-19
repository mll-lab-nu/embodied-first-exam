# roboolympics-fun-golf-putt-realgrasp-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-fun-golf-putt-realgrasp-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `golf_putt_realgrasp` / seed 0 |
| Oracle | `full` — one Dex1-1 across the grip; club starts hanging (level it turns 23-25 deg in the jaws); two-hand address unreachable by IK; reference carries the club shaft-vertical and swings by wrist roll: holed at 17.3 s, 10/12 perturbations The privileged twin's reference rows (1730 control steps, success after 17.3 s) streamed through the client. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Hole the 3.0 m putt: with one stroke of the putter held in your right hand's gripper, roll the golf ball that lies on the green into the hole, without letting go of the putter. (RoboOlympics `golf-putt-realgrasp`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The hole is two and a half ball widths across and three metres away: the ball must start within about one degree of the line and at a speed between the one that just reaches the hole and the one that jumps it, and there is no second stroke. The club is an adult's, long and heavy for this robot's wrist, and it has to be brought from where it starts to an address beside the ball first. It is held across a two-finger gripper's jaws by friction: tilted towards its toe it turns in the jaws, so it has to be carried with the shaft near the vertical, and the swing rocks it in the jaws, so the face at impact is not quite where the arm put it. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the client (`solution/rows.npz`, recorded by scripts/roboolympics/make_oracles.py). one Dex1-1 across the grip; club starts hanging (level it turns 23-25 deg in the jaws); two-hand address unreachable by IK; reference carries the club shaft-vertical and swings by wrist roll: holed at 17.3 s, 10/12 perturbations The privileged twin's reference rows (1730 control steps, success after 17.3 s) streamed through the client.

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The ball (42.67 mm, 45.9 g) lies at rest on a flat green of stimp 10 (a ball that starts rolling at 1.83 m/s stops after 3.05 m). The hole is cut into the green 3.0 m from the ball: 0.108 m across and 0.1016 m deep, with no flagstick in it. A putter (0.86 m long, 0.5 kg, 3.0 degrees of loft, a round grip 0.024 m thick and 0.26 m long) is a separate body; at the start its grip is closed across the jaws of your right hand's two-finger gripper, which holds it by friction only: it can slip, turn in the gripper and fall. The putter is in your hand while its grip touches both of the gripper's jaws; it has left your hand when for more than 0.05 s the grip has not touched both jaws. Your left hand may hold the grip too; the putter may touch nothing of you but your two hands. You succeed when the ball is holed with one stroke: after the stroke it comes to rest (its centre moves less than 0.001 m in 1.0 s) inside the hole with the whole ball below the surface of the green. A stroke is a fair strike of the ball with the putter's head (any side of the head): the first contact of the head with the ball starts it, every further contact must come within 0.2 s of the first (an accidental double hit is still one stroke), and all the contacts together may last at most 0.03 s. You fail if the putter leaves your right hand at any time (dropped, thrown or slipped out of the gripper); if the putter touches any part of you other than your hands; if the contacts last longer (the ball was pushed, scraped or scooped), if the head touches the ball again later (a second stroke), if anything else of you ever touches the ball (the putter's shaft or grip, a foot, a leg, a hand), if at the moment of the stroke your feet touch the green on both sides of the line of play (the straight line through the ball's spot and the hole's centre, extended behind the ball) or on that line, if the ball comes to rest anywhere but in the hole (on the lip and on the green beyond the hole included), if the ball leaves the green, if you fall (your pelvis lower than 0.35 m above the green, or any part of you other than your feet touching the ground; the putter may touch the green as long as it stays in your hand), or after 30 s.

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
| Category | basketball-and-rackets |
| Rule book | The Rules of Golf (R&A / USGA, 2023): Definitions "Hole", "Holed", "Stroke", "Line of Play"; Rules 8.1b, 9.4, 10.1a, 10.1b, 10.1c, 11.1, 13.2, 13.3a; the Equipment Rules (2023), Part 2 (clubs) and Part 4 (the ball); the USGA Stimpmeter instructions for the green's speed; deviations: Definition "Hole": the opening is a regular 24-sided polygon inscribed in the 0.108 m circle (flats 0.5 mm inside it, never wider than the official hole) with rigid vertical walls (the liner is only drawn), because the simulator has no cylindrical cavity · Rule 13.2: there is no flagstick (as when the player has it removed) · Rule 10.1 and the Equipment Rules on the grip: the hand is a two-finger gripper, Unitree's Dex1-1 (90 mm stroke, 80 mm jaws, at most 120 N), on the right wrist; the grip lies across its jaws, at right angles to the forearm (as a fist holds a hammer), and the putter is held by their friction alone; "in the hand" is defined by contact: the grip touches both jaws, and a break of up to 0.05 s is not a release. The stroke is made with that hand (a one-handed stroke is legal); the left hand may hold the grip too. The club itself is not scaled to the 1.32 m robot · Rule 10.1b (anchoring): the club may touch nothing of the player but the hands (stricter than the Rule, which allows the club against a forearm) · the start: the club is not level at your right side but hangs from your right hand held out ahead (a two-finger gripper cannot carry a level putter across its jaws: it turns in them under its own weight); one hand, not two: on this model the robot cannot put both hands on the grip at the address · Rule 10.1a (a fair strike; an accidental double hit is one stroke): the referee needs numbers: every contact of the head with the ball must fall within 0.2 s of the first, and the contacts together may last at most 0.03 s (the simulated impact of a clean putt lasts 0.012 s, a real one 0.0005 s: the ball's contact is softer than a real ball's so that the simulator's 1 ms step resolves it) · Rules 9.4, 11.1 and 3.3 (penalty strokes, replaying, counting strokes): a single attempt: anything that would cost a penalty or need a second stroke ends it as a failure · Rule 13.3a (waiting for a ball that overhangs the hole): a ball that has been at rest for 1.0 s is final · the green: perfectly flat and uniform, no grain, no wind; its speed (stimp 10) is the ball's rolling resistance, calibrated so that a ball rolling at 1.83 m/s stops after 3.05 m |
| Stages | stroke → holed |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 3000 control steps (30 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
