# robopaint-oil-pearlearring-i01-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-oil-pearlearring-i01-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_oil_pearlearring` / seed 0 |
| Oracle | `partial` — Reference solution in solution/: the hi-res version's stroke program for the pointed brush, executed by the robot at generation time (2026-10-09; README Change Log). The verifier scores it 1 (tests/grade.py with rcb_brush_strict.py, two fresh replays, the eai-robopaint:0.2.0 runtime, 2026-10-09): path_mm 28809 of the 86500 mm budget; its strokes are sweeps. Harbor oracle and nop runs: docs/benchmarks/robopaint.md (Oil: the pointed brush). |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robopaint-0.2.0` |

## Task
**Process rules** (docs/benchmarks/robopaint.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: the brush tip's path while it presses on the main sheet with paint (`path_mm`) is at most 86500 mm (3 ×
the reference solution's 28809 mm), and at most 10 % of it lies in strokes longer than
2.5 × the diagonal of their bounding box (zigzags, back-and-forth fills, spirals, loops). They are part of the frozen instance (the rules added to its `target.success`); the graders'
`rcb_brush_strict.py` applies them (the verifier and the scoring service).

The instance: paint the picture in `environment/target.png` (a square crop of Johannes Vermeer's Girl with a Pearl Earring, c. 1665: a public-domain masterpiece, cropped and downscaled to the 227 mm main sheet) in at most 2453 strokes, with 16 premixed paints (the picture's colours quantised) on a plate and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; everything frozen in `environment/instance.json`.

Paint the picture: mean CIELAB ΔE <= 4.4, p90 ΔE <= 8.5, SSIM of L* >= 0.84, edge correlation >= 0.76, paint IoU >= 0.96 (all after the best single shift of the sheet, at most 5 mm along each axis, inside the central area 8 mm in from the sheet's edges) and at most 2453 strokes. `final_reward` = max(0, 1 - mean ΔE / 20) (× 2453 / strokes above 2453). The thresholds are the reference solution's execution by this robot (1638 strokes: mean ΔE 3.98, p90 7.59, SSIM 0.884, edge correlation 0.813, paint IoU 1.000) with a margin (ΔE x 1.1, SSIM - 0.04, edge correlation - 0.05, paint IoU - 0.03).

## Difficulty
There is no exact solution: the picture is a real painting, the paint is wet (strokes pick up and blend what is under them), the brush makes 2-11 mm marks (the fine ones need a light, exact press), 16 premixed paints are all there is, and fine work costs robot time: the reference solution's 1638 strokes take 52 of the episode's 60 simulated minutes (62015 of the 72000 control steps). The rule is set by the reference solution executed by this robot, with a margin; the measured axes are in task.toml [metadata].

## Reference solution
The reference solution is our baseline painter's stroke program (`solution/program.json`, made at generation time by a stroke optimiser with libmypaint in the loop against the picture: a ground of parallel rows in the nearest paints, then 4 layers of curved strokes along the picture's isophotes with ever lighter presses (marks of about 6, 3.6, 2.6 and 2.1 mm), placed where the canvas is furthest from the picture, each paint's strokes of a layer in a nearest-neighbour order) executed by the robot (`solution/ref_oil.py` with the program's `motion`: a 6 mm hover between strokes, quick dips, short holds); the rule was calibrated on exactly that execution (`solution/calibration.json`). The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
62015 control steps, 1638 strokes, mean ΔE 3.984, p90 ΔE 7.593, SSIM 0.8842, paint IoU 0.9998.

## Verification
"The rule" below is the picture rule and the process rules (Task); the replays run
`/tests/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
Oracle label `partial`: the reference solution, scored under the process rules (task.toml `oracle_evidence`).
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes (`/tests/grade.py`); pass iff
both replayed main sheets meet the rule, the final-state hashes (paint layers of both sheets + robot state + the loaded paint)
agree and the rebuilt frozen instance matches the recorded one. PhysX and libmypaint (single-threaded, with the image's
determinism patch) run on the CPU: a live run, in-process replays and fresh-process replays end in the same state bit for bit
(`rcb_brush.py selftest`); camera rendering does not change it. `/logs/verifier/replay.mp4` and `canvas.png` never affect the verdict.
A file that is not a readable trajectory (not an npz, no `actions`, a wrong shape, NaN, more than 72,000 rows) scores 0 as
`bad_trajectory`; `grader_error` (with `infra_error`) is left for the verifier's own failures (a replay process without a result
or past its 1650 s, a frozen instance that does not rebuild in the verifier: `instance_ok` 0).
The verifier has 3600 s: two replays of the 72,000 control steps a trajectory may have take up to 36 min at the measured
67-102 steps/s (docs/benchmarks/robopaint.md).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 0.25-0.5 GB, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: sim p90 1.7 GB, privileged container p90 2.5 GB + scorer 0.7 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial the agent drives (the benchmark's own `scorer` service is recorded only): 5 GiB GPU memory, 16 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 5 GiB GPU memory, 21 GiB memory. Limits measured: GPU: 0.5 GiB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: the [environment] cap 16 GiB, which every past trial ran under (docker peak 3.0 GiB over 73 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)); the scorer service is the benchmark's own (recorded only, not in the limits), the whole trial's expected peak adds 5 GiB for it; processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Simulator, tool and robot | ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU) + libmypaint 1.6.1 (ISC; the mypaint-brushes 2.0.2 preset `tanda/oil-03-paint`, CC0, made pointed: its random dab offset and tracking noise follow the pressure, frozen as `brush.preset_json`) through `rcb_brush.py`'s MyPaintPainter (CPU) / franka-panda holding a paint brush (PandaStick's rigid stick as the handle + a 15 mm collision-free tuft; TCP = the tuft's tip) |
| Base image and GPU | 0.1.1 + libmypaint + the shim + the presets. Physics and paint run on the CPU; SAPIEN still needs the NVIDIA GPU (Vulkan) to build the scene and render: `environment/docker-compose.yaml` |

### Change Log
- 2026-10-09: the hi-res version (docs/benchmarks/robopaint.md, Oil: the pointed brush). The brush is `tanda/oil-03-paint` made pointed: a light press draws a 2-3 mm line (before, every mark was 5-11 mm wide). The reference solution is a new program of 1635 strokes (was 300); executed by the robot it scores mean ΔE 3.98, SSIM 0.884 and edge correlation 0.813 against the picture (was 5.16, 0.802, 0.661). The rule is recalibrated on it with the same margins, except SSIM - 0.04 (was - 0.03): mean ΔE <= 4.4 (was 5.7), p90 ΔE <= 8.5 (was 12.5), SSIM >= 0.84 (was 0.77), edge correlation >= 0.76 (was 0.61); at most 2453 strokes (was 450); a path of at most 86500 mm (was 34700 mm). The picture, the scene's geometry and the scoring code are unchanged; results before this date are not comparable with this version.
- 2026-10-10: the verifier and the scoring service only (review of 2026-10-10, board 0067). The verifier's timeout is 3600 s (was 1800 s): two fresh replays of the 72,000 control steps a trajectory may have take up to 36 min at the measured 67-102 steps/s, so a long painting timed the verifier out and the trial had no reward. A file that is not a readable trajectory (not an npz, pickled arrays, no `actions`) scores 0 as `bad_trajectory` (was `grader_error`); every `reward.json` has `deterministic`. The `scorer` service restarts if its process dies (`restart: on-failure`). The verdict of a trajectory the verifier could replay before is unchanged, and so are the instance, the picture and the rules: the task keeps its name.
- 2026-10-10 (2): `task.toml` `[agent].allowed_hosts` only. The allowlist is now the one every other allowlist task has (`scripts/set_agent_egress.py`): it gains `*.openai.azure.com` and `*.cognitiveservices.azure.com`, so that an agent whose model is served by Azure OpenAI can reach it directly (without them such an agent could not reach its model and ended as a 0 without having acted). Nothing else changes: the task keeps its name.
- 2026-10-10 (review round 2, board 0067): `tests/grade.py` only. A frozen instance that the verifier's host does not rebuild (`instance_ok = 0`) is `grader_error = 1` and `infra_error = 1` (it was a plain 0 without a flag: the replays ran on another scene and say nothing about the trajectory), and every `grader_error = 1` (a replay process without a result or past its time limit) now has `infra_error = 1` next to it; every `reward.json` carries `infra_error`. The reward is 0 in these cases, as before; the pass rule, the frozen instance and the tooling are unchanged.
- 2026-10-14 (failure analysis of 2026-10-14): the graders' `rcb_brush_strict.py`, the same file in every RoboPaint task, gained the calligraphy families' counted strokes (their own entry, where it applies); a task without those rule keys in `target.success` (lettering and the paintings) is graded exactly as before.
