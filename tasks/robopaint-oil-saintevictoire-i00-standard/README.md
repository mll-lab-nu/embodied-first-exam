# robopaint-oil-saintevictoire-i00-standard

Standard-mode twin of `robopaint-oil-saintevictoire-i00` (same frozen instance): the agent gets only the `eai-standard/2.2` client
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
| static facts | sheets (main: scored; practice: never scored or counted), the 16 paint wells (colours, radii) and the dip rule, the brush's tuft length and handle stop, the picture → sheet mapping (and its scale), the stroke budget (659); not given: where anything is (no positions or heights: the cameras show them), the paint engine or its preset |
| cameras | `canvas_cam` (overhead main sheet, 1024²), `practice_cam` (overhead practice sheet, 512×1024), `scene_cam` (640×480), `side_cam` (640×360, grazing view of the brush height); static calibration in every response |
| oracle | `solution/`: streams the privileged reference solution's joint targets (one row per control step, `hold`) as `joint_position` chunks; the recorded trajectory then equals the privileged one; label `partial` (task.toml `oracle_evidence`: the recorded runs predate this version), human review in PR #3 |
| crash recovery | the service journals every executed control step (`journal.f64`) and checkpoints every call with the state hash; after a crash compose restarts the sidecar (`restart: on-failure:6`) and the service resumes the SAME episode (resume class `exact`: the replayed state must equal the checkpoint), at most twice; `reward.json` reports `sim_startups`, `resumes`, `infra_error` (docs/STANDARD_MODE_2_2.md §13) |
| verification | `success` = both fresh-process replays of the recorded episode meet the rule (mean CIELAB ΔE <= 8.4, p90 ΔE <= 14.0, SSIM of L* >= 0.62, edge correlation >= 0.29, paint IoU >= 0.96 (all after the best single shift of the sheet, at most 5 mm along each axis, inside the central area 8 mm in from the sheet's edges) and at most 659 strokes) ∧ they agree exactly (computed in the sidecar after the agent is gone); every metric of the replayed sheet in `reward.json`; `/logs/verifier/replay.mp4` |

The picture is a public-domain painting, Paul Cézanne, *Mont Sainte-Victoire* (1902-06; Wikimedia Commons `File:Paul Cézanne - Mont Sainte-Victoire - Google Art Project.jpg`, Public domain), cropped to a square and downscaled to the sheet; libmypaint is ISC, the presets CC0: `environment/NOTICE-exemplar.md`.
