# roboolympics-hurdles-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-hurdles-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `hurdles` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_hurdles.py: positive by injection (the H1-2 given 2.0 m/s forward and 5.5 m/s up over each standing 1.067 m hurdle, a real walk to the line); negatives: knocked with a hand, arm or trunk, under the top, beside the hurdle, a leg beside it, left the lane, down. The H1-2's pelvis stands at 1.035 m and walks at 0.7 m/s (50 m alone is 71 s of the 140 s); nothing known lifts it over the bar; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Run the 50 m hurdles: go over all four hurdles in your lane, never beside one or under its top, and bring your torso to the finish line. (RoboOlympics `hurdles`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
A hurdle's top is higher than the robot's hip joints: each of the four has to be jumped or stepped over with the whole pelvis above 1.067 m and each foot lifted a metre, on a body of 67 kg whose only built-in gait walks at 0.7 m/s and drifts in heading. Walking alone takes half the time limit for the distance. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-hurdles-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: World Athletics rules for the hurdles, at the indoor distance of 50 m. The lane runs along +x, 1.22 m wide, centred on y = 0; the start line (0.05 m wide) has its far edge at x = 0, the finish line is x = 50.0 m. 4 hurdles stand across the lane, the first 13.72 m from the start line and one every 9.14 m after it (the last 8.86 m before the finish). A hurdle is 1.067 m high and 1.19 m wide with a top bar 0.07 m high; its two base feet, 0.7 m long, lie on the track on your side of it. It is hinged at the foot of its uprights and tips over forwards when a horizontal force of more than 3.8 kg pushes the middle of its top bar; let go before it has gone too far, it swings back. The clock starts at t = 0. You go over a hurdle when your pelvis and both your feet (the ankle joints) have crossed the plane of its top bar towards +x, each between the bar's two ends, the pelvis higher than the hurdle's top (1.067 m above the track) and each foot higher than the lower edge of its top bar (1.067 m less 0.07 m), whether the hurdle still stands or not; a pelvis or a foot that comes back over the plane has not crossed it and must cross it again. The hurdles are gone over in order. Knocking a hurdle down with your legs is allowed (a hurdle tipped more than 45.0 degrees is counted as down, without a fault). You finish at the moment the leading point of your torso (the trunk and head hull; not the arms, legs or feet) reaches the finish line, with all hurdles gone over. You succeed with a finish within 140 s of robot time. A fall does not end the race: you are down while your pelvis is below 0.4 m, you may get up and go on, but 10.0 s down in a row end it. You fail if your pelvis or a foot crosses the next hurdle's plane beside the hurdle, or lower than said above (going under its top); if a part of one of your legs is beside the next hurdle (beyond the bar's ends, within 0.1 m of its plane) lower than the hurdle's top; if a hurdle is tipped more than 10.0 degrees within 0.5 s of being touched, while it was not yet tipped that far, by a hand, an arm, your trunk or your pelvis (knocked by hand or body; only hurdles within 3 m of your pelvis are judged); if your pelvis is more than half the lane's width from y = 0; if your torso reaches the finish line before every hurdle is gone over; when down for 10.0 s; or after 140 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | track-and-jumps |
| Rule book | World Athletics Competition and Technical Rules, 2024 edition: TR 22 (22.1-22.3 distances and heights: the men's hurdle 1.067 m high, 13.72 m to the first, 9.14 m between; at the indoor distance of 50 m that is four hurdles and 8.86 m from the last to the finish; 22.4-22.5 the hurdle: 1.18 to 1.20 m wide, a top bar 70 mm high, a base at most 0.70 m long, at least 10 kg, a toppling force of 3.6 to 4.0 kg at the centre of the top bar's top edge; 22.6 each hurdle is gone over in the athlete's own lane; 22.6.1 a foot or leg beside the hurdle below the plane of its top; 22.6.2 knocking a hurdle down by hand or body; 22.7 knocking hurdles down otherwise is no offence), TR 17.3 (lanes), TR 18.2 and TR 19 (the finish); deviations: TR 16 (the start): no starter's commands, no blocks and no reaction time: the robot stands with the front ends of its feet 0.02 m behind the start line and the clock runs from t = 0 · TR 22.6 ('goes over each hurdle') is judged geometrically at the plane of the hurdle's top bar: the pelvis must pass above the height of the hurdle's top, each foot (its ankle joint) above the lower edge of the top bar (a foot that strikes the bar knocks the hurdle down, which is allowed; a foot below the bar goes under), all three between the bar's ends · TR 22.6.2 (knocking down or displacing a hurdle by hand, body or the upper side of the lead leg): intent and the side of the leg cannot be judged: a hurdle tipped more than 10.0 degrees within 0.5 s of a touch by a hand, an arm, the trunk or the pelvis is a failure; the legs may knock it down · TR 17.3 (lanes): the lane is judged by the pelvis (its centre more than half a lane width from the lane's centre line); TR 22.6.1 is judged on the centres of the legs' collision bodies within 0.1 m of the hurdle's plane · TR 17 (a fallen athlete): a robot whose pelvis is below 0.4 m is down; it may get up and go on, but 10.0 s down in a row end the race (did not finish) · TR 19 (photo finish): the time is the instant the leading point of the torso link's collision mesh reaches the finish line's plane, interpolated between 1 ms physics steps (the H1-2's trunk and head are one link, so its torso includes the head); no wind; the robot alone on a straight of three lanes · the hurdle touches only the robot (its hinge's stop is the ground), and tips forwards only, like RoboOlympics'; the distance is the indoor 50 m with its four hurdles, on an outdoor straight, not the 110 m; the time limit, 140 s, is this benchmark's (FAMILIES.md) |
| Stages | hurdle 1 → hurdle 2 → hurdle 3 → hurdle 4 → finish |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 14000 control steps (140 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
