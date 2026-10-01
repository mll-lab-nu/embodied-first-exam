# robopaint-xingshu-ren-i00-standard

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robopaint-xingshu-ren-i00-privileged` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_xingshu_ren` / seed 0 |
| Oracle | `partial` — Reference solution in solution/. Oracle 1 and nop 0 in the release validation (ws3, 2026-09-28: xingshu-l-oracle-final0928, xingshu-l-nop-final0928), on earlier scoring and tooling. Changed since: the v2 registered scoring (a67040a8: scorer and success rule; the saved oracle trajectories re-scored, all pass; Harbor oracle and nop on tianlangqiqing and zhi), tooling snapshot 23 (ccb213d0: the scorer; re-scores bit-identical), the 2.2 inputs (cf95376f) and the rated limits (fe5fb9e6), both adding tooling queries only; protocol v1.0 gave the standard service, collect hook, grader and oracle client crash recovery. Not re-run on this version (static validation only). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/embodied-agent-interface-v2-internal/eai-robopaint:0.2.0` |

## Task
Standard-mode twin of `robopaint-xingshu-ren-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.2` client
(docs/STANDARD_MODE_2_2.md) and the target picture (`/app/target.png`, 1024 px covering the main sheet); the simulator and the
brush model run in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar for the cameras), which owns the scene
and records the episode as a (T, 7) trajectory. There is no reset, no sheet readout, no brush state or model and no score: ink is
permanent and the agent sees the sheets only through the cameras (`canvas_cam` 1024 px over the main sheet, `practice_cam` over the
practice sheet). It has to find out how the brush marks the paper on the practice sheet. The collect hook
(`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the trajectory in two fresh processes, scores the
replayed main sheet and writes `final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.

## Difficulty
Same scene, exemplar and rule as `robopaint-xingshu-ren-i00-privileged` (see its Difficulty), without its privileged help: no reset, no sheet readout, no model of the mark and no score. Every stroke on the main sheet is permanent and is seen only through the cameras; how the tool marks the paper has to be learned from test strokes on the practice sheet.

## Reference solution
`solution/`: streams the privileged oracle's joint targets (one row per control step, `hold`) as `joint_position` chunks; the recorded trajectory then equals the privileged oracle's; label `partial` (task.toml `oracle_evidence`: the recorded runs predate this version), human review in PR #3.

## Verification
`success` = both fresh-process replays of the recorded episode meet the rule after the best single shift of the sheet, at most 5 mm along each axis (IoU ≥ 0.80, boundary F ≥ 0.75, every region covered ≥ 0.80 (2 regions of the exemplar's ink), stray ≤ 0.04, ≤ 2 strokes) ∧ they agree exactly (computed in the sidecar after the agent is gone); every metric of the replayed sheet in `reward.json`; `/logs/verifier/replay.mp4`.

## Details
| | |
|---|---|
| Action space | `eai-standard/2.2`: `submit` chunks of `ee_pose` (7: brush-tip pose, rows `dt` apart, straight-line tip targets with IK per 20 Hz control step, ≤ 0.25 m/s) or `joint_position` (7, streamed at 20 Hz); `observe` frames or a watch window; binary RCB1 responses |
| Static facts | sheets (main: scored; practice: never scored or counted), the ink stone and its dip rule, the brush's tuft length and handle stop, the picture → sheet mapping (and its scale), the stroke cap (2); not given: where anything is (no positions or heights: the cameras show them), the brush model, any width table |
| Cameras | `canvas_cam` (overhead main sheet, 1024²), `practice_cam` (overhead practice sheet, 512×1024), `scene_cam` (640×480), `side_cam` (640×360, grazing view of the brush height); static calibration in every response |
| Crash recovery | the service journals every executed control step (`journal.f64`) and checkpoints every call with the state hash; after a crash compose restarts the sidecar (`restart: on-failure:6`) and the service resumes the SAME episode (resume class `exact`: the replayed state must equal the checkpoint), at most twice; `reward.json` reports `sim_startups`, `resumes`, `infra_error` (docs/STANDARD_MODE_2_2.md §13) |

### Sources
Wikimedia Commons, File:神龍蘭亭序全.JPG (https://commons.wikimedia.org/wiki/File:%E7%A5%9E%E9%BE%8D%E8%98%AD%E4%BA%AD%E5%BA%8F%E5%85%A8.JPG): the Shenlong hand copy (馮承素, attributed, Tang, c. 627-650, ink on paper, Palace Museum, Beijing) of Wang Xizhi's 蘭亭序 (running script, c. 353). Licence on the file page: {{PD-Art|PD-old-100-1923|deathyear=672}} (public domain). The characters were cropped from this scan (downloaded unmodified on 2026-09-28), binarised and placed on the sheet; the scroll writes 脩 for 修.

### Licences
The exemplar is a public-domain rubbing/scan of a historical work of running-script calligraphy (Wikimedia Commons, PD-Art /
PD-old; Sources above); licence notices: `environment/NOTICE-exemplar.md` (the agent's), `environment/sim/NOTICE-exemplar.md`
(the graders').
