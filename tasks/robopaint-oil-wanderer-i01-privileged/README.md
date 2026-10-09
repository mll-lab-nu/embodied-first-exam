# robopaint-oil-wanderer-i01-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-oil-wanderer-i01-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_oil_wanderer` / seed 0 |
| Oracle | `partial` — Reference solution in solution/: the hi-res version's stroke program for the pointed brush, executed by the robot at generation time (2026-10-09; README Change Log). The verifier scores it 1 (tests/grade.py with rcb_brush_strict.py, two fresh replays, the eai-robopaint:0.2.0 runtime, 2026-10-09): path_mm 21539 of the 64700 mm budget; its strokes are sweeps. Harbor oracle and nop runs: docs/benchmarks/robopaint.md (Oil: the pointed brush). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
**Process rules** (docs/benchmarks/robopaint.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: the brush tip's path while it presses on the main sheet with paint (`path_mm`) is at most 64700 mm (3 ×
the reference solution's 21539 mm), and at most 10 % of it lies in strokes longer than
2.5 × the diagonal of their bounding box (zigzags, back-and-forth fills, spirals, loops). They are part of the frozen instance (the rules added to its `target.success`); the graders'
`rcb_brush_strict.py` applies them (the verifier and the scoring service).

The instance: paint the picture in `environment/target.png` (a square crop of Caspar David Friedrich's Wanderer above the Sea of Fog, c. 1817: a public-domain masterpiece, cropped and downscaled to the 227 mm main sheet) in at most 1974 strokes, with 16 premixed paints (the picture's colours quantised) on a plate and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; everything frozen in `environment/instance.json`.

Paint the picture: mean CIELAB ΔE <= 3.1, p90 ΔE <= 5.5, SSIM of L* >= 0.87, edge correlation >= 0.78, paint IoU >= 0.96 (all after the best single shift of the sheet, at most 5 mm along each axis, inside the central area 8 mm in from the sheet's edges) and at most 1974 strokes. `final_reward` = max(0, 1 - mean ΔE / 20) (× 1974 / strokes above 1974). The thresholds are the reference solution's execution by this robot (1333 strokes: mean ΔE 2.73, p90 4.85, SSIM 0.913, edge correlation 0.839, paint IoU 1.000) with a margin (ΔE x 1.1, SSIM - 0.04, edge correlation - 0.05, paint IoU - 0.03).

## Difficulty
There is no exact solution: the picture is a real painting, the paint is wet (strokes pick up and blend what is under them), the brush makes 2-11 mm marks (the fine ones need a light, exact press), 16 premixed paints are all there is, and fine work costs robot time: the reference solution's 1333 strokes take 41 of the episode's 60 simulated minutes (49736 of the 72000 control steps). The rule is set by the reference solution executed by this robot, with a margin; the measured axes are in task.toml [metadata].

## Reference solution
The reference solution is our baseline painter's stroke program (`solution/program.json`, made at generation time by a stroke optimiser with libmypaint in the loop against the picture: a ground of parallel rows in the nearest paints, then 4 layers of curved strokes along the picture's isophotes with ever lighter presses (marks of about 6, 3.6, 2.6 and 2.1 mm), placed where the canvas is furthest from the picture, each paint's strokes of a layer in a nearest-neighbour order) executed by the robot (`solution/ref_oil.py` with the program's `motion`: a 6 mm hover between strokes, quick dips, short holds); the rule was calibrated on exactly that execution (`solution/calibration.json`). The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
49736 control steps, 1333 strokes, mean ΔE 2.729, p90 ΔE 4.854, SSIM 0.9127, paint IoU 0.9996.

## Verification
"The rule" below is the picture rule and the process rules (Task); the replays run
`tests/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
Oracle label `partial`: the reference solution, scored under the process rules (task.toml `oracle_evidence`).
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes (`tests/grade.py`); pass iff
both replayed main sheets meet the rule, the final-state hashes (paint layers of both sheets + robot state + the loaded paint)
agree and the rebuilt frozen instance matches the recorded one. PhysX and libmypaint (single-threaded, with the image's
determinism patch) run on the CPU: a live run, in-process replays and fresh-process replays end in the same state bit for bit
(`rcb_brush.py selftest`); camera rendering does not change it. `/logs/verifier/replay.mp4` and `canvas.png` never affect the verdict.

## Details
| | |
|---|---|
| Simulator, tool and robot | ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU) + libmypaint 1.6.1 (ISC; the mypaint-brushes 2.0.2 preset `tanda/oil-03-paint`, CC0, made pointed: its random dab offset and tracking noise follow the pressure, frozen as `brush.preset_json`) through `rcb_brush.py`'s MyPaintPainter (CPU) / franka-panda holding a paint brush (PandaStick's rigid stick as the handle + a 15 mm collision-free tuft; TCP = the tuft's tip) |
| Base image and GPU | 0.1.1 + libmypaint + the shim + the presets. Physics and paint run on the CPU; SAPIEN still needs the NVIDIA GPU (Vulkan) to build the scene and render: `environment/docker-compose.yaml` |

### Change Log
- 2026-10-09: the hi-res version (docs/benchmarks/robopaint.md, Oil: the pointed brush). The brush is `tanda/oil-03-paint` made pointed: a light press draws a 2-3 mm line (before, every mark was 5-11 mm wide). The reference solution is a new program of 1316 strokes (was 288); executed by the robot it scores mean ΔE 2.73, SSIM 0.913 and edge correlation 0.839 against the picture (was 3.66, 0.843, 0.698). The rule is recalibrated on it with the same margins, except SSIM - 0.04 (was - 0.03): mean ΔE <= 3.1 (was 4.1), p90 ΔE <= 5.5 (was 8.5), SSIM >= 0.87 (was 0.81), edge correlation >= 0.78 (was 0.64); at most 1974 strokes (was 432); a path of at most 64700 mm (was 28900 mm). The picture, the scene's geometry and the scoring code are unchanged; results before this date are not comparable with this version.
