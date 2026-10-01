# robopaint-acrylic-vision-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-acrylic-vision-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_acrylic_vision` / seed 0 |
| Oracle | `partial` — Reference solution in solution/. Oracle 1 and nop 0 in the release validation (ws3, 2026-09-28: acrylic-u-oracle-final0928, acrylic-u-nop-final0928), on earlier scoring and tooling. Changed since: the v2 registered scoring (8bc4fc0c: scorer and success rule; the saved oracle trajectories re-scored, all pass; Harbor oracle and nop on applesoranges and redfuji), tooling snapshot 23 (ccb213d0: the scorer; re-scores bit-identical), the 2.2 inputs (cf95376f) and the rated limits (fe5fb9e6), both adding tooling queries only. Not re-run on this version (static validation only). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/embodied-agent-interface-v2-internal/eai-robopaint:0.2.0` |

## Task
The instance: copy the painting in `environment/target.png` (a small acrylic painting after Paul Gauguin's Vision after the Sermon, 1888; the exemplar = this robot's painting of a hidden program of 300 strokes in 4 layers made by our stroke-based painting optimiser from the public-domain source) onto the 227 mm main sheet in at most 390 strokes, with 10 premixed paints on a plate and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; everything frozen in `environment/instance.json` (the brush preset's text included).

Copy the painting (笔触临摹): after the best single shift of the sheet, at most 5 mm along each axis, mean CIELAB ΔE <= 2.0, p90 ΔE <= 6.0, SSIM of L* >= 0.92, edge correlation >= 0.8, paint IoU >= 0.95 and at most 390 strokes. `final_reward` = max(0, 1 - mean ΔE / 20) (× 390 / strokes above 390).

## Difficulty
The exemplar is layered (a ground of 16 mm strokes, forms at 9 mm, details at 5 mm and 3 mm) and the paint is opaque, so later strokes hide earlier ones and the picture shows the strokes themselves. Measured on the robot with this task's grader (after the best single shift of the sheet, at most 5 mm along each axis): the whole program shifted by 2-4 mm (five offsets) passes (the worst: ΔE 1.21 / p90 3.1 / SSIM 0.968 / edge 0.95); the program at twice the speed fails (ΔE 2.11 / p90 5.3 / SSIM 0.939 / edge 0.90); these fail: the naive palette hatching (ΔE 31.64 / p90 70.5 / SSIM 0.087 / edge 0.00); the naive sheet-covering rows (ΔE 13.38 / p90 29.0 / SSIM 0.517 / edge 0.06); the program with its layers reversed (ΔE 10.52 / p90 33.9 / SSIM 0.712 / edge 0.62); a coarse-brush-only painting (16 + 9 mm brushes, the whole budget) (ΔE 10.97 / p90 27.3 / SSIM 0.587 / edge 0.25); the two most used paints swapped (ΔE 13.02 / p90 61.7 / SSIM 0.848 / edge 0.90); 20 % more press (ΔE 6.00 / p90 17.3 / SSIM 0.735 / edge 0.43). The oracle reproduces the exemplar (ΔE 0.13).

## Reference solution
The exemplar IS the robot's execution of the hidden stroke program (`solution/program.json`, `solution/ref_oil.py`: a dip whenever the paint changes, travel, touch-down, the Catmull-Rom path at its speed with the press interpolated, lift; lag feed-forward), so the oracle reproduces it exactly. The program comes from our stroke-based painting optimiser (layered coarse-to-fine greedy strokes with libmypaint in the loop, `solution/README.md`). The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
31753 control steps, 316 strokes, mean ΔE 0.133, p90 ΔE 0.244, SSIM 0.9999, paint IoU 1.0000.

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
| Simulator, tool and robot | ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU) + libmypaint 1.6.1 (ISC; the mypaint-brushes 2.0.2 preset `tanda/acrylic-03-paint`, CC0) through `rcb_brush.py`'s MyPaintPainter (CPU) / franka-panda holding a paint brush (PandaStick's rigid stick as the handle + a 15 mm collision-free tuft; TCP = the tuft's tip) |
| Base image and GPU | 0.1.1 + libmypaint + the shim + the presets. Physics and paint run on the CPU; SAPIEN still needs the NVIDIA GPU (Vulkan) to build the scene and render: `environment/docker-compose.yaml` |
