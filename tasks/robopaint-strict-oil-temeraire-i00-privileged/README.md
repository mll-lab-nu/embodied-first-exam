# robopaint-strict-oil-temeraire-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint-strict |
| Mode | privileged |
| Twin | `robopaint-strict-oil-temeraire-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_strict_oil_temeraire` / seed 0 |
| Oracle | `partial` — The RoboPaint pair's reference solution, unchanged (solution/; its RoboPaint record: the oracle_evidence of robopaint-oil-temeraire-i00-privileged). Under the process rules the strict verifier scores it 1 (tests/grade.py with rcb_brush_strict.py, two fresh replays, ws3, 2026-10-05): path_mm 9366 of the 28100 mm budget; its strokes are sweeps. Harbor oracle and nop runs on one pair per family: docs/benchmarks/robopaint-strict.md (Validation). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
**RoboPaint-strict** (docs/benchmarks/robopaint-strict.md): the RoboPaint task `robopaint-oil-temeraire-i00-privileged` with process rules on top of
its picture rule, so that the exemplar has to be made with strokes rather than coloured in: the brush tip's path while it presses on the main sheet with paint (`path_mm`) is at most 28100 mm (3 ×
the reference solution's 9366 mm), and at most 10 % of it lies in strokes longer than
2.5 × the diagonal of their bounding box (zigzags, back-and-forth fills, spirals, loops). Same scene, frozen instance
(the rules added to its `target.success`), picture, tooling and reference solution; the rules are applied by the graders'
`rcb_brush_strict.py` (the verifier and the scoring service).

The instance: paint the picture in `environment/target.png` (a square crop of J. M. W. Turner's The Fighting Temeraire, 1839: a public-domain masterpiece, cropped and downscaled to the 227 mm main sheet) in at most 449 strokes, with 16 premixed paints (the picture's colours quantised) on a plate and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; everything frozen in `environment/instance.json`.

Paint the picture: mean CIELAB ΔE <= 4.5, p90 ΔE <= 8.0, SSIM of L* >= 0.83, edge correlation >= 0.39, paint IoU >= 0.96 (all after the best single shift of the sheet, at most 5 mm along each axis, inside the central area 8 mm in from the sheet's edges) and at most 449 strokes. `final_reward` = max(0, 1 - mean ΔE / 20) (× 449 / strokes above 449). The thresholds are the reference solution's execution by this robot (299 strokes: mean ΔE 4.06, p90 7.08, SSIM 0.860, edge correlation 0.441, paint IoU 1.000) with a margin (ΔE x 1.1, SSIM - 0.03, edge correlation - 0.05, paint IoU - 0.03).

## Difficulty
There is no exact solution: the picture is a real painting, the paint is wet (strokes pick up and blend what is under them), the brush makes 5-11 mm marks, 16 premixed paints are all there is and the stroke budget is small. The rule is set by the reference solution executed by this robot, with a margin; the measured axes are in task.toml [metadata].

## Reference solution
The reference solution is our baseline painter's stroke program (`solution/program.json`, made at generation time by a stroke optimiser with libmypaint in the loop against the picture: a ground of parallel rows in the nearest paints, then 2 layers of curved strokes along the picture's isophotes, placed where the canvas is furthest from the picture) executed by the robot (`solution/ref_oil.py`); the rule was calibrated on exactly that execution (`solution/calibration.json`). The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
22329 control steps, 299 strokes, mean ΔE 4.057, p90 ΔE 7.084, SSIM 0.8603, paint IoU 0.9999.

## Verification
RoboPaint-strict: "the rule" below is RoboPaint's picture rule and the process rules (Task); the replays run
`tests/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
Oracle label `partial`: the RoboPaint pair's reference solution, scored under the process rules (task.toml `oracle_evidence`).
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes (`tests/grade.py`); pass iff
both replayed main sheets meet the rule, the final-state hashes (paint layers of both sheets + robot state + the loaded paint)
agree and the rebuilt frozen instance matches the recorded one. PhysX and libmypaint (single-threaded, with the image's
determinism patch) run on the CPU: a live run, in-process replays and fresh-process replays end in the same state bit for bit
(`rcb_brush.py selftest`); camera rendering does not change it. `/logs/verifier/replay.mp4` and `canvas.png` never affect the verdict.

## Details
| | |
|---|---|
| Simulator, tool and robot | ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU) + libmypaint 1.6.1 (ISC; the mypaint-brushes 2.0.2 preset `tanda/oil-03-paint`, CC0) through `rcb_brush.py`'s MyPaintPainter (CPU) / franka-panda holding a paint brush (PandaStick's rigid stick as the handle + a 15 mm collision-free tuft; TCP = the tuft's tip) |
| Base image and GPU | 0.1.1 + libmypaint + the shim + the presets. Physics and paint run on the CPU; SAPIEN still needs the NVIDIA GPU (Vulkan) to build the scene and render: `environment/docker-compose.yaml` |
