# embodied-olympics-fun-discus-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-discus-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `discus` / seed 0 |
| Oracle | `full` — Reference: a standing throw by the trunk's turn from a technique found offline by CMA-ES over whole-body key poses (Embodied Olympics' method): 12.9 m/s from 1.82 m, 15.87 m (the line is 15 m), then out of the rear half and standing. Open loop on the frozen start, not robust. Referee test negatives: walking out with it, out early, outside the sector, short, touched after the release, a front-half exit The privileged twin's reference rows (848 control steps, success after 8.48 s) streamed through the client. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Throw the discus in your right hand from inside the circle so that it lands inside the sector at least 15.0 m from the circle, then leave the circle from its rear half and stand. (Embodied Olympics `discus`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
15.0 m needs a release at about 12 m/s near 35 to 40 degrees with the discus flat to its flight and spinning, or the air turns it over. The H1-2's arm motors give 40 N m at the shoulder, so the speed has to come from the trunk's turn, inside a circle of 2.5 m that the robot may not leave until the discus is down. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the client (`solution/rows.npz`, recorded at generation time). Reference: a standing throw by the trunk's turn from a technique found offline by CMA-ES over whole-body key poses (Embodied Olympics' method): 12.9 m/s from 1.82 m, 15.87 m (the line is 15 m), then out of the rear half and standing. Open loop on the frozen start, not robust. Referee test negatives: walking out with it, out early, outside the sector, short, touched after the release, a front-half exit The privileged twin's reference rows (848 control steps, success after 8.48 s) streamed through the client.

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The men's discus (2.0 kg, 0.22 m across, 0.045 m thick at its centre) starts gripped flat against your right palm. The circle is 2.5 m across inside its rim; the ground outside is 0.02 m higher than its inside. The sector opens from the circle's centre, 34.92 degrees wide, symmetric about the direction you face at the start. The throw: you let go of the discus (once: it cannot be gripped again). Its first touch of the ground must be inside the sector lines (on a line is out); the throw is measured from that point to the inside of the rim along the line through the circle's centre. You succeed when a valid throw measures at least 15.0 m and you have then left the circle correctly and stood for 1.0 s. Leaving correctly: after the discus has landed, your first touch of the rim's top or of the ground outside the circle is behind the line through the circle's centre across the throwing direction (the rear half). Standing: only your feet on the ground, the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. You fail if any part of you touches the rim's top (its top inside edge included) or the ground outside the circle before the discus has landed, or in the front half before you have left correctly; if the discus lands outside the sector or short of 15.0 m; if any part of you touches it after the release (your right arm may still brush it during the first 0.2 s); if you fall (your pelvis lower than 0.5 m above the circle's floor, or any part of you other than your feet on the ground); or after 60 s. Where you touch the ground is judged on the points of contact; a contact within 0.003 m of the rim's top counts as on it.

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
| Category | throwing-catching-striking |
| Rule book | World Athletics Competition and Technical Rules 2024: TR 32.5-32.8 (the circle, 2.50 m for the discus), TR 32.12 (the 34.92 degree sector), TR 32.13, 32.14, 32.16, 32.17 and 32.20 (throwing events: the start, failures, the landing, leaving the circle, the measurement), TR 34 (the men's discus), TR 35 (the discus cage); deviations: TR 34 (the discus): the hand holds the discus flat against its palm by a grip switched on and off, not by fingertips over the rim; it is released when the grip is switched off. The discus is an ellipsoid of the official diameter, thickness and mass (no separate metal rim: its moment of inertia is that of a uniform body). · TR 35 (the cage): there is no cage. · TR 32.5-32.6: the ground outside the circle is level with the rim's top for 1 m and then falls to the field's level over 1 m (the circle's inside is the field's level, 0.02 m below the rim, instead of the field being level with the rim). · TR 32.20: the mark is the point where the discus first touches the ground. · TR 32.15 (interrupting a trial, laying the implement down): not modelled; the first release is the throw, and the discus cannot be gripped again. · TR 32.14 names no fall: here a fall ends the trial as a failure, as in every task of this benchmark; the trial ends when the robot has left the circle correctly and stands. · TR 25.17 (one minute for a trial): the whole trial, leaving the circle included, has 60 s. · Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag, lift and the pitching moment of an ellipsoid, coefficients of the order of the published wind-tunnel data), still air, no wind. · The qualifying mark of 15.0 m is this benchmark's (a school standard for the 2 kg discus); the rule book only measures. |
| Stages | release → landing → exit |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
