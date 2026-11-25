# embodied-olympics-fun-trap-ball-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-trap-ball-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `trap_ball` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (the robot teleported at t = 0 to stand in the real pass, which reaches its foot; the ball set to 0.3 m/s as it comes off the foot, under control 1.45 s after the touch); the pass is played by a football machine 15 m away (exit 9.6 m/s, -4 deg, 34 rad/s topspin), skids and hops, and arrives 1.97 s later at 5.9 m/s, 0.5 m to the right; negatives: a planted foot (the ball ends 4.3 m away or in an arm), rolling away, the first touch on the shin, a handball, too close to the machine, touching the machine; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Trap the pass: take the ball rolling past you with a foot and bring it to rest close to you within three seconds. (Embodied Olympics `trap-ball`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
A foot has to be in the way of a 6 m/s ball at the right hundredth of a second, half a metre to the side, and it has to take the pace off: a ball that hits a planted foot bounces a few metres away, far outside the metre, and the walking policy cannot catch a ball that is faster than it. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-trap-ball-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: A size-5 football (0.22 m across, 0.43 kg) waits in a ball machine 15.0 m ahead of you and 0.5 m to your right; about 3.2 s after the start the machine plays it along the ground at about 9.6 m/s, parallel to the way you face, so that it goes by 0.5 m to the right of where you stand. Your first touch must be with a foot or an ankle (the parts below the shin). After it you may play the ball as often as you like with any part of you except the hands and the arms. You succeed when, within 3.0 s of the first touch, the ball is under control: slower than 0.2 m/s for 0.5 s without a break, its centre all that time within 1.0 m of your pelvis (measured along the ground), you on your feet. You fail if the first part of you that the ball touches is not a foot or an ankle, if a hand or an arm touches the ball at any time (handball), if 3.0 s after the first touch the ball is not under control, if your pelvis comes within 9.15 m of the ball machine before the pass has left it, if you touch the machine or the waiting ball, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 10 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | IFAB Laws of the Game 2025/26: Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 12 (handball: the hand or the arm), Law 13 (9.15 m from the ball until it is in play) and the glossary (a kick is a contact with the foot or the ankle). Receiving a pass is a skill, not a rule-book event: the pass and the control standard (first touch with a foot, the ball at rest within 1 m inside 3 s) are the benchmark's; deviations: The pass is played by a two-wheel football machine standing on the grass 15.0 m away instead of a team-mate, the same in every attempt: its wheels drive the ball out 0.55 m above the grass, nearly level, at about 9.6 m/s with topspin (the two wheels give it at most about 35 rad/s, less than a rolling ball's): it skids and hops low along the grass and reaches the robot at about 6.0 m/s, as the family's former 8 m/s rolling pass did. The pitch is level and uniform (the official ball's rolling resistance, no bobble), no wind. · Law 13's distance is applied to the robot itself: until the pass is played it stays 9.15 m from the ball machine, so that the pass is played, not met at the machine. |
| Stages | first touch → control |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1000 control steps (10 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
