# {{NAME}}-standard

## Task
Standard-mode twin of `{{NAME}}-privileged` (same frozen instance): the agent gets only the `eai-standard/2.2` client
(docs/protocol/standard_mode.md) and the exemplar as a picture (`/app/target.png`, 1024 px covering the main sheet); the simulator
and the paint engine (libmypaint) run in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar for the cameras), which owns the
scene and records the episode as a (T, 7) trajectory. There is no reset, no sheet readout, no brush state or paint model and no score:
paint is permanent and the agent sees the sheets only through the cameras (`canvas_cam` 1024 px over the main sheet, `practice_cam`
over the practice sheet). The practice sheet is there for test strokes. The collect hook
(`environment/sim/finalize.sh`) ends the episode; the service scores its live main sheet and writes `final.json`, then renders the
trajectory once into the video; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.

## Difficulty
Same scene, exemplar and rule as `{{NAME}}-privileged` (see its Difficulty), without its privileged help: no reset, no sheet readout, no model of the mark and no score. Every stroke on the main sheet is permanent and is seen only through the cameras; how the tool marks the paper has to be learned from test strokes on the practice sheet.

## Reference solution
{{L_ORACLE}}; label `{{ORACLE}}` (task.toml `oracle_evidence`: the recorded runs predate this version), human review in PR #3.

## Verification
`success` = the live episode's main sheet meets the rule ({{RULE_SHORT}}), scored by the sim sidecar after the agent's container is stopped (`final.json`: `graded_by = "live"`; nothing is replayed to grade it); every metric of the live sheet in `reward.json`; `/logs/verifier/replay.mp4` (the trajectory rendered once after the verdict).

## Details
| | |
|---|---|
| Action space | `eai-standard/2.2`: `submit` chunks of `ee_pose` (7: brush-tip pose, rows `dt` apart, straight-line tip targets with IK per 20 Hz control step, ≤ 0.25 m/s) or `joint_position` (7, streamed at 20 Hz); `observe` frames or a watch window; binary RCB1 responses |
| Static facts | sheets (main: scored; practice: never scored or counted), the {{NCOLORS}} paint wells (colours, radii) and the dip rule, the brush's tuft length and handle stop, the picture → sheet mapping (and its scale), the stroke budget ({{BUDGET}}); not given: where anything is (no positions or heights: the cameras show them), the paint engine or its preset{{L_NOT_GIVEN}} |
| Cameras | `canvas_cam` (overhead main sheet, 1024²), `practice_cam` (overhead practice sheet, 512×1024), `scene_cam` (640×480), `side_cam` (640×360, grazing view of the brush height); static calibration in every response |
| Crash recovery | the service journals every executed control step (`journal.f64`) and checkpoints every call with the state hash; after a crash compose restarts the sidecar (`restart: on-failure:6`) and the service resumes the SAME episode (resume class `exact`: the replayed state must equal the checkpoint), at most twice; `reward.json` reports `sim_startups`, `resumes`, `infra_error` (docs/protocol/standard_mode.md §13) |

### Licences
{{SRC}}; libmypaint is ISC, the presets CC0: `environment/NOTICE-exemplar.md`.

### Change Log
{{CHANGELOG}}
