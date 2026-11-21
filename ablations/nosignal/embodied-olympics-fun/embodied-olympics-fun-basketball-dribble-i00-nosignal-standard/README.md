# embodied-olympics-fun-basketball-dribble-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-basketball-dribble-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `basketball_dribble` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: No reference solution; the referee is tested with the H1-2's own Inspire hands at the core's default forces (20 N per fingertip, 30 N the thumb; no extra factor; nothing welded). Start: the ball resting on the upturned right hand, the left hand on its side; the start command holds it the whole minute (nop: time). Positive by a declared injection: the robot really opens both hands and moves them out to the sides so the ball falls out of them before a foot lifts, turns the right palm down at its side and really walks the 14 m (0.8 m/s, heading held by feedback) while the ball really bounces and really meets the right hand 53 times; injected: at the ball's first floor contact its velocity is set to rise to the palm, and at each real touch of the hand its velocity is set (4 m/s down, towards where the palm will be): success in 20.0 s, longest hand touch 0.01 s, the ball at most 4.9 mm into the hands; the same state hash twice. Negatives: walking with the held ball (travelling), a dropped ball walked away from, backwards over the end line, tossed up and caught on the same hand (two touches without the floor), a hand under the ball (carrying), the ball held 0.3 s against the palm-down hand (come to rest), up against the palm again without a bounce, a touch by the thigh, thrown 6 m ahead, thrown back over the end line, both hands on the ball at once, dribbling on the spot (time), a fall.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Dribble the basketball, which starts held in your two hands, from the end line across the centre line, 14 m up the court, one hand at a time, without a dribbling, carrying or travelling violation. (Embodied Olympics `basketball-dribble`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The ball keeps 85 % of its speed in a bounce but a hand absorbs it, so every touch has to push it down and forward again by the hand's own motion to where the hand will be, with a hand about 8 cm wide and a ball 24 cm across, for 14 m, on a body whose walking gait covers about 0.7 m/s, drifts in heading, and is disturbed by every push of the arm. The built-in walking gait steps on the spot even at a zero command, so the ball has to leave the hands before it starts. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-basketball-dribble-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: A FIBA court, 28.0 m by 15.0 m inside its boundary lines (lines 0.05 m wide); the centre line's axis is 14.0 m from the end line. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor). Your hands are five-finger hands, each closed by its grip value (0 open, 1 closed); they hold the ball only by contact and friction: it starts resting on your upturned right hand, the fingers curled a little round it, your left hand on its side, and it can slip or drop. A hand is the palm, the fingers, the thumb and the wrist; a hand is on the ball while it touches the ball, gaps shorter than 0.03 s included; the ball is in your hands while at least one hand is on it, and it has left them once no hand has been on it for 0.03 s. You stand still. Starting the dribble: the first foot you lift makes the other your pivot foot; the pivot foot, and before a foot is lifted either foot, may not slide more than 0.2 m along the floor, and the pivot foot may not leave the floor before the ball has left your hands (a foot has left the floor when it has not touched it for 0.03 s). While the ball is in your hands it may touch no part of you but your hands, and it may not touch the floor. The ball leaving your hands (pushed, dropped or slipped) is the first touch of your dribble. The dribble: after that you play the ball with one hand at a time, by touches that push it to the floor (thrown, tapped, rolled or bounced): between two touches by your hands the ball must have touched the floor; contacts of a hand less than 0.03 s apart are one touch. There is no limit to your steps while the ball is not in a hand. You succeed at the first moment the ball touches the floor in the frontcourt (beyond the centre line's far edge, 14.0 m plus half a line width from the end line) with both your feet in the frontcourt (every point where each foot last touched the floor is beyond that edge), after at least one touch of your dribble after the ball left your hands. You fail if you travel at the start; if the ball touches the floor or a part of you other than a hand while it is in your hands; if, after it has left your hands, a hand's touch lasts longer than 0.3 s (the ball has come to rest in the hand); if a hand carries the ball (it touches the ball from below, its lowest contact point on the ball lower than the ball's centre by more than 0.3 of the ball's radius, for longer than 0.1 s); if both hands touch the ball at the same time; if a hand touches the ball twice without the ball having touched the floor in between; if the ball touches any part of you other than a hand; if the ball's centre is ever more than 2.0 m (horizontally) from your pelvis after it left your hands; if the ball or any part of you touches the floor on or outside a boundary line (out of bounds); if you fall (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 60 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Category | basketball-and-rackets |
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (size-7 ball), Art. 13 (how the ball is played), Art. 14 (control: a player holds a live ball), Art. 23 (out of bounds), Art. 24 (dribbling), Art. 25 (travelling), Art. 28.1.3 (when a dribbled ball is in the frontcourt); deviations: the player's hands: the H1-2's own Inspire five-finger hands (six drives each: four fingers, the thumb's flexion and rotation; fingertip forces 20 N, the thumb 30 N), each closed by one command; the ball is held in the two hands by contact and friction alone (nothing is welded) and can slip or drop; it has left your hands when no hand has been on it for 0.03 s. The fingers' rubber pads absorb the ball (critically damped), so a dribbling hand gives the ball its speed by its own motion; the floor keeps the ball's rule-book rebound. · Art. 24.1.3 (carrying the ball, a hand under it): judged by where a hand touches the ball: a touch from below (the hand's lowest contact point on the ball lower than the ball's centre by more than 0.3 of its radius) that lasts longer than 0.1 s carries the ball; a hand on top of it or on its side pushes it. · Art. 24.1.2 (the ball 'comes to rest' in a hand) is read as: a hand's touch of the ball that lasts longer than 0.3 s. A dribble that has ended cannot legally be started again (Art. 24.2), so a ball that comes to rest in a hand, or is touched by both hands at once, ends the attempt. · Art. 13: every touch of the ball by a part of you other than a hand is a violation, also while the ball is held at the start (no ball held against the chest or between the forearms); intent (an accidental touch of a leg is legal in the rule book) cannot be judged. · Art. 14 / 24 give no distance for 'control' of a dribbled ball: here the ball's centre must stay within 2.0 m (horizontally) of your pelvis, so that a ball thrown ahead and walked after is not a dribble. · Art. 28 (eight seconds to reach the frontcourt) is not applied: the attempt lasts at most 60 s of robot time. |
| Stages | dribble → past the free-throw line → in the frontcourt |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
