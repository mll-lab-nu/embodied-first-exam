# embodied-olympics-fun-free-kick-wall-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-free-kick-wall-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `free_kick_wall` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by a real kick (a standing power kick through lowcmd: 14.8 m/s off the foot, in at the near post); a fall after the kick does not fail; but only 8 of 13 gain and ball-offset perturbations score (the ball rebounds off the wall into the fallen robot, or goes wide), below the 9 of 10 bar, so it is not shipped as a reference solution; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Take a direct free kick: with one kick of a foot, send the ball over or around the wall of mannequins into the official goal 20.0 m away. (Embodied Olympics `free-kick-wall`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The wall hides the near half of the goal: the ball has to be driven past or over its end along a narrow line, or round it into the far half, some 21 m, which needs well over 6 m/s off the foot (over the wall about 11 m/s). The robot has no kicking skill: Embodied Olympics' balanced model-based kick sends the ball off at about 4 m/s, and a swing hard enough (10 to 16 m/s measured) throws the 33 kg body round on its standing foot. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-free-kick-wall-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: A size-5 football (0.22 m across, 0.43 kg, in air) lies at rest on the grass in front of your right foot: its centre 0.32 m ahead of your pelvis and -0.13 m to your left (negative: to the right). The goal line is 20.0 m beyond the ball, square to the direction you face; the goal is 7.32 m wide between the posts and 2.44 m high under the crossbar (posts and bar 0.12 m thick), its centre 4.0 m to the left of the line straight ahead through the ball. A wall of 4 training mannequins stands between the ball and the goal, side by side, their faces 9.15 m from the ball, covering the near (right-hand) post (its outer edge 0.25 m outside the line from the ball to that post's inner edge): each 1.75 m tall and 0.5 m wide, 3.0 kg, standing free on a 13.0 kg rubber base (0.5 m wide, 0.4 m deep, 0.05 m high), so that a ball can knock one over. There is no goalkeeper. The kick is a contact of a foot of yours with the ball: the foot below the ankle, or your lower leg where it lies over the foot and no more than 0.12 m above the ankle joint; every such contact within 0.15 s of the first belongs to the one kick. You succeed at the moment the whole ball is over the goal line between the posts and under the bar; it may touch the mannequins, the posts, the bar and the ground on the way. You fail if any other part of you touches the ball at any time, if a foot touches the ball again later than 0.15 s after the first contact (a second touch), if the ball is not moving towards the goal line at the end of the kick, if the whole ball crosses the goal line outside the goal, if after the kick the ball has been slower than 0.1 m/s for 1.0 s, if you fall before the kick (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 30 s. A fall after the kick does not end the attempt (the Laws judge the ball once it is in play, not the kicker; the setting fall_after_kick_fails = 0, where 1 would make any fall a failure). No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m, posts and crossbar 12 cm wide; the penalty area 16.5 m deep), Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 10 (a goal: the whole ball passes over the goal line between the posts and under the crossbar), Law 13 (free kicks: a direct free kick, the ball stationary, in play when it is kicked and clearly moves; the kicker may not touch it again until it has touched another player; all opponents at least 9.15 m from the ball until it is in play) and the glossary (a kick: contact with the foot and/or the ankle); deviations: Law 13 (the opponents): the defensive wall is 4 free-standing training mannequins (FORZA senior free-kick mannequin size: 1.75 m tall, 0.5 m wide) on FORZA's 13.0 kg rubber base, side by side with their faces 9.15 m from the ball, covering the near post. They are free bodies standing on the grass (rubber on grass, friction 0.8: an estimate): a ball that hits one can rock, slide or topple it. They do not jump, and there is no goalkeeper and no other player: opponents cannot be simulated otherwise. · Law 13 (one kick): the referee takes every contact of a foot with the ball within 0.15 s of the first as the one kick; a later contact by the kicker is a second touch. A referee's eye is replaced by this number. · Glossary (a kick is made with the foot or the ankle): the foot is the robot's ankle-roll link; its lower-leg collision hull covers the instep and the ankle, so a contact with that hull counts as the foot where it lies over the foot (from 0.08 m behind to 0.15 m ahead of the ankle joint) and no more than 0.12 m above the ankle joint; higher up it is the shin, which may not touch the ball. · Law 1: only the attacked end of the field is there (the penalty area, the goal area and the arc painted); the goal's net is a rigid cage 2.0 m deep; no wind. The free kick's spot (20.0 m from the goal line, 4.0 m to the right of the goal's centre) is this benchmark's choice: outside the penalty area, where a direct free kick is taken, and inside the range of the robot's measured hard kicks (10 to 16 m/s; the ball has to roll or fly about 21 m). The kicker starts at the ball, without a run-up. |
| Stages | kick → goal |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 3000 control steps (30 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
