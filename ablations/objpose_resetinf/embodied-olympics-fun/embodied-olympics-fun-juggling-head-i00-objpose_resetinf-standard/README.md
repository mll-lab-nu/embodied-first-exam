# embodied-olympics-fun-juggling-head-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-juggling-head-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `juggling_head` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (after each touch the ball reset to 3.5 m/s up over the head: ten headers); a two-wheel football machine 1 m in front lobs the ball (exit 4.8 m/s, 76 deg) onto the top of the head, 3.5 m/s down and 1.1 m/s towards the robot; a real controller (a squat timed to the ball) makes the first header, 3.55 to 3.45 m/s (0.97, the bar is 0.95); negatives: nop (one passive bounce at 0.85, then the ground), a still head, weak touches, carried, hand, chest, shoulder, nine then the ground, touching the machine before the feed, the ball onto the machine, out of the grid, a fall; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Juggle the football on your head: a ball machine in front of you lobs it onto your head; keep it in the air with ten headers in a row, touching it with nothing but your head, without it touching the ground. (Embodied Olympics `juggling-head`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Every header must give the falling 0.43 kg ball back more speed than a still head would, so the head has to meet it moving up at the right moment, ten times in a row; the first one must also take out the lob's drift towards the robot, and the head is round and only about 15 cm across, so a contact one centimetre off its top sends the ball sideways at about 0.3 m/s and a few centimetres off it out of reach, all while the robot keeps its balance. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-juggling-head-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: You stand in the middle of a square grid 4.572 m on a side (5 yards; cones at its corners) on level grass. A size-5 football (0.22 m across, 0.43 kg, in air) waits in a ball machine that stands on the grass 1.0 m in front of you; at 1.0 s its gate opens and the machine lobs the ball up and onto your head. Until the ball has left the machine, touching the ball or the machine fails. From then on, a touch is a contact of the ball with your head (contacts less than 0.05 s apart are one touch). A touch is a header that counts when the ball's centre has then risen at least 0.22 m above the height it had when the touch began, before anything touches it again, and when the ball left the touch with at least 0.95 of the speed it had just before it (both taken at the height where the touch began): the head must strike the ball, a ball that only bounces on a still head leaves slower; such a touch is not counted, and is not a fault. This holds for the first touch too. You succeed at the moment the 10th header counts. You fail if the ball touches the ground or the ball machine, if any part of you other than the head touches it (the shoulders, the chest, an arm, a hand, a leg), if one touch lasts longer than 0.05 s (the ball resting or balanced on the head), if the ball is touched again before it has risen 0.22 m, if a foot steps out of the grid (a foot's ankle joint beyond its edge), if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 60 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Category | football-and-volleyball |
| Rule book | Ontario Soccer Association, Technical Benchmark Exercises (2015, for U12-U13 players), exercise 1 'Head Juggling': one attempt, the player in a 5 x 5 yard grid keeps the ball up with the head, each head juggle one point, the count stopped by the ball touching the ground, by another body part, or by stepping out of the grid; the benchmark records the count and sets no pass mark, so the family's standard is 10 consecutive headers (the same standard as the family 'juggling'). IFAB Laws of the Game 2025/26 for the ball (Law 2: size 5, 68-70 cm round, 410-450 g); deviations: The start: in the benchmark the ball starts in the player's hands and the player throws it up onto the head; the robot has fists and no fingers, so a two-wheel football machine standing on the grass 1.0 m in front of the robot lobs it instead, the same in every attempt: its gate opens at 1.0 s, a ram pushes the ball into the wheels and it leaves them about 0.28 s later, rises steeply and comes down on the head at about 3.5 m/s, still moving towards the robot at about 1.1 m/s (a toss from a coach a metre away arrives the same way). Until the ball has left the machine, neither the ball nor the machine may be touched; afterwards the machine is part of the grid's furniture, and a ball that touches it ends the count. · A counter's eye is replaced by numbers: contacts less than 0.05 s apart are one touch, a touch may last at most 0.05 s, and the ball's centre must then rise at least 0.22 m (one ball diameter) above where it was when the touch began, before anything touches it again. The limit on a touch's length is twice a measured human header's (about 25 ms: Bayly et al., IEEE EMBS 2002, the same subjects as Naunheim et al., Med Sci Sports Exerc 35:1406-1412, 2003; a size-5 ball's contact with the robot's head lasts about 11 ms), so that a ball cushioned on the head and pushed up is not a header. · The ball bounces off the robot's hard head shell as off a hard floor (the ball's own restitution from the rule book's drop test; a still head held by its motors returns about 0.83 of the speed). A human head and neck are softer: the heading model of Naunheim et al. (2003) takes a restitution of 0.4 to 0.7, but no measurement of the ball on a live head was found, and the robot's head is not a human's; the simulation keeps the robot's own contact, so a robot header needs less head speed than a human one. · A header is a strike: so that a ball that merely bounces on a still head (it returns about 0.8 of its speed, each bounce lower) is not head juggling, a touch counts only if the ball leaves it with at least 0.95 of the speed it arrived with; the first touch too, because the ball is fed, not thrown up by the robot. A touch that does not is not counted and is not a fault. · The head: the G1's head is the upper hull of its torso link (the part 'head'); any other part of the robot touching the ball (the shoulders, the chest, an arm) is another body part. · Stepping out of the grid is judged by the feet: a foot's ankle joint beyond the grid's edge. No wind. |
| Stages | header 1 → header 2 → header 3 → header 4 → header 5 → header 6 → header 7 → header 8 → header 9 → header 10 |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
