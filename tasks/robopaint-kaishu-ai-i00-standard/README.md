# robopaint-kaishu-ai-i00-standard

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robopaint-kaishu-ai-i00-privileged` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_kaishu_ai` / seed 0 |
| Oracle | `partial` — Reference solution in solution/ (streams the privileged reference's joint targets), unchanged from the earlier version of this task (the picture score only; its Harbor oracle and nop runs, and what changed since: docs/benchmarks/robopaint.md, Oracle evidence). The same trajectory scores 1 under the process rules in the verifier, whose replay CLI the collect hook runs (ws3, 2026-10-05): path_mm 735 and mark_width_mm 5.57, against the colouring-in limits 2210 mm and 1.67 mm. Harbor oracle and nop runs on one pair per family: docs/benchmarks/robopaint.md (Validation). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
**Process rules** (docs/benchmarks/robopaint.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: colouring in fails: a brush-tip path on the main sheet (`path_mm`) longer than 2210 mm (3 × the reference
solution's 735 mm) made of marks narrower than 1.67 mm on average (`mark_width_mm`: each stroke's own
inked area / `path_mm`; 0.3 × the reference's 5.57 mm). They are part of the frozen instance (the rules added to its `target.success`); the collect hook's
replays apply them with the graders' `rcb_brush_strict.py`.

Standard-mode twin of `robopaint-kaishu-ai-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.2` client
(docs/STANDARD_MODE_2_2.md) and the target picture (`/app/target.png`, 1024 px covering the main sheet); the simulator and the
brush model run in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar for the cameras), which owns the scene
and records the episode as a (T, 7) trajectory. There is no reset, no sheet readout, no brush state or model and no score: ink is
permanent and the agent sees the sheets only through the cameras (`canvas_cam` 1024 px over the main sheet, `practice_cam` over the
practice sheet). It has to find out how the brush marks the paper on the practice sheet. The collect hook
(`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the trajectory in two fresh processes, scores the
replayed main sheet and writes `final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.

## Difficulty
Same scene, exemplar and rule as `robopaint-kaishu-ai-i00-privileged` (see its Difficulty), without its privileged help: no reset, no sheet readout, no model of the mark and no score. Every stroke on the main sheet is permanent and is seen only through the cameras; how the tool marks the paper has to be learned from test strokes on the practice sheet.

## Reference solution
`solution/`: streams the privileged oracle's joint targets (one row per control step, `hold`) as `joint_position` chunks; the recorded trajectory then equals the privileged oracle's; label `partial` (task.toml `oracle_evidence`: the reference solution, scored under the process rules).

## Verification
"The rule" below is the picture rule and the process rules (Task); the collect hook's replays run
`environment/sim/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
`success` = both fresh-process replays of the recorded episode meet the rule after the best single shift of the sheet, at most 5 mm along each axis (IoU ≥ 0.80, boundary F ≥ 0.75, every stroke covered ≥ 0.80, stray ≤ 0.04, ≤ 13 strokes) ∧ they agree exactly (computed in the sidecar after the agent is gone); every metric of the replayed sheet in `reward.json`; `/logs/verifier/replay.mp4`.

## Details
| | |
|---|---|
| Action space | `eai-standard/2.2`: `submit` chunks of `ee_pose` (7: brush-tip pose, rows `dt` apart, straight-line tip targets with IK per 20 Hz control step, ≤ 0.25 m/s) or `joint_position` (7, streamed at 20 Hz); `observe` frames or a watch window; binary RCB1 responses |
| Static facts | sheets (main: scored; practice: never scored or counted), the ink stone and its dip rule, the brush's tuft length and handle stop, the picture → sheet mapping (and its scale), the stroke cap (13); not given: where anything is (no positions or heights: the cameras show them), the brush model, any width table |
| Cameras | `canvas_cam` (overhead main sheet, 1024²), `practice_cam` (overhead practice sheet, 512×1024), `scene_cam` (640×480), `side_cam` (640×360, grazing view of the brush height); static calibration in every response |
| Crash recovery | the service journals every executed control step (`journal.f64`) and checkpoints every call with the state hash; after a crash compose restarts the sidecar (`restart: on-failure:6`) and the service resumes the SAME episode (resume class `exact`: the replayed state must equal the checkpoint), at most twice; `reward.json` reports `sim_startups`, `resumes`, `infra_error` (docs/STANDARD_MODE_2_2.md §13) |

### Licences
The exemplar derives from the fonts AR PL KaitiM GB / AR PL UKai via Make Me a Hanzi (Arphic Public License):
`environment/ARPHICPL.TXT`, `environment/NOTICE-exemplar.md`.
