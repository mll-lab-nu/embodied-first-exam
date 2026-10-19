# embodied-olympics-fun-juggling-realgrasp-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-juggling-realgrasp-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `juggling_realgrasp` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_juggling_realgrasp.py: positive by injection after a real drop (the arms roll apart and the ball falls from between the palms; after it the ball is put over the head and each head touch sends it up at 2.6 m/s, one toe touch too); the start squeeze, about 6.6 N per palm, holds the ball 30 s (2.7 mm creep), without it the ball slips out at once; negatives: holding it, the ground, a weak squeeze, held against a forearm, pressed back between the palms (re-grip), a still head, low touches, a hand after the drop, the trunk, a ball resting on the robot; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Juggle the football: drop it from between your palms and keep it in the air for ten touches in a row with your feet, legs or head, without it touching the ground or a hand again. (Embodied Olympics `juggling-realgrasp`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Each touch is an upward strike by a leg or the head, timed to a falling 0.43 kg ball and aimed so that the ball comes down within reach again, ten times in a row; the robot has to stand on one leg to use a foot or a thigh, which neither built-in gait does, and a ball that merely bounces on a still limb loses a quarter of its height each time and wanders off. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-juggling-realgrasp-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: A size-5 football (0.22 m across, 0.43 kg, in air) starts pressed between your two open palms; your hands have no fingers and no grip (the grip columns of the action rows do nothing in this task): only the squeeze of your arms and friction hold the ball, and it slips out when they press too little. Until the drop only your hands (the palm pads and the wrists) may touch the ball. The drop: the ball has touched no part of you for 0.03 s; it is the end of the ball's last contact with a hand. A hand or an arm may still be in contact with the ball for 0.15 s after the drop (the ball leaving the hand); after that a hand or an arm on the ball is a handball. From the drop on, a touch is a contact of the ball with a foot, a shin, a thigh or your head (contacts less than 0.05 s apart are one touch); it counts when the ball's centre has then risen at least 0.22 m above the height it had when the touch began, before anything touches it again, and, for every touch after the first, when the ball leaves the touch with at least 0.95 of the speed it had when the touch began (both taken at the height where the touch began; a ball that only bounces on a still limb leaves slower: such a touch is not counted, and is not a fault). You succeed at the moment the tenth touch counts. You fail if the ball touches the ground (before the drop too), if a part of you other than the hands touches it before the drop, if a hand or an arm touches it later than 0.15 s after the drop, if your trunk (chest, shoulders, pelvis) touches it, if one touch lasts longer than 0.15 s (the ball resting or balanced on you), if the ball is touched again before it has risen 0.22 m, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground; standing on one foot is not a fall), or after 30 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | football-and-volleyball |
| Rule book | Keepie-uppie (ball juggling), the football skill: the ball is dropped from the hands and kept in the air with the feet, the legs and the head, each touch counted, the count ending when the ball touches the ground or a hand; it is a skill test, not an event of the Laws, and the family's standard is 10 consecutive touches. IFAB Laws of the Game 2025/26 for the ball (Law 2: size 5, 68-70 cm round, 410-450 g) and for handling (Law 12: the hand or the arm); deviations: A counter's eye is replaced by numbers: contacts less than 0.05 s apart are one touch, a touch may last at most 0.15 s, and it counts when the ball's centre has then risen at least 0.22 m (one ball diameter) above where it was when the touch began, before anything touches it again; a ball that rolls or rests on a leg is not a touch. · A touch is a strike: so that a ball that merely bounces on a still limb or head is not juggling, every touch after the first must send the ball off with at least 0.95 of the speed it arrived with (a still limb returns about 0.85); a touch that does not is not counted, and is not a fault. · Only the feet, the legs (shin and thigh) and the head count and may touch the ball; the chest and the shoulders, which a human juggler may use, are not allowed, because the robot's trunk is one rigid shell. · The ball starts pressed between the robot's two open palms in front of its hips (the robot has flat palm pads, no fingers and no grip): only the arms' squeeze and friction hold it, and it slips out when they press too little. The drop is the hands' own movement (the palms parting); a referee's eye for 'the ball has left the hand' is replaced by a number: the ball touches no part of the robot for 0.03 s, and the drop is the end of its last contact. Before the drop only the hands may touch the ball (a ball held against the body, an arm or a leg is not in the hand). The palm absorbs the ball as a hand does (the palm-ball contact of dunk-realgrasp: a ball thrown at a still palm keeps 0.12 of its speed); every other contact keeps the ball's rule-book rebound. No wind. |
| Stages | touch 1 → touch 2 → touch 3 → touch 4 → touch 5 → touch 6 → touch 7 → touch 8 → touch 9 → touch 10 |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 3000 control steps (30 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
