# robopaint-oil-cafeterrace-i01-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-oil-cafeterrace-i01-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_oil_cafeterrace` / seed 0 |
| Oracle | `partial` — Reference solution in solution/: the stroke program for the pointed brush, executed by the robot at generation time (tasks/robopaint/README.md, Targets). The verifier scores it 1 (tests/grade.py with rcb_brush_strict.py, two fresh replays, the efe:robopaint-0.2.0 runtime, 2026-10-09): path_mm 22864 of the 68600 mm budget; its strokes are sweeps. Harbor oracle and nop runs: tasks/robopaint/README.md (Oil: the pointed brush). |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:robopaint-0.2.0` |

## Task
**Process rules** (tasks/robopaint/README.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: the brush tip's path while it presses on the main sheet with paint (`path_mm`) is at most 68600 mm (3 ×
the reference solution's 22864 mm), and at most 10 % of it lies in strokes longer than
2.5 × the diagonal of their bounding box (zigzags, back-and-forth fills, spirals, loops). They are part of the frozen instance (the rules added to its `target.success`); the graders'
`rcb_brush_strict.py` applies them (the verifier and the scoring service).

The instance: paint the picture in `/app/target.png` (a square crop of Vincent van Gogh's Cafe Terrace at Night, 1888: a public-domain masterpiece, cropped and downscaled to the 227 mm main sheet) in at most 2507 strokes, with 16 premixed paints (the picture's colours quantised) on a plate and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; everything frozen in `environment/instance.json`.

Paint the picture: mean CIELAB ΔE <= 8.0, p90 ΔE <= 13.5, SSIM of L* >= 0.66, edge correlation >= 0.57, paint IoU >= 0.96 (all after the best single shift of the sheet, at most 5 mm along each axis, inside the central area 8 mm in from the sheet's edges) and at most 2507 strokes. `final_reward` = max(0, 1 - mean ΔE / 20) (× 2507 / strokes above 2507). The thresholds are the reference solution's execution by this robot (1667 strokes: mean ΔE 7.22, p90 12.21, SSIM 0.703, edge correlation 0.626, paint IoU 1.000) with a margin (ΔE x 1.1, SSIM - 0.04, edge correlation - 0.05, paint IoU - 0.03).

## Difficulty
There is no exact solution: the picture is a real painting, the paint is wet (strokes pick up and blend what is under them), the brush makes 2-11 mm marks (the fine ones need a light, exact press), 16 premixed paints are all there is, and fine work costs robot time: the reference solution's 1667 strokes take 51 of the episode's 60 simulated minutes (61032 of the 72000 control steps). The rule is set by the reference solution executed by this robot, with a margin; the measured axes are in task.toml [metadata].

## Reference solution
The reference solution is our baseline painter's stroke program (made at generation time by a stroke optimiser with libmypaint in the loop against the picture: a ground of parallel rows in the nearest paints, then 4 layers of curved strokes along the picture's isophotes with ever lighter presses (marks of about 6, 3.6, 2.6 and 2.1 mm), placed where the canvas is furthest from the picture, each paint's strokes of a layer in a nearest-neighbour order) executed by the robot (with the program's motion settings: a 6 mm hover between strokes, quick dips, short holds); the rule was calibrated on exactly that execution: mean ΔE ≤ 8, p90 ΔE ≤ 13.5, SSIM ≥ 0.66, edge correlation ≥ 0.57 and paint IoU ≥ 0.96. The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
61032 control steps, 1667 strokes, mean ΔE 7.221, p90 ΔE 12.209, SSIM 0.7034, paint IoU 0.9997.

## Verification
"The rule" below is the picture rule and the process rules (Task); the replays run
`/tests/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
Oracle label `partial`: the reference solution, scored under the process rules (task.toml `oracle_evidence`).
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in one fresh process (`/tests/grade.py`); pass iff
the replayed main sheet meets the rule and the rebuilt frozen instance matches the recorded one.
PhysX and libmypaint (single-threaded, with the image's
determinism patch) run on the CPU: a live run, in-process replays and fresh-process replays end in the same state bit for bit
(`rcb_brush.py selftest`); camera rendering does not change it. `/logs/verifier/replay.mp4` and `canvas.png` never affect the verdict.
A file that is not a readable trajectory (not an npz, no `actions`, a wrong shape, NaN, more than 72,000 rows) scores 0 as
`bad_trajectory`; `grader_error` (with `infra_error`) is left for the verifier's own failures (a replay process without a result
or past its 1650 s, a frozen instance that does not rebuild in the verifier: `instance_ok` 0).
The verifier has 3600 s: a replay of the 72,000 control steps a trajectory may have takes up to 18 min at the measured
67-102 steps/s (tasks/robopaint/README.md).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 12 GiB | 2048 | 3 GiB | 10 GiB |
| `scorer` | 2 | 4 GiB | 1024 | 3 GiB | — |
| verifier | no cap | no cap | no cap | 3 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main` and `scorer`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## Details
| | |
|---|---|
| Simulator, tool and robot | ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU) + libmypaint 1.6.1 (ISC; the mypaint-brushes 2.0.2 preset `tanda/oil-03-paint`, CC0, made pointed: its random dab offset and tracking noise follow the pressure, frozen as `brush.preset_json`) through `rcb_brush.py`'s MyPaintPainter (CPU) / franka-panda holding a paint brush (PandaStick's rigid stick as the handle + a 15 mm collision-free tuft; TCP = the tuft's tip) |
| Base image and GPU | 0.1.1 + libmypaint + the shim + the presets. Physics and paint run on the CPU; SAPIEN still needs the NVIDIA GPU (Vulkan) to build the scene and render: `environment/docker-compose.yaml` |
