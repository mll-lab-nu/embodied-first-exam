# roboolympics-shot-put-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-shot-put-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `shot_put` / seed 0 |
| Oracle | `full` — Reference: a standing put from a technique found offline by CMA-ES over whole-body key poses (RoboOlympics' method, search_technique.py): 8.1 m/s from 1.78 m, pushed (0.997), 8.20 m (the line is 6 m), then out of the rear half and standing. Open loop on the frozen start, not robust. Referee test: positive by injection; negatives: the shot lowered, taken behind the shoulders, a sling, the other hand, out early, toes on the board, outside the sector, short, a front-half exit The privileged twin's reference rows (608 control steps, success after 6.08 s) streamed through the client. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Put the shot that your right hand holds at your neck, from the shoulder with that hand alone, so that it lands inside the sector at least 6.0 m from the circle, then leave the circle from its rear half and stand. (RoboOlympics `shot-put`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The shot weighs 7.26 kg and the H1-2's arm motors give 40 N m at the shoulder and 18 N m at the elbow: the arm alone cannot push it fast, so the legs and the trunk have to drive the put, inside a circle two steps wide. 6.0 m needs a release near 7 m/s at about 40 degrees. The stance you start in is not in balance under the shot: held as it is in `stand` mode the robot topples forward within about 4.5 s, so the put (or a counter-lean) has to begin at once. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the client (`solution/rows.npz`, recorded by scripts/roboolympics/make_oracles.py). Reference: a standing put from a technique found offline by CMA-ES over whole-body key poses (RoboOlympics' method, search_technique.py): 8.1 m/s from 1.78 m, pushed (0.997), 8.20 m (the line is 6 m), then out of the rear half and standing. Open loop on the frozen start, not robust. Referee test: positive by injection; negatives: the shot lowered, taken behind the shoulders, a sling, the other hand, out early, toes on the board, outside the sector, short, a front-half exit The privileged twin's reference rows (608 control steps, success after 6.08 s) streamed through the client.

## Verification
The sim sidecar's referee judges the live attempt, then the service replays the recorded attempt in a fresh simulator;
`tests/grade.py` reads `/data/final.json`: pass iff the live run and the replay succeed and end in the same state. The
rules: The men's shot (7.26 kg, 0.12 m across) starts gripped against your right palm beside your neck: you have taken your stance. The circle is 2.135 m across inside its rim; the ground outside is 0.02 m higher than its inside. At the front, a stop board 1.21 m long, 0.112 m wide and 0.1 m high follows the rim. The sector opens from the circle's centre, 34.92 degrees wide, symmetric about the direction you face at the start. The put (TR 33.1), judged on the shot's centre relative to your trunk (the line through your two shoulder joints, your trunk's up and forward directions) from the start to the release: the centre never lower than 0.0 m below the line of the shoulders and never more than 0.0 m behind it; nothing but your right hand and your trunk touches the shot; and when you let go (once: it cannot be gripped again) the shot must be moving away from your right shoulder joint with at least 0.5 of its speed relative to that joint (a push from the shoulder, not a throw or a sling). The shot's first touch of the ground must be inside the sector lines (on a line is out); the put is measured from that point to the inside of the rim along the line through the circle's centre. You succeed when a valid put measures at least 6.0 m and you have then left the circle correctly and stood for 1.0 s. Leaving correctly: after the shot has landed, your first touch of the rim's top or of the ground outside the circle is behind the line through the circle's centre across the putting direction (the rear half). Standing: only your feet on the ground, the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. You fail if any part of you touches the rim's top (its top inside edge included), the ground outside the circle or any part of the stop board other than its inner side (its top edge is not its inner side) before the shot has landed, or in the front half before you have left correctly; if the shot drops below or goes behind the line of the shoulders, is touched by anything but the right hand and the trunk, or is not pushed at the release; if it lands outside the sector or short of 6.0 m; if any part of you touches it after the release (your right arm and your trunk may still brush it during the first 0.2 s); if you fall (your pelvis lower than 0.5 m above the circle's floor, or any part of you other than your feet on the ground); or after 60 s. Where you touch the ground is judged on the points of contact; a contact within 0.003 m of the rim's top, or that far outside the stop board's inner side, counts as on the top. The neck line of the stance runs from 0.08 m above the middle of the shoulder line to the chin, 0.2 m above and 0.09 m in front of it; at the start the shot's centre is within 0.22 m of it.

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
| Category | throwing-catching-striking |
| Rule book | World Athletics Competition and Technical Rules 2024: TR 32.5-32.8 (the circle), TR 32.12 (the sector), TR 32.13, 32.14, 32.16, 32.17 and 32.20 (throwing events: the start, failures, the landing, leaving the circle, the measurement), TR 33.1 (the put from the shoulder), TR 33.2 (the stop board), TR 33.4-33.5 (the men's shot); deviations: TR 33.1 ("touch or be in close proximity to the neck or the chin"): the hand holds the shot by a grip switched on and off; the stance is given at the start (the shot against the palm beside the neck, its centre within 0.22 m of the line from the base of the neck to the chin). From then to the release the rule is judged on the shot's centre in the trunk's frame: "the hand shall not be dropped below this position" as not lower than 0.0 m below the line of the two shoulder joints, "not behind the line of the shoulders" as not more than 0.0 m behind that line, and "put" (not thrown or slung) as: at the release the shot moves away from the putting shoulder's joint with at least 0.5 of its speed relative to that joint. · TR 32.5-32.6: the ground outside the circle is level with the rim's top for 1 m and then falls to the field's level over 1 m (the circle's inside is the field's level, 0.02 m below the rim, instead of the field being level with the rim). · TR 32.20: the mark is the point where the shot first touches the ground, not the nearest edge of its dent. · TR 32.15 (interrupting a trial, laying the implement down): not modelled; the first release is the put, and the shot cannot be gripped again. · TR 32.14 names no fall: here a fall ends the trial as a failure, as in every task of this benchmark; the trial ends when the robot has left the circle correctly and stands. · TR 25.17 (one minute for a trial): the whole trial, leaving the circle included, has 60 s. · Flight: the shot's drag in still air (MuJoCo's ellipsoid fluid model, a quasi-steady model), no wind. · The qualifying mark of 6.0 m is this benchmark's (a school standard for the 7.26 kg shot); the rule book only measures. |
| Stages | release → landing → exit |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
