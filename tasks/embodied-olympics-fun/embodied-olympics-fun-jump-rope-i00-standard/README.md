# embodied-olympics-fun-jump-rope-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-jump-rope-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `jump_rope` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_jump_rope.py: positive by injection on the real rope (its state set turning at 1.5 rev/s, then turned by the robot's own arms through the Dex1 grippers; a 2 m/s take-off by hand): the rope really passes under both airborne feet at 6.8 m/s, 6-8 cm below the soles, one counted jump, the robot lands and stands 1 s; the full 17 with a hand-scripted rope loop and hand take-offs; negatives: a hop with the rope lying, a dropped handle, the rope beside the body, under one foot only, a to-and-fro swing, backwards, at the standing feet, stepping over, a one-footed take-off, several hops per turn (counted once), a hop forward over a still rope (also at y = 8 m with the heading turning in the air), a fall, a last jump that does not end standing. Arm circles alone (288 settings searched) keep the real rope turning for 1-5 turns and give at most 2 jumps with injected take-offs; no G1 controller hops repeatedly; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Skip rope: turn the rope forwards with both hands, over your head and under your feet, and jump it with both feet together, 17 times within one minute. (Embodied Olympics `jump-rope`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Every jump needs two skills at once. The arms must keep a light, floppy rope turning at a steady speed through grippers that hold it only by friction. The legs must make a two-footed hop, about 0.1 m high and timed to within a tenth of a second, to the rope coming under the feet. Then the robot must land and do it again 17 times without falling. Neither built-in gait can hop, and a rope that stops on a shin or a toe has to be started again from behind. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-jump-rope-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: You hold a skipping rope by its two handles, one in each of your two-finger grippers. Turn it forwards: over your head from back to front, then down in front of you and under your feet from front to back. A jump counts when the rope, after passing over your head, passes under both feet while nothing of you touches the floor, and your take-off was two-footed: both feet left the floor within 0.1 s of each other. The rope passes over your head when its point straight above your head crosses the upright plane through your head, from back to front, higher than the top of your head. It passes under a foot when its point at that foot's sideways position crosses the upright plane through that foot, across your heading, from front to back, lower than the bottom of the foot plus the rope's thickness, while it moves backwards over the floor at 1.0 m/s or more (the rope turning, not you hopping forwards over a still rope). It must pass under the second foot within 0.15 s of the first. Each turn of the rope counts at most once. Extra hops between turns are allowed but do not count. A miss does not end the attempt: if the rope stops on your body, passes under the feet while a foot or anything else of you touches the floor, passes under only one foot, turns backwards, or comes under your feet without first going over your head, that turn does not count, and the rope must go over your head again before the next jump. After your 17th counted jump you must land on your feet (the first thing of you to touch the floor) and then stand for 1.0 s without a break: only your feet on the floor, your torso within about 20 degrees of vertical, your pelvis slower than 0.35 m/s; then you succeed. You fail if you let go of a handle (a handle out of its gripper's jaws for more than 0.05 s, or a handle touching the floor), if the last landing is not on your feet, if you fall (your pelvis lower than 0.35 m, or any part of you other than your feet on the floor), or after 60 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (an RTX 4090 workstation, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | track-and-jumps |
| Rule book | The Chinese National Student Physical Fitness Standard (国家学生体质健康标准, 2014 revision, Ministry of Education 教体艺〔2014〕5号), one-minute rope skipping (1分钟跳绳): the rope turned forwards, a two-foot jump (正摇双脚跳); each turn of the rope round the body that passes under the feet counts one; a miss (the rope caught on the body) does not stop the clock, the skipper starts the rope again; the result is the count in one minute. The family's success line is the standard's pass mark (60 points) for first-grade boys: 17 jumps in one minute; deviations: Equipment: the standard names no rope. The rope here is a 7 ft (2.13 m between the swivels) beaded school rope, the length that skipping-rope sizing charts give a skipper shorter than 1.45 m (4 ft 9 in): 28 rigid segments of two 38 mm low-density polyethylene beads each (9.5 mm across, Kanga's deluxe beaded rope), 0.1 kg in all (a 7 ft segmented rope weighs 0.2 lb). Neighbouring segments are tied by stiff pivots that stretch by a few millimetres under load (the cord), and the rope feels the air's drag. Its two plastic handles are 0.15 m long and 0.04 kg each, with the rope on a swivel at their far ends. · Hands: the robot's hands are Unitree Dex1-1 two-finger grippers. Each handle is held between the jaws only by their friction, so it can slip out or be dropped. · Judging: a judge's eye is replaced by geometry, checked at every 1 ms physics step. The rope passes under a foot when its point at that foot's sideways position crosses, from front to back, the upright plane across the robot's heading through the foot, lower than the foot's lowest point (plus the rope's thickness). It passes over the head when its point at the head's sideways position crosses the upright plane through the head from back to front, higher than the top of the head. Three numbers the standard leaves to the judge's eye: the rope must move backwards at 1.0 m/s or more as it passes (a turning rope, not a hop over a still one), under the second foot within 0.15 s of the first, and both feet must leave the floor within 0.1 s of each other (a two-foot jump). · Timing: the minute runs from t = 0, with the robot standing, a handle in each gripper and the rope on the floor behind its heels. The attempt ends with success once the robot has landed on its feet after the 17th jump and stood still for 1.0 s (the families' land-and-stand rule), without waiting for the end of the minute. |
| Stages | jump 1 → jump 2 → jump 3 → jump 4 → jump 5 → jump 6 → jump 7 → jump 8 → jump 9 → jump 10 → jump 11 → jump 12 → jump 13 → jump 14 → jump 15 → jump 16 → jump 17 → stand |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
