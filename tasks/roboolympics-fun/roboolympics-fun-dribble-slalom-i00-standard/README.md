# roboolympics-fun-dribble-slalom-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-fun-dribble-slalom-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `dribble_slalom` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_dribble_slalom.py: positive by injection (the robot really walks the whole course in 54 s, the ball escorted 0.45 m ahead of it); negatives: the ball or the robot on the wrong side, straight back instead of weaving, the ball more than 2 m away, a cone touched, a handball. A walking kick gives the ball about 2 m/s: kick-and-chase inside the 2 m limit was not attempted; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Dribble the football through the slalom: out through the six cones, round the last one and back through them over the start line, keeping the ball within 2 m and touching no cone. (RoboOlympics `dribble-slalom`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
About 30 m of path with a tight turn in 90 s leaves little slack for a robot that walks at 0.6 m/s, and its running policy does not know the ball. Every step that meets the ball kicks it, a 0.43 kg ball kicked at walking speed rolls metres, and it has to be steered through gaps of 2 m without the feet or the ball touching a cone. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-fun-dribble-slalom-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: A size-5 football (0.22 m across, 0.43 kg) lies 0.5 m ahead of you, behind the start line, which is 1.0 m ahead of you and square to the way you face. Six cones (0.3 m high, base radius 0.11 m, free-standing) stand on the line you face along, the first 2.0 m beyond the start line and then every 2.0 m. Each cone has a plane through it, square to the course. On the way out the ball's centre and your pelvis must each cross the plane of cone 1 to its left (your left at the start), of cone 2 to its right, and so on in turn, cone 6 to its right; then round cone 6 and back: the plane of cone 6 to its other side (the left as seen from the start), of cone 5 to the right as seen from the start, and so on in turn, cone 1 to the right as seen from the start; and finally back over the start line, the whole ball and your pelvis. For each plane the first crossing in the direction of travel after the plane before it decides, for the ball and for you separately. You succeed when the whole ball and your pelvis are back over the start line after all twelve planes. You fail if the ball or you cross a plane on the wrong side, if the ball's centre is ever more than 2.0 m from your pelvis (measured along the ground), if you or the ball touch a cone, if a hand or an arm touches the ball (handball; any other part of you may play it), if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 90 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | football-and-volleyball |
| Rule book | The slalom dribble of football skill tests (a line of cones, out through them, round the last and back through them, against the clock); it is a drill, not an event of the Laws: the course is six cones 2 m apart with 90 s allowed. IFAB Laws of the Game 2025/26 for the ball (Law 2: size 5, 68-70 cm round, 410-450 g) and for handling (Law 12: the hand or the arm); deviations: The line the ball and the player must weave is made exact: the ball's centre and the robot's pelvis must each pass every cone on the prescribed side, judged where they cross the line through that cone square to the course; a tester's eye is replaced by these planes. · The pitch is level and uniform (the official ball's rolling resistance), no wind. |
| Stages | out 1 → out 2 → out 3 → out 4 → out 5 → out 6 → back 6 → back 5 → back 4 → back 3 → back 2 → back 1 → finish |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 9000 control steps (90 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
