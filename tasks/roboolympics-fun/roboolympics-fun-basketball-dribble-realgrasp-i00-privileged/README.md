# roboolympics-fun-basketball-dribble-realgrasp-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | privileged |
| Twin | `roboolympics-fun-basketball-dribble-realgrasp-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `basketball_dribble_realgrasp` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_basketball_dribble_realgrasp.py: positive by injection (the palms really open before a foot lifts, a real 14 m walk in 20 s with 40 real floor bounces and palm touches; each push is the ball's velocity set at the real touch, since the palm absorbs the ball); negatives: walking with the held ball, held ball on the floor / against the chest, resting on the palm, a double touch, caught in both palms again, a leg touch, thrown ahead, walked away from, out of bounds (ball, robot), dribbling on the spot, a fall; nop holds 60 s; the hold slips without the squeeze (0.06 s) or with one palm (0.12 s). A real palm push was not attempted; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Dribble the basketball, which starts pressed between your two palms, from the end line across the centre line, 14 m up the court, one palm at a time, without a dribbling or a travelling violation. (RoboOlympics `basketball-dribble-realgrasp`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The ball keeps 85 % of its speed in a bounce but a palm absorbs it, so every touch has to push it down and forward again by the hand's own motion to where the hand will be, with a rigid palm 8 cm wide, for 14 m, on a body whose walking gait covers about 0.7 m/s, drifts in heading, and is disturbed by every push of the arm. The built-in walking gait steps on the spot even at a zero command, so the ball has to leave the palms before it starts.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (the palms really open before a foot lifts, a real 14 m walk in 20 s with 40 real floor bounces and palm touches; each push is the ball's velocity set at the real touch, since the palm absorbs the ball); negatives: walking with the held ball, held ball on the floor / against the chest, resting on the palm, a double touch, caught in both palms again, a leg touch, thrown ahead, walked away from, out of bounds (ball, robot), dribbling on the spot, a fall; nop holds 60 s; the hold slips without the squeeze (0.06 s) or with one palm (0.12 s). A real palm push was not attempted.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: A FIBA court, 28.0 m by 15.0 m inside its boundary lines (lines 0.05 m wide); the centre line's axis is 14.0 m from the end line. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor). Your hands have no fingers and no grip: the ball starts pressed between your two flat palms, and only the force of your arms and friction hold it; it can slip out. A hand is the palm pad and the wrist; a hand is on the ball while it touches the ball, gaps shorter than 0.03 s included; the ball is in your hands while at least one hand is on it, and it has left them once no hand has been on it for 0.03 s. You stand still. Starting the dribble: the first foot you lift makes the other your pivot foot; the pivot foot, and before a foot is lifted either foot, may not slide more than 0.2 m along the floor, and the pivot foot may not leave the floor before the ball has left your hands (a foot has left the floor when it has not touched it for 0.03 s). While the ball is in your hands it may touch no part of you but your hands, and it may not touch the floor. The ball leaving your hands (pushed, dropped or slipped) is the first touch of your dribble. The dribble: after that you play the ball with one hand at a time, by touches that push it to the floor (thrown, tapped, rolled or bounced): between two touches by your hands the ball must have touched the floor; contacts of a hand less than 0.03 s apart are one touch. There is no limit to your steps while the ball is not in a hand. You succeed at the first moment the ball touches the floor in the frontcourt (beyond the centre line's far edge, 14.0 m plus half a line width from the end line) with both your feet in the frontcourt (every point where each foot last touched the floor is beyond that edge), after at least one touch of your dribble after the ball left your hands. You fail if you travel at the start; if the ball touches the floor or a part of you other than a hand while it is in your hands; if, after it has left your hands, a hand's touch lasts longer than 0.3 s (the ball has come to rest in the hand); if both hands touch the ball at the same time; if a hand touches the ball twice without the ball having touched the floor in between; if the ball touches any part of you other than a hand; if the ball's centre is ever more than 2.0 m (horizontally) from your pelvis after it left your hands; if the ball or any part of you touches the floor on or outside a boundary line (out of bounds); if you fall (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 60 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | basketball-and-rackets |
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (size-7 ball), Art. 13 (how the ball is played), Art. 14 (control: a player holds a live ball), Art. 23 (out of bounds), Art. 24 (dribbling), Art. 25 (travelling), Art. 28.1.3 (when a dribbled ball is in the frontcourt); deviations: Art. 3 (equipment): the hands are flat rubber palm pads without fingers; the ball is held only by pressing it between the two palms (friction), and it slips or drops when the arms do not press hard enough. It is dribbled by pushing it with a palm; it has left your hands when no hand has been on it for 0.03 s. · Art. 3 (equipment, the hand): the palm is modelled as the soft part of a hand: it absorbs the ball (a ball thrown at a still palm keeps 0.12 of its speed) instead of bouncing it like the floor (0.85); with the ball's own floor rebound on the palms a squeezed ball rattles out of them within about a second. A dribbling hand therefore gives the ball its speed by its own motion. The floor keeps the ball's rule-book rebound. · Art. 24.1.2 (the ball 'comes to rest' in a hand) is read as: a hand's touch of the ball that lasts longer than 0.3 s. A dribble that has ended cannot legally be started again (Art. 24.2), so a ball that comes to rest in a hand, or is touched by both hands at once, ends the attempt. · Art. 13: every touch of the ball by a part of you other than a hand is a violation, also while the ball is held at the start (no ball held against the chest or between the forearms); intent (an accidental touch of a leg is legal in the rule book) cannot be judged. · Art. 14 / 24 give no distance for 'control' of a dribbled ball: here the ball's centre must stay within 2.0 m (horizontally) of your pelvis, so that a ball thrown ahead and walked after is not a dribble. · Art. 28 (eight seconds to reach the frontcourt) is not applied: the attempt lasts at most 60 s of robot time. |
| Stages | dribble → past the free-throw line → in the frontcourt |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `c28c2956096d62c2253dfd0468b260de5fde1d138606ce967cb95d504b7a958a` |
| Episode | 6000 control steps (60 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/roboolympics-fun-files/, built from embodied_first_exam/roboolympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
