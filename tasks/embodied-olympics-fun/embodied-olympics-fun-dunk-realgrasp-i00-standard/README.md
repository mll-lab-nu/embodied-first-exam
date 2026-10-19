# embodied-olympics-fun-dunk-realgrasp-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-dunk-realgrasp-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `dunk_realgrasp` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_dunk_realgrasp.py: positive by injection (on the ring lowered to the FIBA Mini-Basketball 2.60 m with the start 0.75 m from it: a real two-palm squeeze raised overhead in stand mode, a ghost take-off at 2.70 m/s by an acceleration field on the robot only so the ball rides on palm friction, teleport over the ring at the apex, the squeezed ball really taken down through the ring with both palms on it and no rim contact; the landing is injected too); negatives: drop from above, let go over the rim, one hand at the entry, from below, missed after letting go inside, ball on the floor, a third step, hanging on the ring, a fall. nop holds the ball 15 s (about 20 N per palm, holds an extra 3.6 g) and fails by time. Overhead the ball's centre reaches 2.2 m; the ring is at 2.60 m; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Dunk the basketball with both hands: holding it pressed between your two palms, jump, force it down through the ring from above with both hands on it, and land on your feet. (Embodied Olympics `dunk-realgrasp`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
With both arms up and the ball pressed between the palms its centre is about 2.2 m above the floor; the ring is at 2.60 m, so the whole 67 kg body has to rise about half a metre while the arms keep squeezing the ball through the jump's accelerations, and the hands, wrists and forearms have to go into a ring only 0.21 m wider than the ball, then the robot has to come down on its feet. The robot has a walking gait and nothing that jumps or lands; the built-in walking gait steps on the spot even at a zero command, so while the ball is in your hands its steps are counted like any others. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-dunk-realgrasp-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The official basket: a rigid ring of 0.45 m inner diameter (0.018 m metal), its top edge 2.6 m above the floor, its centre 0.375 m in front of a backboard 1.8 m wide and 1.05 m high whose lower edge is 2.45 m above the floor. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor). Your hands have no fingers and no grip: the ball starts pressed between your two flat palms, and only the force of your arms and friction hold it; it can slip out. A hand is on the ball while it touches the ball, gaps shorter than 0.03 s included (a hand is the palm pad and the wrist); the ball is in your hands while at least one hand is on it. The ball must stay in your hands from the start until its centre has gone down into the ring: no dribble, no throw, no drop. The dunk: the ball's centre goes down through the ring's plane inside the ring while both hands are on the ball, and on down to one ball diameter below the ring (in the hands, or let go once its centre is inside the ring). The ball may not pass up through the ring first: a ball whose centre comes up through the ring from below is a violation. Travelling: while the ball is in your hands you may take at most 2 steps. A step is a foot touching the floor after it has been off it for at least 0.03 s; both feet landing within 0.03 s of each other are one step; the same foot may not touch down twice in a row; a foot on the floor may not slide more than 0.2 m from where it stood or was put down; after that no foot may touch the floor again until the ball is through the ring. Hanging on the ring: you may touch the basket (the ring, its plate, the backboard) with any part of you for at most 0.3 s in all. After the dunk let go of the ball (no hand on it) and stand: for 1.0 s without a break only your feet touch the ground, your torso is upright (the cosine of its tilt at least 0.94) and your pelvis moves slower than 0.35 m/s. Then you have succeeded. You fail if the ball leaves your hands before its centre has entered the ring; if the ball touches the floor before the dunk; if the ball goes through the ring after an entry at which not both hands were on it (a one-hand dunk, a tip, a shot or a drop); if, let go inside the ring, it touches the floor without having gone through; if the ball comes up through the ring from below; if you travel; if you hang on the ring; if you fall at any time (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 15 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (4090-ws1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | basketball-and-rackets |
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (backboard, ring, size-7 ball), Art. 14 (control: a player holds a live ball), Art. 15 (a dunk: the ball forced downwards into the basket with one or both hands; here both), Art. 16 (goal; a ball that passes through the basket from below is a violation), Art. 25 (travelling), Art. 36 (technical foul: hanging on the ring); FIBA Mini-Basketball Rules (the ring at 2.60 m); deviations: Basketball Equipment (basket): the basket is lowered by 0.45 m: the ring's top edge is 2.6 m above the floor, the ring height of FIBA Mini-Basketball, and the full-size backboard keeps its size and its height relative to the ring (lower edge 2.45 m). The ball stays the size-7 ball. With the official ring at 3.05 m no H1-2 jump was found that gets the squeezed ball over the ring. · Art. 3 (equipment): the hands are flat rubber palm pads without fingers; the ball is held only by pressing it between the two palms (friction), and it slips or drops when the arms do not press hard enough. · Art. 3 (equipment, the hand): the palm is modelled as the soft part of a hand: it absorbs the ball (a ball thrown at a still palm keeps 0.12 of its speed) instead of bouncing it like the floor (0.85); with the ball's own floor rebound on the palms a squeezed ball rattles out of them within about a second. The floor, the ring and the backboard keep the ball's rule-book rebound. · Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not slow the ball. The ball is through the basket when its centre has gone down through the ring's plane inside the ring and on to one ball diameter below it. · Art. 25.2.1: you start standing with the ball in the hands and are judged as a player who has just ended a dribble while moving: two steps are allowed (a standing player would have a pivot foot instead). After the two steps no foot may touch the floor again while the ball is held: pivoting after a stop is not offered. · Art. 24 (dribble): there is no dribble in this task; the ball stays in the hands from the start until the dunk, and a ball that touches the floor before the dunk ends the attempt. · Art. 36: hanging on the ring is judged by time: the robot may touch the basket (ring, its plate, the backboard) for at most 0.3 s in all. · The landing (on the feet, standing 1.0 s) is this task's own requirement; the rule book asks nothing of a player after a goal. |
| Stages | dunk → stand |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1500 control steps (15 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
