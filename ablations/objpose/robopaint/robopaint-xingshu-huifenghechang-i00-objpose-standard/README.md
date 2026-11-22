# robopaint-xingshu-huifenghechang-i00-standard

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robopaint-xingshu-huifenghechang-i00-privileged` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_xingshu_huifenghechang` / seed 0 |
| Oracle | `partial` — Reference solution in solution/ (streams the privileged reference's joint targets; tasks/robopaint/README.md, Targets). The same trajectory scores 1 under the process rules in the verifier (the graders' rcb_brush_strict.py, with which the sim service also scores the live sheet): path_mm 2483 and mark_width_mm 3.04, against the colouring-in limits 6060 mm and 1.15 mm. Harbor oracle 1 and nop 0 on both modes of this pair on its current files (2026-10-09): tasks/robopaint/README.md (Validation). |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:robopaint-0.2.0` |

## Task
**Process rules** (tasks/robopaint/README.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: colouring in fails: a brush-tip path on the main sheet (`path_mm`) longer than 6060 mm (3 × the reference
solution's 2017 mm) made of marks narrower than 1.15 mm on average (`mark_width_mm`: each stroke's own
inked area / `path_mm`; 0.3 × the reference's 3.85 mm). The cap counts strokes as written: a contact is cut where the brush moves more than 5 mm without a mark
0.1 mm wide, and a stroke longer than 1250 mm (5 × the reference's
longest, 250 mm) counts once per started 1250 mm; at most 10 % of the
path in strokes longer than 12 × their bounding box's diagonal (sweeps). They are part of the frozen instance (the rules added to its `target.success`); the sim service
applies them to the live sheet with the graders' `rcb_brush_strict.py`.

Standard-mode twin of `robopaint-xingshu-huifenghechang-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.2` client
(docs/protocol/standard_mode.md) and the target picture (`/app/target.png`, 1024 px covering the main sheet); the simulator and the
brush model run in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar for the cameras), which owns the scene
and records the episode as a (T, 7) trajectory. There is no reset, no sheet readout, no brush state or model and no score: ink is
permanent and the agent sees the sheets only through the cameras (`canvas_cam` 1024 px over the main sheet, `practice_cam` over the
practice sheet). It has to find out how the brush marks the paper on the practice sheet. The collect hook
(`environment/sim/finalize.sh`) ends the episode; the service scores its live main sheet and writes `final.json`, then renders the
trajectory once into the video; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.

## Difficulty
Same scene, exemplar and rule as `robopaint-xingshu-huifenghechang-i00-privileged` (see its Difficulty), without its privileged help: no reset, no sheet readout, no model of the mark and no score. Every stroke on the main sheet is permanent and is seen only through the cameras; how the tool marks the paper has to be learned from test strokes on the practice sheet.

## Reference solution
`solution/`: streams the privileged oracle's joint targets (one row per control step, `hold`) as `joint_position` chunks; the recorded trajectory then equals the privileged oracle's; label `partial` (task.toml `oracle_evidence`: the reference solution, scored under the process rules).

## Verification
"The rule" below is the picture rule and the process rules (Task); the sim service scores the live sheet with
`environment/sim/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
`success` = the live episode's main sheet meets the rule after the best single shift of the sheet, at most 5 mm along each axis (IoU ≥ 0.80, boundary F ≥ 0.75, every region covered ≥ 0.80 (43 regions of the exemplar's ink), stray ≤ 0.04, ≤ 28 strokes), scored by the sim sidecar after the agent's container is stopped (`final.json`: `graded_by = "live"`; nothing is replayed to grade it); every metric of the live sheet in `reward.json`; `/logs/verifier/replay.mp4` (the trajectory rendered once after the verdict).
A `final.json` that is missing, unreadable or without a verdict (the collect hook did not finish), a give-up after crashes
that were not all inside the agent's calls, a frozen instance that does not rebuild in the sidecar (`instance_mismatch`, refused
before the agent is served) and a live sheet the service could not score (`grade_error`) are an infrastructure failure
(`infra_error = 1`), not the agent's 0; `sim_error = 1` marks an episode that a simulator error ended. A video that fails or runs
out of time never changes the verdict. The collect hook has 2820 s.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 5 GiB | 2048 | no GPU | 10 GiB |
| `sim` | 3 | 5 GiB | 1024 | 3 GiB | — |
| verifier (as `main`) | 8 | 5 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## Details
| | |
|---|---|
| Action space | `eai-standard/2.2`: `submit` chunks of `ee_pose` (7: brush-tip pose, rows `dt` apart, straight-line tip targets with IK per 20 Hz control step, ≤ 0.25 m/s) or `joint_position` (7, streamed at 20 Hz); `observe` frames or a watch window; binary RCB1 responses |
| Static facts | sheets (main: scored; practice: never scored or counted), the ink stone and its dip rule, the brush's tuft length and handle stop, the picture → sheet mapping (and its scale), the stroke cap (28); not given: where anything is (no positions or heights: the cameras show them), the brush model, any width table |
| Cameras | `canvas_cam` (overhead main sheet, 1024²), `practice_cam` (overhead practice sheet, 512×1024), `scene_cam` (640×480), `side_cam` (640×360, grazing view of the brush height); static calibration in every response |
| Crash recovery | the service journals every executed control step (`journal.f64`) and checkpoints every call with the state hash; after a crash compose restarts the sidecar (`restart: on-failure:6`) and the service resumes the SAME episode (resume class `exact`: the replayed state must equal the checkpoint), at most twice; `reward.json` reports `sim_startups`, `resumes`, `infra_error` (docs/protocol/standard_mode.md §13) |

### Sources
Wikimedia Commons, File:神龍蘭亭序全.JPG (https://commons.wikimedia.org/wiki/File:%E7%A5%9E%E9%BE%8D%E8%98%AD%E4%BA%AD%E5%BA%8F%E5%85%A8.JPG): the Shenlong hand copy (馮承素, attributed, Tang, c. 627-650, ink on paper, Palace Museum, Beijing) of Wang Xizhi's 蘭亭序 (running script, c. 353). Licence on the file page: {{PD-Art|PD-old-100-1923|deathyear=672}} (public domain). The characters were cropped from this scan (downloaded unmodified on 2026-09-28), binarised and placed on the sheet; the scroll writes 脩 for 修.

### Licences
The exemplar is a public-domain rubbing/scan of a historical work of running-script calligraphy (Wikimedia Commons, PD-Art /
PD-old; Sources above); licence notices: `environment/NOTICE-exemplar.md` (the agent's), `environment/sim/NOTICE-exemplar.md`
(the graders').
