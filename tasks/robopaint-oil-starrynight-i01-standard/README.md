# robopaint-oil-starrynight-i01-standard

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robopaint-oil-starrynight-i01-privileged` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_oil_starrynight` / seed 0 |
| Oracle | `partial` — Reference solution in solution/ (streams the privileged reference's joint targets; the hi-res version of 2026-10-09, README Change Log). The same trajectory scores 1 under the process rules in the verifier, whose replay CLI the collect hook runs (2026-10-09): path_mm 20747 of the 62300 mm budget; its strokes are sweeps. Harbor oracle and nop runs: docs/benchmarks/robopaint.md (Oil: the pointed brush). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
**Process rules** (docs/benchmarks/robopaint.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: the brush tip's path while it presses on the main sheet with paint (`path_mm`) is at most 62300 mm (3 ×
the reference solution's 20747 mm), and at most 10 % of it lies in strokes longer than
2.5 × the diagonal of their bounding box (zigzags, back-and-forth fills, spirals, loops). They are part of the frozen instance (the rules added to its `target.success`); the collect hook's
replays apply them with the graders' `rcb_brush_strict.py`.

Standard-mode twin of `robopaint-oil-starrynight-i01-privileged` (same frozen instance): the agent gets only the `eai-standard/2.2` client
(docs/STANDARD_MODE_2_2.md) and the exemplar as a picture (`/app/target.png`, 1024 px covering the main sheet); the simulator
and the paint engine (libmypaint) run in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar for the cameras), which owns the
scene and records the episode as a (T, 7) trajectory. There is no reset, no sheet readout, no brush state or paint model and no score:
paint is permanent and the agent sees the sheets only through the cameras (`canvas_cam` 1024 px over the main sheet, `practice_cam`
over the practice sheet). The practice sheet is there for test strokes. The collect hook
(`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the trajectory in two fresh processes, scores the
replayed main sheet and writes `final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.

## Difficulty
Same scene, exemplar and rule as `robopaint-oil-starrynight-i01-privileged` (see its Difficulty), without its privileged help: no reset, no sheet readout, no model of the mark and no score. Every stroke on the main sheet is permanent and is seen only through the cameras; how the tool marks the paper has to be learned from test strokes on the practice sheet.

## Reference solution
`solution/`: streams the privileged reference solution's joint targets (one row per control step, `hold`) as `joint_position` chunks; the recorded trajectory then equals the privileged one; label `partial` (task.toml `oracle_evidence`: the reference solution, scored under the process rules).

## Verification
"The rule" below is the picture rule and the process rules (Task); the collect hook's replays run
`environment/sim/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
`success` = both fresh-process replays of the recorded episode meet the rule (mean CIELAB ΔE <= 6.5, p90 ΔE <= 11.5, SSIM of L* >= 0.68, edge correlation >= 0.52, paint IoU >= 0.96 (all after the best single shift of the sheet, at most 5 mm along each axis, inside the central area 8 mm in from the sheet's edges) and at most 2517 strokes) ∧ they agree exactly (computed in the sidecar after the agent is gone); every metric of the replayed sheet in `reward.json`; `/logs/verifier/replay.mp4`.

## Details
| | |
|---|---|
| Action space | `eai-standard/2.2`: `submit` chunks of `ee_pose` (7: brush-tip pose, rows `dt` apart, straight-line tip targets with IK per 20 Hz control step, ≤ 0.25 m/s) or `joint_position` (7, streamed at 20 Hz); `observe` frames or a watch window; binary RCB1 responses |
| Static facts | sheets (main: scored; practice: never scored or counted), the 16 paint wells (colours, radii) and the dip rule, the brush's tuft length and handle stop, the picture → sheet mapping (and its scale), the stroke budget (2517); not given: where anything is (no positions or heights: the cameras show them), the paint engine or its preset |
| Cameras | `canvas_cam` (overhead main sheet, 1024²), `practice_cam` (overhead practice sheet, 512×1024), `scene_cam` (640×480), `side_cam` (640×360, grazing view of the brush height); static calibration in every response |
| Crash recovery | the service journals every executed control step (`journal.f64`) and checkpoints every call with the state hash; after a crash compose restarts the sidecar (`restart: on-failure:6`) and the service resumes the SAME episode (resume class `exact`: the replayed state must equal the checkpoint), at most twice; `reward.json` reports `sim_startups`, `resumes`, `infra_error` (docs/STANDARD_MODE_2_2.md §13) |

### Licences
The picture is a public-domain painting, Vincent van Gogh, *The Starry Night* (1889; Wikimedia Commons `File:Van Gogh - Starry Night - Google Art Project.jpg`, Public domain), cropped to a square and downscaled to the sheet; libmypaint is ISC, the presets CC0: `environment/NOTICE-exemplar.md`.

### Change Log
- 2026-10-09: the hi-res version (docs/benchmarks/robopaint.md, Oil: the pointed brush). The brush is `tanda/oil-03-paint` made pointed: a light press draws a 2-3 mm line (before, every mark was 5-11 mm wide). The reference solution is a new program of 1678 strokes (was 455); executed by the robot it scores mean ΔE 5.91, SSIM 0.721 and edge correlation 0.572 against the picture (was 7.64, 0.595, 0.337). The rule is recalibrated on it with the same margins, except SSIM - 0.04 (was - 0.03): mean ΔE <= 6.5 (was 8.4), p90 ΔE <= 11.5 (was 15.5), SSIM >= 0.68 (was 0.56), edge correlation >= 0.52 (was 0.28); at most 2517 strokes (was 683); a path of at most 62300 mm (was 39600 mm). The picture, the scene's geometry and the scoring code are unchanged; results before this date are not comparable with this version.
