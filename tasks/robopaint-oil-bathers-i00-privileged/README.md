# robopaint-oil-bathers-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-oil-bathers-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_oil_bathers` / seed 0 |
| Oracle | `partial` — Reference solution in solution/. Oracle 1 and nop 0 in the release validation (ws3, 2026-09-28: oil-u-oracle-final0928, oil-u-nop-final0928), on earlier scoring and tooling. Changed since: the v2 registered scoring (cc866ac9: scorer and success rule; the saved oracle trajectories re-scored, all pass; Harbor oracle and nop on irises and pearlearring), the 2.2 inputs (cf95376f) and the rated limits (fe5fb9e6), both adding tooling queries only. Not re-run on this version (static validation only). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
The instance: paint the picture in `environment/target.png` (a square crop of Georges Seurat's Bathers at Asnières, 1884: a public-domain masterpiece, cropped and downscaled to the 227 mm main sheet) in at most 449 strokes, with 16 premixed paints (the picture's colours quantised) on a plate and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; everything frozen in `environment/instance.json`.

Paint the picture: mean CIELAB ΔE <= 7.1, p90 ΔE <= 13.0, SSIM of L* >= 0.71, edge correlation >= 0.5, paint IoU >= 0.96 (all after the best single shift of the sheet, at most 5 mm along each axis, inside the central area 8 mm in from the sheet's edges) and at most 449 strokes. `final_reward` = max(0, 1 - mean ΔE / 20) (× 449 / strokes above 449). The thresholds are the reference solution's execution by this robot (304 strokes: mean ΔE 6.43, p90 11.47, SSIM 0.743, edge correlation 0.553, paint IoU 1.000) with a margin (ΔE x 1.1, SSIM - 0.03, edge correlation - 0.05, paint IoU - 0.03).

## Difficulty
There is no exact solution: the picture is a real painting, the paint is wet (strokes pick up and blend what is under them), the brush makes 5-11 mm marks, 16 premixed paints are all there is and the stroke budget is small. The rule is set by the reference solution executed by this robot, with a margin; the measured axes are in task.toml [metadata].

## Reference solution
The reference solution is our baseline painter's stroke program (`solution/program.json`, made at generation time by a stroke optimiser with libmypaint in the loop against the picture: a ground of parallel rows in the nearest paints, then 2 layers of curved strokes along the picture's isophotes, placed where the canvas is furthest from the picture) executed by the robot (`solution/ref_oil.py`); the rule was calibrated on exactly that execution (`solution/calibration.json`). The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
22930 control steps, 304 strokes, mean ΔE 6.426, p90 ΔE 11.469, SSIM 0.7429, paint IoU 0.9999.

## Verification
Oracle label `partial`: the recorded oracle runs predate this version's files (task.toml `oracle_evidence`); human review in PR #3.
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
