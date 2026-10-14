# robofunolympics-basketball-dribble-i00-standard

| | |
|---|---|
| Benchmark | RoboFunOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `robofunolympics-basketball-dribble-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `basketball_dribble` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/robofunolympics/tests/test_basketball_dribble.py: positive by injection (a real 14 m walk in 20 s with 42 real floor bounces and palm touches; each push is the ball's velocity set at the real touch); negatives: dribbling on the spot, a carry, the ball more than 2 m away, out of bounds, a double touch, both hands, another body part, a fall. A real palm push was not attempted; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Dribble the basketball in your right hand from the end line across the centre line, 14 m up the court, without a dribbling or a travelling violation. (RoboFunOlympics `basketball-dribble`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The ball keeps 85 % of its speed in a bounce, so every touch has to push it down and forward again to where the hand will be, with a rigid palm 8 cm wide, for 14 m, on a body whose walking gait covers about 0.7 m/s, drifts in heading, and is disturbed by every push of the arm. The built-in walking gait steps on the spot even at a zero command, so while the ball is in your hand its steps are counted like any others. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `robofunolympics-basketball-dribble-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, then the service replays the recorded attempt in a fresh simulator;
`tests/grade.py` reads `/data/final.json`: pass iff the live run and the replay succeed and end in the same state. The
rules: A FIBA court, 28.0 m by 15.0 m inside its boundary lines (lines 0.05 m wide); the centre line's axis is 14.0 m from the end line. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor). It starts gripped in your right hand, and you stand still. Starting the dribble: the first foot you lift makes the other your pivot foot; the pivot foot, and before a foot is lifted either foot, may not slide more than 0.2 m along the floor, and the pivot foot may not leave the floor before you have let go of the ball (a foot has left the floor when it has not touched it for 0.03 s). The dribble: after the release you play the ball with one hand at a time, by touches that push it to the floor (thrown, tapped, rolled or bounced): between two touches by your hands the ball must have touched the floor; contacts of a hand less than 0.03 s apart are one touch; the release counts as the first touch (the releasing hand may stay on the ball for 0.03 s after the grip opens; the next touch by a hand needs a bounce on the floor first); no grip takes the ball again. There is no limit to your steps while the ball is not in a hand. You succeed at the first moment the ball touches the floor in the frontcourt (beyond the centre line's far edge, 14.0 m plus half a line width from the end line) with both your feet in the frontcourt (every point where each foot last touched the floor is beyond that edge), after at least one touch of your dribble. You fail if you travel at the start; if a hand's touch lasts longer than 0.3 s (the ball has come to rest in the hand); if both hands touch the ball at the same time; if a hand touches the ball twice without the ball having touched the floor in between; if the ball touches any part of you other than a hand; if the ball's centre is ever more than 2.0 m (horizontally) from your pelvis after the release; if the ball or any part of you touches the floor on or outside a boundary line (out of bounds); if you fall (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 60 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (size-7 ball), Art. 13 (how the ball is played), Art. 23 (out of bounds), Art. 24 (dribbling), Art. 25 (travelling), Art. 28.1.3 (when a dribbled ball is in the frontcourt); deviations: Art. 3 (equipment): the hand holds the ball by a grip switched on and off, not by fingers; the ball is released when the grip is switched off, and after that release no grip takes it again. · Art. 24.1.2 (the ball 'comes to rest' in a hand) is read as: a hand's touch of the ball that lasts longer than 0.3 s. A dribble that has ended cannot legally be started again (Art. 24.2), so a ball that comes to rest in a hand, or is touched by both hands at once, ends the attempt. · Art. 13: every touch of the ball by a part of you other than a hand is a violation; intent (an accidental touch of a leg is legal in the rule book) cannot be judged. · Art. 14 / 24 give no distance for 'control' of a dribbled ball: here the ball's centre must stay within 2.0 m (horizontally) of your pelvis, so that a ball thrown ahead and walked after is not a dribble. · Art. 28 (eight seconds to reach the frontcourt) is not applied: the attempt lasts at most 60 s of robot time. |
| Stages | dribble → past the free-throw line → in the frontcourt |
| Service | `environment/sim/server.py` (the RoboFunOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/robofunolympics.md) |
