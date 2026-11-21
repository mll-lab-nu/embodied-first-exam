# embodied-olympics-fun-dunk-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-dunk-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `dunk` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: No reference solution in the task. An own-motor dunk from this start is shown by search (CMA-ES over joint targets on a lowcmd jump, then the walking policy for the landing, about 7,000 episodes): a deep squat, a jump with an arm swing (the pelvis 0.43 m above standing), the fingers half closed over the ball in the air, the ball's centre at most 2.53 m, carried into the ring by both hands 0.10 m from its axis, through at 2.74 s, standing at 4.79 s; rim and backboard contact 0.10 s; the energy is paid for by the actuators' work (+671 J against +605 J of mechanical energy in the take-off), feed-forward torque at most 100 N m, no weld. Plain open-loop jumps with the ball raised from the chest come no nearer than 0.24 m to the ring's axis above the rim. Positive by a declared magic action: the real open-hand hold and raise, a ghost jump (an upward force field on the robot's bodies for 0.35 s, the ball carried only by the hands), robot and ball teleported together over the ring at the apex, the ball going down through the real ring with both hands on it, the hands opening, an injected upright landing, a real stand; the same state hash twice; with the real landing it also stands. Negatives: nop (time, the ball still in the hands), a drop above the ring, a release over the rim, a one-hand entry, up through the ring from below, a miss after a release inside the ring, the ball on the floor, travelling (walking with the ball), hanging on the ring, a fall. The start squeeze holds an extra 0.8 g on the ball.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Dunk the basketball with both hands: holding it in your two hands, jump, force it down through the ring from above with both hands on it, and land on your feet. (Embodied Olympics `dunk`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
With both arms up and the ball held between the hands its centre is about 2.19 m above the floor; the ring is at 2.39 m, so the whole 67 kg body has to rise about 0.4 m (the ball's centre to about 2.53 m) while the hands keep the ball through the jump's accelerations, and the hands, wrists and forearms have to go into a ring only 0.21 m wider than the ball, then the robot has to come down on its feet. The robot has a walking gait and nothing that jumps or lands; the built-in walking gait steps on the spot even at a zero command, so while the ball is in your hands its steps are counted like any others. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-dunk-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The basket (official size, lowered): a rigid ring of 0.45 m inner diameter (0.018 m metal), its top edge 2.39 m above the floor, its centre 0.375 m in front of a backboard 1.8 m wide and 1.05 m high whose lower edge is 2.24 m above the floor. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor). Your hands are five-finger hands; the ball starts held between them, the palms pressed on its sides and the hands open, and only the hands' contact and friction hold it; it can slip out. A hand is on the ball while it touches the ball, gaps shorter than 0.03 s included (a hand is the palm, the fingers and the wrist); the ball is in your hands while at least one hand is on it. The ball must stay in your hands from the start until its centre has gone down into the ring: no dribble, no throw, no drop. The dunk: the ball's centre goes down through the ring's plane inside the ring while both hands are on the ball, and on down to one ball diameter below the ring (in the hands, or let go once its centre is inside the ring). The ball may not pass up through the ring first: a ball whose centre comes up through the ring from below is a violation. Travelling: while the ball is in your hands you may take at most 2 steps. A step is a foot touching the floor after it has been off it for at least 0.03 s; both feet landing within 0.03 s of each other are one step; the same foot may not touch down twice in a row; a foot on the floor may not slide more than 0.2 m from where it stood or was put down; after that no foot may touch the floor again until the ball is through the ring. Hanging on the ring: you may touch the basket (the ring, its plate, the backboard) with any part of you for at most 0.3 s in all. After the dunk let go of the ball (no hand on it) and stand: for 1.0 s without a break only your feet touch the ground, your torso is upright (the cosine of its tilt at least 0.94) and your pelvis moves slower than 0.35 m/s. Then you have succeeded. You fail if the ball leaves your hands before its centre has entered the ring; if the ball touches the floor before the dunk; if the ball goes through the ring after an entry at which not both hands were on it (a one-hand dunk, a tip, a shot or a drop); if, let go inside the ring, it touches the floor without having gone through; if the ball comes up through the ring from below; if you travel; if you hang on the ring; if you fall at any time (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 15 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (backboard, ring, size-7 ball), Art. 14 (control: a player holds a live ball), Art. 15 (a dunk: the ball forced downwards into the basket with one or both hands; here both), Art. 16 (goal; a ball that passes through the basket from below is a violation), Art. 25 (travelling), Art. 36 (technical foul: hanging on the ring); FIBA Mini-Basketball Rules (the ring at 2.60 m); deviations: Basketball Equipment (basket): the basket is lowered: the ring's top edge is 2.39 m above the floor, below FIBA Mini-Basketball's 2.60 m (FIBA's own ring: 3.05 m), set at the robot's measured own-motor reach (H1-2 with H2-class leg actuators), at the edge of the robot's reach; the full-size backboard keeps its size and its height relative to the ring (lower edge 2.24 m). The ball stays the size-7 ball. · Art. 3 (equipment, the hands): the hands are the H1-2's own Inspire five-finger hands (six drives: four fingers, the thumb's flexion and rotation), closed by one command per hand; the ball is held by the hands' contact and friction alone (the open palms pressed on its sides by the arms) and slips or drops when they do not hold it. · Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not slow the ball. The ball is through the basket when its centre has gone down through the ring's plane inside the ring and on to one ball diameter below it. · Art. 25.2.1: you start standing with the ball in the hands and are judged as a player who has just ended a dribble while moving: two steps are allowed (a standing player would have a pivot foot instead). After the two steps no foot may touch the floor again while the ball is held: pivoting after a stop is not offered. · Art. 24 (dribble): there is no dribble in this task; the ball stays in the hands from the start until the dunk, and a ball that touches the floor before the dunk ends the attempt. · Art. 36: hanging on the ring is judged by time: the robot may touch the basket (ring, its plate, the backboard) for at most 0.3 s in all. · The landing (on the feet, standing 1.0 s) is this task's own requirement; the rule book asks nothing of a player after a goal. |
| Stages | dunk → stand |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1500 control steps (15 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
