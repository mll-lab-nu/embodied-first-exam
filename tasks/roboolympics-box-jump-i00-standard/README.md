# roboolympics-box-jump-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-box-jump-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `box_jump` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_box_jump.py: positive by injection (1.6 m/s forward and 3.7 m/s up onto the 0.61 m box, a perfect landing, the stand is the robot's own); negatives: touching the box before the jump, landing on the floor, a leg tuck, a one-foot take-off, the box's side, not on the feet, the floor after the landing, a fall. The H1-2's open-loop squat jump leaves the ground at 1.8 m/s; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Jump from the floor onto the 0.61 m box in front of you with a two-foot take-off, land on its top with both feet, and stand up straight on it. (RoboOlympics `box-jump`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
No built-in action of this robot leaves the ground: the jump is whole-body joint control, and it must lift 67 kg far enough for the soles to clear 0.61 m, more than half the length of the legs. The landing has to be absorbed on a box only 0.51 m deep that is free to slide, and the robot must then straighten up on it. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-box-jump-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, then the service replays the recorded attempt in a fresh simulator;
`tests/grade.py` reads `/data/final.json`: pass iff the live run and the replay succeed and end in the same state. The
rules: The box is a free rigid body of 25.0 kg (not fixed to the floor; friction coefficient 1.0, a stiff wooden surface: contact time constant 0.005 s): 0.61 m high, its top 0.51 m long (along +x, the way you face) and 0.76 m wide. You must get onto it with one jump. Your jump is your first flight phase of at least 0.1 s (nothing of you touches anything). It counts only if: nothing of you touched the box before it (no stepping or climbing up); it left the floor from both feet (each foot was on the floor within the last 0.1 s before lift-off); it was a real take-off (your pelvis rose at least 0.1 m above its height at lift-off: tucking the legs while falling is not a jump). The landing is judged over the 0.5 s that follow the first contact: in that time only your feet may touch anything, and only the box's top face (each contact within 0.02 m of the top plane and pushing within 20.0 degrees of straight out of it: a foot against a side face or jammed on an edge is not on the top), and at its end both feet are on the top. Then you stand up straight on the box for 2.0 s without a break: both feet on the top face and nothing else touching anything, your torso within 20.0 degrees of vertical, your pelvis moving no faster than 0.35 m/s and at least 1.0 m above the box's top (hips and knees extended). You fail if the jump breaks one of these rules, if any part of you touches the floor after the landing, if a part other than a foot touches the box, if you fall before the jump (a fall is any part of you other than your feet touching the floor; there is no pelvis-height limit, a deep squat is not a fall), or after 20 s. You may walk on the floor before the jump. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | parkour-apparatus-balance |
| Rule book | CrossFit's box jump movement standard (the CrossFit Games Open workout descriptions: both feet start on the floor, both feet end on the box, hips and knees fully extended on top) on the men's prescribed box: 24 in (0.61 m) high, the 20 x 24 x 30 in plyometric box standing on its 20 x 30 in face; deviations: the step-up that some Open workouts permit is not a box jump here: the take-off is from both feet and there is a flight (the family is the jump, not the step-up) · full extension on top is judged by the pelvis' height above the box's top (1.0 m; this robot's pelvis is 1.04 m above its soles with straight legs, 1.02 to 1.03 m in its own standing posture, whose knees stay bent 0.36 rad, and below 1.0 m once the knees bend more than about 0.65 rad) and by the torso's tilt: a referee cannot see "open hips" on a robot otherwise · one repetition, judged to a held stand of 2.0 s on the box (a workout counts repetitions; here the repetition is one attempt and the stand shows control) |
| Stages | take-off → landing → stand |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 2000 control steps (20 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
