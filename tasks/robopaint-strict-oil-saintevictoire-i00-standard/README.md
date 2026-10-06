# robopaint-strict-oil-saintevictoire-i00-standard

| | |
|---|---|
| Benchmark | RoboPaint-strict |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robopaint-strict-oil-saintevictoire-i00-privileged` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_strict_oil_saintevictoire` / seed 0 |
| Oracle | `partial` — The RoboPaint pair's reference solution, unchanged (solution/ streams the privileged reference's joint targets; its RoboPaint record: the oracle_evidence of robopaint-oil-saintevictoire-i00-standard). The same trajectory scores 1 under the process rules in the strict verifier, whose replay CLI the collect hook runs (ws3, 2026-10-05): path_mm 11925 of the 35800 mm budget; its strokes are sweeps. Harbor oracle and nop runs on one pair per family: docs/benchmarks/robopaint-strict.md (Validation). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
**RoboPaint-strict** (docs/benchmarks/robopaint-strict.md): the RoboPaint task `robopaint-oil-saintevictoire-i00-standard` with process rules on top of its
picture rule, so that the exemplar has to be made with strokes rather than coloured in: the brush tip's path while it presses on the main sheet with paint (`path_mm`) is at most 35800 mm (3 ×
the reference solution's 11925 mm), and at most 10 % of it lies in strokes longer than
2.5 × the diagonal of their bounding box (zigzags, back-and-forth fills, spirals, loops). Same scene, frozen instance
(the rules added to its `target.success`), picture, service and reference solution; the collect hook's replays apply the rules
with the graders' `rcb_brush_strict.py`.

Standard-mode twin of `robopaint-strict-oil-saintevictoire-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.2` client
(docs/STANDARD_MODE_2_2.md) and the exemplar as a picture (`/app/target.png`, 1024 px covering the main sheet); the simulator
and the paint engine (libmypaint) run in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar for the cameras), which owns the
scene and records the episode as a (T, 7) trajectory. There is no reset, no sheet readout, no brush state or paint model and no score:
paint is permanent and the agent sees the sheets only through the cameras (`canvas_cam` 1024 px over the main sheet, `practice_cam`
over the practice sheet). The practice sheet is there for test strokes. The collect hook
(`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the trajectory in two fresh processes, scores the
replayed main sheet and writes `final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.

## Difficulty
Same scene, exemplar and rule as `robopaint-strict-oil-saintevictoire-i00-privileged` (see its Difficulty), without its privileged help: no reset, no sheet readout, no model of the mark and no score. Every stroke on the main sheet is permanent and is seen only through the cameras; how the tool marks the paper has to be learned from test strokes on the practice sheet.

## Reference solution
`solution/`: streams the privileged reference solution's joint targets (one row per control step, `hold`) as `joint_position` chunks; the recorded trajectory then equals the privileged one; label `partial` (task.toml `oracle_evidence`: the RoboPaint pair's reference solution, scored under the process rules).

## Verification
RoboPaint-strict: "the rule" below is RoboPaint's picture rule and the process rules (Task); the collect hook's replays run
`environment/sim/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
`success` = both fresh-process replays of the recorded episode meet the rule (mean CIELAB ΔE <= 8.4, p90 ΔE <= 14.0, SSIM of L* >= 0.62, edge correlation >= 0.29, paint IoU >= 0.96 (all after the best single shift of the sheet, at most 5 mm along each axis, inside the central area 8 mm in from the sheet's edges) and at most 659 strokes) ∧ they agree exactly (computed in the sidecar after the agent is gone); every metric of the replayed sheet in `reward.json`; `/logs/verifier/replay.mp4`.

## Details
| | |
|---|---|
| Action space | `eai-standard/2.2`: `submit` chunks of `ee_pose` (7: brush-tip pose, rows `dt` apart, straight-line tip targets with IK per 20 Hz control step, ≤ 0.25 m/s) or `joint_position` (7, streamed at 20 Hz); `observe` frames or a watch window; binary RCB1 responses |
| Static facts | sheets (main: scored; practice: never scored or counted), the 16 paint wells (colours, radii) and the dip rule, the brush's tuft length and handle stop, the picture → sheet mapping (and its scale), the stroke budget (659); not given: where anything is (no positions or heights: the cameras show them), the paint engine or its preset |
| Cameras | `canvas_cam` (overhead main sheet, 1024²), `practice_cam` (overhead practice sheet, 512×1024), `scene_cam` (640×480), `side_cam` (640×360, grazing view of the brush height); static calibration in every response |
| Crash recovery | the service journals every executed control step (`journal.f64`) and checkpoints every call with the state hash; after a crash compose restarts the sidecar (`restart: on-failure:6`) and the service resumes the SAME episode (resume class `exact`: the replayed state must equal the checkpoint), at most twice; `reward.json` reports `sim_startups`, `resumes`, `infra_error` (docs/STANDARD_MODE_2_2.md §13) |

### Licences
The picture is a public-domain painting, Paul Cézanne, *Mont Sainte-Victoire* (1902-06; Wikimedia Commons `File:Paul Cézanne - Mont Sainte-Victoire - Google Art Project.jpg`, Public domain), cropped to a square and downscaled to the sheet; libmypaint is ISC, the presets CC0: `environment/NOTICE-exemplar.md`.
