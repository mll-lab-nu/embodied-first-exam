# robopaint-acrylic-suddenshower-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-acrylic-suddenshower-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_acrylic_suddenshower` / seed 0 |
| Oracle | `partial` — Reference solution in solution/, unchanged from the earlier version of this task (the picture score only; its Harbor oracle and nop runs, and what changed since: docs/benchmarks/robopaint.md, Oracle evidence). Under the process rules the verifier scores it 1 (tests/grade.py with rcb_brush_strict.py, two fresh replays, ws3, 2026-10-05): path_mm 13495 of the 40500 mm budget; its strokes are sweeps. Harbor oracle and nop runs on one pair per family: docs/benchmarks/robopaint.md (Validation). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
**Process rules** (docs/benchmarks/robopaint.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: the brush tip's path while it presses on the main sheet with paint (`path_mm`) is at most 40500 mm (3 ×
the reference solution's 13495 mm), and at most 10 % of it lies in strokes longer than
2.5 × the diagonal of their bounding box (zigzags, back-and-forth fills, spirals, loops). They are part of the frozen instance (the rules added to its `target.success`); the graders'
`rcb_brush_strict.py` applies them (the verifier and the scoring service).

The instance: copy the painting in `environment/target.png` (a small acrylic painting after Utagawa Hiroshige's woodblock print Sudden Shower over Shin-Ohashi Bridge and Atake, 1857; the exemplar = this robot's painting of a hidden program of 292 strokes in 4 layers made by our stroke-based painting optimiser from the public-domain source) onto the 227 mm main sheet in at most 380 strokes, with 10 premixed paints on a plate and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; everything frozen in `environment/instance.json` (the brush preset's text included).

Copy the painting (笔触临摹): after the best single shift of the sheet, at most 5 mm along each axis, mean CIELAB ΔE <= 2.0, p90 ΔE <= 6.0, SSIM of L* >= 0.92, edge correlation >= 0.8, paint IoU >= 0.95 and at most 380 strokes. `final_reward` = max(0, 1 - mean ΔE / 20) (× 380 / strokes above 380).

## Difficulty
The exemplar is layered (a ground of 16 mm strokes, forms at 9 mm, details at 5 mm and 3 mm) and the paint is opaque, so later strokes hide earlier ones and the picture shows the strokes themselves. Measured on the robot with this task's grader (after the best single shift of the sheet, at most 5 mm along each axis): the whole program shifted by 2-4 mm (five offsets) passes (the worst: ΔE 0.73 / p90 1.7 / SSIM 0.977 / edge 0.96); the program at twice the speed passes (ΔE 1.15 / p90 2.9 / SSIM 0.958 / edge 0.92); these fail: the naive palette hatching (ΔE 16.93 / p90 42.3 / SSIM 0.175 / edge 0.08); the naive sheet-covering rows (ΔE 7.12 / p90 18.7 / SSIM 0.618 / edge 0.13); the program with its layers reversed (ΔE 6.29 / p90 21.5 / SSIM 0.762 / edge 0.49); a coarse-brush-only painting (16 + 9 mm brushes, the whole budget) (ΔE 6.29 / p90 16.9 / SSIM 0.628 / edge 0.17); the two most used paints swapped (ΔE 2.39 / p90 12.9 / SSIM 0.929 / edge 0.93); 20 % more press (ΔE 3.28 / p90 9.9 / SSIM 0.796 / edge 0.60). The oracle reproduces the exemplar (ΔE 0.14).

## Reference solution
The exemplar IS the robot's execution of the hidden stroke program (`solution/program.json`, `solution/ref_oil.py`: a dip whenever the paint changes, travel, touch-down, the Catmull-Rom path at its speed with the press interpolated, lift; lag feed-forward), so the oracle reproduces it exactly. The program comes from our stroke-based painting optimiser (layered coarse-to-fine greedy strokes with libmypaint in the loop, `solution/README.md`). The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
26042 control steps, 300 strokes, mean ΔE 0.145, p90 ΔE 0.265, SSIM 0.9999, paint IoU 1.0000.

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
| Simulator, tool and robot | ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU) + libmypaint 1.6.1 (ISC; the mypaint-brushes 2.0.2 preset `tanda/acrylic-03-paint`, CC0) through `rcb_brush.py`'s MyPaintPainter (CPU) / franka-panda holding a paint brush (PandaStick's rigid stick as the handle + a 15 mm collision-free tuft; TCP = the tuft's tip) |
| Base image and GPU | 0.1.1 + libmypaint + the shim + the presets. Physics and paint run on the CPU; SAPIEN still needs the NVIDIA GPU (Vulkan) to build the scene and render: `environment/docker-compose.yaml` |
