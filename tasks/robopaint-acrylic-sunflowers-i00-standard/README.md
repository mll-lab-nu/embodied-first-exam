# robopaint-acrylic-sunflowers-i00-standard

Standard-mode twin of `robopaint-acrylic-sunflowers-i00` (same frozen instance): the agent gets only the `eai-standard/2.2` client
(docs/STANDARD_MODE_2_2.md) and the exemplar as a picture (`/app/target.png`, 1024 px covering the main sheet); the simulator
and the paint engine (libmypaint) run in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar for the cameras), which owns the
scene and records the episode as a (T, 7) trajectory. There is no reset, no sheet readout, no brush state or paint model and no score:
paint is permanent and the agent sees the sheets only through the cameras (`canvas_cam` 1024 px over the main sheet, `practice_cam`
over the practice sheet). The practice sheet is there for test strokes. The collect hook
(`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the trajectory in two fresh processes, scores the
replayed main sheet and writes `final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.

| | |
|---|---|
| mode | standard (camera RGB + proprioception, no reset) |
| action space | `eai-standard/2.2`: `submit` chunks of `ee_pose` (7: brush-tip pose, rows `dt` apart, straight-line tip targets with IK per 20 Hz control step, ≤ 0.25 m/s) or `joint_position` (7, streamed at 20 Hz); `observe` frames or a watch window; binary RCB1 responses |
| static facts | sheets (main: scored; practice: never scored or counted), the 10 paint wells (colours, radii) and the dip rule, the brush's tuft length and handle stop, the picture → sheet mapping (and its scale), the stroke budget (380); not given: where anything is (no positions or heights: the cameras show them), the paint engine or its preset, the hidden stroke program |
| cameras | `canvas_cam` (overhead main sheet, 1024²), `practice_cam` (overhead practice sheet, 512×1024), `scene_cam` (640×480), `side_cam` (640×360, grazing view of the brush height); static calibration in every response |
| oracle | `solution/`: streams the privileged oracle's joint targets (one row per control step, `hold`) as `joint_position` chunks; the recorded trajectory then equals the privileged oracle's; label `partial` (task.toml `oracle_evidence`: the recorded runs predate this version), human review in PR #3 |
| crash recovery | the service journals every executed control step (`journal.f64`) and checkpoints every call with the state hash; after a crash compose restarts the sidecar (`restart: on-failure:6`) and the service resumes the SAME episode (resume class `exact`: the replayed state must equal the checkpoint), at most twice; `reward.json` reports `sim_startups`, `resumes`, `infra_error` (docs/STANDARD_MODE_2_2.md §13) |
| verification | `success` = both fresh-process replays of the recorded episode meet the rule (after the best single shift of the sheet, at most 5 mm along each axis, mean CIELAB ΔE <= 2.0, p90 ΔE <= 6.0, SSIM of L* >= 0.92, edge correlation >= 0.8, paint IoU >= 0.95 and at most 380 strokes) ∧ they agree exactly (computed in the sidecar after the agent is gone); every metric of the replayed sheet in `reward.json`; `/logs/verifier/replay.mp4` |

The exemplar is this robot's painting after Vincent van Gogh, *Sunflowers* (1888), a public-domain work (Wikimedia Commons `File:Vincent Willem van Gogh 127.jpg`, Public domain); the exemplar picture is CC0; libmypaint is ISC, the presets CC0: `environment/NOTICE-exemplar.md`.
