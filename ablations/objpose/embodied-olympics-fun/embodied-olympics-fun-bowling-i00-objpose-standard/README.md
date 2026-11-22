# embodied-olympics-fun-bowling-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-bowling-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `bowling` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (the 6 lb ball, held for real between the bare palms by friction only, with the palm contact of a supported human hand, rebound 0.10, taken from the hands and laid on the lane 0.35 m past the line at 8 m/s, 1.2 deg, entering 5 cm right of the head pin: a strike; entries 2-3 cm right give 8-9 pins); negatives: nop (held for the whole 40 s), arms opened (the ball drops), walking over the foul line, a gutter ball, a head-pin hit that is not a strike, touched after the release, a foul after the delivery, a fall. No controller delivers 4 m/s or more from a two-palm hold; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Bowl a strike: from behind the foul line, deliver the ball you hold pressed between your two palms down the lane so that all ten pins are knocked down. (Embodied Olympics `bowling`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
A strike needs the ball in the pocket beside the head pin, a few centimetres wide, after 18 m of lane on which it slides on the oil and grips on the dry boards; a 6 lb ball is deflected by the pins more than a heavy one, so it must also arrive fast. The 2.7 kg ball is held only by the squeeze of two fingerless palms, which the swing's speed and the ball's weight pull apart, both hands have to let go of it at the same moment without steering it off its line, and the body may not cross the foul line. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-bowling-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The lane is 1.0541 m wide and runs 18.288 m from the foul line to the head pin's spot, with a gutter 0.235 m wide and 0.047 m deep on each side; behind the foul line the approach, level with the lane, is 4.572 m long. Ten pins (0.381 m tall, 1.53 kg each) stand in the triangle of four rows, 0.3048 m apart, its point towards you. The ball (0.218 m across, 2.72 kg, no finger holes) starts pressed between your two palms. Your hands have no fingers and no grip: only the force of your arms and friction hold the ball, and it can slip out. Until the release the ball may touch no part of you but your hands (the palm pads and the wrists; either or both). The release: the ball has touched no part of you for 0.05 s (it is released at its last touch); after that no part of you may touch it again. The lane is oiled (friction 0.04) for the first 13.5 m in its middle, less far on its outside boards, and dry (friction 0.2) beyond. A delivery: the released ball crosses the foul line. It is a foul if any part of you touches the lane, a gutter or anything else on or beyond the foul line, at any time. Pins count only if the ball reaches them on the lane: a ball that touches a gutter before it has touched a pin knocks down nothing. A pin is down when it is tilted more than 20.0 degrees or is no longer on the lane's surface; the pins are counted 5.0 s after the ball first touches one. You succeed with a strike: all ten pins down. You fail on a foul; on a gutter ball; if fewer than ten pins are down at the count; if the ball touches a part of you other than a hand before the release; if any part of you touches the ball after the release; if you fall before the count (your pelvis lower than 0.5 m above the approach, or any part of you other than your feet on the approach or the floor); or after 40 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Category | throwing-catching-striking |
| Rule book | USBC Playing Rules 2024-2025 and USBC Equipment Specifications: the lane (60 ft from the foul line to the head pin, 41.5 in wide, gutters, pin deck), the pins (15 in, 3 lb 6 oz, 12 in apart), the ball (at most 8.595 in and 16 lb); the playing rules on a strike, a legal delivery, the foul (Rule 5) and legal and illegal pinfall. The rules do not say how the ball is held or with how many hands: a two-handed delivery is legal; deviations: Equipment (ball) and the hands: the hands are flat rubber palm pads without fingers and the ball has no finger holes (a uniform ball, no weight block). Nothing grips it: it is held only by pressing it between the palms (contact and friction), a two-handed hold, and it slips or drops when the arms do not press hard enough. It is released when it has touched no part of you for 0.05 s. · Equipment (the hand): the palm pads' contact with the ball is that of a ball on a human hand (a ball thrown at a still palm keeps 0.10 of its speed, as a volleyball dropped onto a supported, relaxed hand does: Ivanova, ISBS 2000; friction 0.7); the world has elliptic friction cones and an impedance ratio of 100 (MuJoCo settings that make a squeezed ball stay put; they apply to every contact, the lane's and the pins' too). The lane, the gutters and the pins keep their own contact parameters. · Equipment (pins): each pin is six stacked cylinders and capsules that follow the official profile, with the official mass, centre of gravity and the profile's moments of inertia. · Lane condition: Embodied Olympics' house pattern as friction zones (oil, friction 0.04, for 13.5 m in the middle of the lane and 3 m shorter on the outside boards; a 1.2 m transition; then dry boards, friction 0.2); the values are Embodied Olympics' assumptions after Frohlich (2004), not a measured lane. · Pinfall and the pin count: a pin is down when it is tilted more than 20.0 degrees or is off the lane's surface (Embodied Olympics' rule: a pin leaning on a wall counts as down); the count is taken 5.0 s after the ball first touches a pin. No pinsetter, no sweep; the pit is 0.1 m deep. · Rule 5: the foul is judged at any time, not only during or after the delivery; a fall also ends the attempt as a failure, as in every task of this benchmark. · One ball: the task is the first ball of a frame. |
| Stages | delivery → pins → strike |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 4000 control steps (40 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
