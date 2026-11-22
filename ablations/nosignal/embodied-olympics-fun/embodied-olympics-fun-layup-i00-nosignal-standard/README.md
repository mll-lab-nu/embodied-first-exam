# embodied-olympics-fun-layup-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-layup-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `layup` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: No reference solution; the referee is tested with the H1-2's own Inspire hands at the core's default forces (20 N per fingertip, 30 N the thumb; no extra factor; nothing welded). Start: the ball resting on the upturned right hand, the left hand on its side; nop: time, no step counted. Positive by a declared injection: the robot really takes two steps on its walking gait with the ball in its hands (two real touchdowns), is teleported with the ball so that the ball is 0.9 m from the ring's axis and given a 2.6 m/s take-off (a ghost jump); at the apex both hands really open and move off the ball (the release in the air judged by contact, 0.22 s after the take-off), then the ball's velocity is set to a toss (6.8 m/s up, aimed down through the ring); its flight through the real ring is physics: success at 2.46 s, the ball at most 2.1 mm into the hands; the same state hash twice. Negatives: a third step, repeated hops (travelling), let go on the floor, let go in the air without a take-off, a jump shot from the start (too far), a toss wide of the ring (the floor), the ball back on the hand after the release, the ball up through the ring from below, a fall, a shuffle of the feet.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Make a layup: with the basketball held in your two hands take at most two steps towards the basket, jump, and let go of the ball in the air close to the ring so that it enters the basket from above. (Embodied Olympics `layup`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Two steps and a jump have to carry a 67 kg body almost two metres while the hands keep the ball through every footfall, and the release comes in the air, about a metre below a ring that is 0.21 m wider than the ball: the hands have to let it go with the speed of the arms' own push, since a hand does not bounce it. The robot has a walking gait and nothing that jumps or lands; the built-in walking gait steps on the spot even at a zero command, so while the ball is in your hands its steps are counted like any others. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-layup-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The official basket: a rigid ring of 0.45 m inner diameter (0.018 m metal), its top edge 3.05 m above the floor, its centre 0.375 m in front of a backboard 1.8 m wide and 1.05 m high whose lower edge is 2.9 m above the floor. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor); it flies in air (drag and spin lift). Your hands are five-finger hands, each closed by its grip value (0 open, 1 closed); they hold the ball only by contact and friction: it starts resting on your upturned right hand, the fingers curled a little round it, your left hand on its side, and it can slip or drop. A hand is the palm, the fingers, the thumb and the wrist; a hand is on the ball while it touches the ball, gaps shorter than 0.03 s included; the ball is in your hands while at least one hand is on it, and you let go of it at the last touch of a hand after which no hand has been on it for 0.03 s. While the ball is in your hands it may touch no part of you but your hands, and it may not touch the floor. Travelling: while the ball is in your hands you may take at most 2 steps. A step is a foot touching the floor after it has been off it for at least 0.03 s; both feet landing within 0.03 s of each other are one step; the same foot may not touch down twice in a row, and a foot on the floor may not slide more than 0.2 m from where it stood or was put down (a shuffle is travelling). After that no foot may touch the floor again until you have let go of the ball. The release: at the moment you let go you must be in the air: nothing of you has touched anything but the ball for at least 0.05 s, after a take-off at which your pelvis was moving upwards at 0.5 m/s or more; and the ball's centre must be within 1.25 m (horizontally) of the ring's centre, the radius of the no-charge semi-circle painted under the basket. You succeed when, after that release, the ball's centre goes down through the ring's plane inside the ring and on down to one ball diameter below it (off the backboard or not). You fail if you travel; if the ball touches the floor or a part of you other than a hand while it is in your hands; if you let go of the ball (on purpose or because it slipped) with something of you on the floor, without a take-off, or further from the ring; if any part of you touches the ball more than 0.05 s after you let go of it (no catching it again); if the ball touches the floor before it is through the ring; if the ball's centre comes up through the ring from below; if you fall before the ball is through (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 15 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court, no-charge semi-circle), Art. 3 and the Basketball Equipment appendix (backboard, ring, size-7 ball), Art. 13 (how the ball is played), Art. 14 (control: a player holds a live ball), Art. 16 (goal), Art. 25 (travelling); deviations: the player's hands: the H1-2's own Inspire five-finger hands (six drives each: four fingers, the thumb's flexion and rotation; fingertip forces 20 N, the thumb 30 N), each closed by one command; the ball is held in the two hands by contact and friction alone (nothing is welded) and can slip or drop; it is let go when no hand has been on it for 0.03 s. · Art. 3 (equipment, the hand): the palm is modelled as the soft part of a hand: it absorbs the ball (a ball thrown at a still palm keeps 0.12 of its speed) instead of bouncing it like the floor (0.85); with the ball's own rebound a ball on a palm rattles off it. The fingers' rubber pads absorb it too (critically damped); the floor, the ring and the backboard keep the ball's rule-book rebound. · Art. 13: while the ball is in your hands it may touch no part of you but the hands (no ball held against the chest or between the forearms); intent cannot be judged. · Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not slow the ball. A goal is judged at the ring: the ball's centre down through the ring's plane and on to one ball diameter below it. · Art. 25.2.1: you start standing with the ball in the hands and are judged as a player who has just ended a dribble while moving: two steps are allowed (a standing player would have a pivot foot instead), since no dribble precedes the layup here. After the two steps no foot may touch the floor again while the ball is held: pivoting after a stop is not offered. · The layup itself is not defined by the rule book: here it is a shot let go in the air (after a real take-off) with the ball inside the no-charge semi-circle's radius of the ring (1.25 m, Art. 2.4.7); a shot from further out or from the floor is not a layup. · One attempt, no opponent, no rebound, no dribble: the ball leaving the hands is the shot, and touching it after that ends the attempt. |
| Stages | approach → release in the air → through the ring |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1500 control steps (15 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
