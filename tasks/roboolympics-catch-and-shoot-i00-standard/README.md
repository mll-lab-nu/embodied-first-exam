# roboolympics-catch-and-shoot-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-catch-and-shoot-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `catch_and_shoot` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_catch_and_shoot.py: the catch is real (an open palm on the pass line takes the 7.2 m/s ball and the robot stays up); the shot is an injection (8.7 m/s at 52 degrees set at the release); negatives: not caught, touched before the pass, a leg, the pivot foot, a third step, touched again, the floor, from below, held, a fall; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Catch and shoot: catch the chest pass that comes to you from the left wing, then shoot from where you stand so that the ball enters the basket from above. (RoboOlympics `catch-and-shoot`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The pass arrives faster than the grip can take it: the hand has to be on the ball's path and moving with it. Then a 0.62 kg ball must leave that hand at about 9 m/s on a steep arc towards a ring 5.8 m away, from a body that may not take a step. The built-in walking gait steps on the spot even at a zero command, so while the ball is in your hand its steps are counted like any others. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-catch-and-shoot-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The official basket: a rigid ring of 0.45 m inner diameter (0.018 m metal), its top edge 3.05 m above the floor, its centre 0.375 m in front of a backboard 1.8 m wide and 1.05 m high whose lower edge is 2.9 m above the floor. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor); it flies in air (drag and spin lift). It is passed to you 2.0 s after the start: a chest pass of 8.0 m/s from 5.0 m away. In order: you catch the ball (a hand's grip takes it) before it has touched the floor; you let go of it (the shot); its centre goes down through the ring's plane inside the ring and on down to one ball diameter below it, which is the success. Travelling, from the catch to the shot's release: if both your feet are on the floor at the catch, the first foot you lift makes the other your pivot foot; the pivot foot, and before a foot is lifted either foot, may not slide more than 0.2 m along the floor (in the steps case below: any foot that is on the floor, from where it stood or was put down), and once it has left the floor no foot may touch the floor again before the ball has left your hand. If a foot is off the floor at the catch, you may take at most 2 steps (a step: a foot touching the floor after it has been off it for at least 0.03 s; both feet landing within 0.03 s of each other are one step; not the same foot twice in a row), and after them no foot may touch the floor again before the release. You fail if anything of you touches the ball before it is passed; if the passed ball touches the floor, or one of your legs or feet, before you have caught it; if you travel; if any part of you touches the ball more than 0.05 s after the shot's release (it cannot be gripped again); if the ball touches the floor before it is through the ring; if the ball's centre comes up through the ring from below; if you fall before the ball is through (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 15 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | basketball-and-rackets |
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (backboard, ring, size-7 ball), Art. 13 (how the ball is played), Art. 16 (goal), Art. 25 (travelling); deviations: Art. 3 (equipment): the hand holds the ball by a grip switched on and off, not by fingers: the grip takes the ball when its surface is within 3.5 cm of the palm and it moves at most 6 m/s relative to the hand; the ball is released when the grip is switched off. · Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not slow the ball. A goal is judged at the ring: the ball's centre down through the ring's plane and on to one ball diameter below it. · The pass is thrown by a machine, not a team-mate: always the same chest pass, at a fixed time. · Art. 13: a touch of the ball by a leg or a foot is always taken as deliberate (a violation); intent cannot be judged. · Art. 25.2.1: a ball caught with a foot off the floor is judged by the two-step rule without the pivoting it allows after a stop: after two steps no foot may touch the floor again while the ball is held. · One attempt, no opponent, no rebound: a pass that is not caught on the fly, and touching the ball after the shot's release, end the attempt. |
| Stages | catch → release → through the ring |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1500 control steps (15 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
