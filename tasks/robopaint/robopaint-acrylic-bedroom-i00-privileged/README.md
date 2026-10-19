# robopaint-acrylic-bedroom-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-acrylic-bedroom-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_acrylic_bedroom` / seed 0 |
| Oracle | `partial` — Reference solution in solution/, unchanged from the earlier version of this task (the picture score only; its Harbor oracle and nop runs, and what changed since: tasks/robopaint/README.md, Oracle evidence). Under the process rules the verifier scores it 1 (tests/grade.py with rcb_brush_strict.py, two fresh replays, ws3, 2026-10-05): path_mm 13415 of the 40300 mm budget; its strokes are sweeps. Harbor oracle and nop runs on one pair per family: tasks/robopaint/README.md (Validation). |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robopaint-0.2.0` |

## Task
**Process rules** (tasks/robopaint/README.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: the brush tip's path while it presses on the main sheet with paint (`path_mm`) is at most 40300 mm (3 ×
the reference solution's 13415 mm), and at most 10 % of it lies in strokes longer than
2.5 × the diagonal of their bounding box (zigzags, back-and-forth fills, spirals, loops). They are part of the frozen instance (the rules added to its `target.success`); the graders'
`rcb_brush_strict.py` applies them (the verifier and the scoring service).

The instance: copy the painting in `/app/target.png` (a small acrylic painting after Vincent van Gogh's The Bedroom, 1888; the exemplar = this robot's painting of a hidden program of 298 strokes in 4 layers made by our stroke-based painting optimiser from the public-domain source) onto the 227 mm main sheet in at most 388 strokes, with 10 premixed paints on a plate and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; everything frozen in `environment/instance.json` (the brush preset's text included).

Copy the painting (笔触临摹): after the best single shift of the sheet, at most 5 mm along each axis, mean CIELAB ΔE <= 2.0, p90 ΔE <= 6.0, SSIM of L* >= 0.92, edge correlation >= 0.8, paint IoU >= 0.95 and at most 388 strokes. `final_reward` = max(0, 1 - mean ΔE / 20) (× 388 / strokes above 388).

## Difficulty
The exemplar is layered (a ground of 16 mm strokes, forms at 9 mm, details at 5 mm and 3 mm) and the paint is opaque, so later strokes hide earlier ones and the picture shows the strokes themselves. Measured on the robot with this task's grader (after the best single shift of the sheet, at most 5 mm along each axis): the whole program shifted by 2-4 mm (five offsets) passes (the worst: ΔE 0.83 / p90 2.1 / SSIM 0.978 / edge 0.96); the program at twice the speed passes (ΔE 1.52 / p90 3.8 / SSIM 0.945 / edge 0.88); these fail: the naive palette hatching (ΔE 26.33 / p90 54.9 / SSIM 0.075 / edge 0.04); the naive sheet-covering rows (ΔE 7.98 / p90 20.0 / SSIM 0.637 / edge -0.02); the program with its layers reversed (ΔE 6.76 / p90 20.8 / SSIM 0.775 / edge 0.70); a coarse-brush-only painting (16 + 9 mm brushes, the whole budget) (ΔE 6.37 / p90 18.0 / SSIM 0.701 / edge 0.29); the two most used paints swapped (ΔE 6.70 / p90 21.0 / SSIM 0.931 / edge 0.92); 20 % more press (ΔE 3.36 / p90 9.5 / SSIM 0.816 / edge 0.50). The oracle reproduces the exemplar (ΔE 0.15).

## Reference solution
The exemplar IS the robot's execution of the hidden stroke program (`solution/program.json`, `solution/ref_oil.py`: a dip whenever the paint changes, travel, touch-down, the Catmull-Rom path at its speed with the press interpolated, lift; lag feed-forward), so the oracle reproduces it exactly. The program comes from our stroke-based painting optimiser (layered coarse-to-fine greedy strokes with libmypaint in the loop, `solution/README.md`). The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
26395 control steps, 314 strokes, mean ΔE 0.146, p90 ΔE 0.275, SSIM 0.9999, paint IoU 1.0000.

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
67-102 steps/s (tasks/robopaint/README.md).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 0.25-0.5 GB, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: sim p90 1.7 GB, privileged container p90 2.5 GB + scorer 0.7 GB, mem_guard (docker memory per container, 4090-ws1, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial the agent drives (the benchmark's own `scorer` service is recorded only): 5 GiB GPU memory, 16 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 5 GiB GPU memory, 21 GiB memory. Limits measured: GPU: 0.5 GiB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: the [environment] cap 16 GiB, which every past trial ran under (docker peak 3.0 GiB over 73 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, 4090-ws1, 10-02..10)); the scorer service is the benchmark's own (recorded only, not in the limits), the whole trial's expected peak adds 5 GiB for it; processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Simulator, tool and robot | ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU) + libmypaint 1.6.1 (ISC; the mypaint-brushes 2.0.2 preset `tanda/acrylic-03-paint`, CC0) through `rcb_brush.py`'s MyPaintPainter (CPU) / franka-panda holding a paint brush (PandaStick's rigid stick as the handle + a 15 mm collision-free tuft; TCP = the tuft's tip) |
| Base image and GPU | 0.1.1 + libmypaint + the shim + the presets. Physics and paint run on the CPU; SAPIEN still needs the NVIDIA GPU (Vulkan) to build the scene and render: `environment/docker-compose.yaml` |

### Change Log
- 2026-10-10: the verifier and the scoring service only (review of 2026-10-10, board 0067). The verifier's timeout is 3600 s (was 1800 s): two fresh replays of the 72,000 control steps a trajectory may have take up to 36 min at the measured 67-102 steps/s, so a long painting timed the verifier out and the trial had no reward. A file that is not a readable trajectory (not an npz, pickled arrays, no `actions`) scores 0 as `bad_trajectory` (was `grader_error`); every `reward.json` has `deterministic`. The `scorer` service restarts if its process dies (`restart: on-failure`). The verdict of a trajectory the verifier could replay before is unchanged, and so are the instance, the picture and the rules: the task keeps its name.
- 2026-10-10 (2): `task.toml` `[agent].allowed_hosts` only. The allowlist is now the one every other allowlist task has (`scripts/set_agent_egress.py`): it gains `*.openai.azure.com` and `*.cognitiveservices.azure.com`, so that an agent whose model is served by Azure OpenAI can reach it directly (without them such an agent could not reach its model and ended as a 0 without having acted). Nothing else changes: the task keeps its name.
- 2026-10-10 (review round 2, board 0067): `tests/grade.py` only. A frozen instance that the verifier's host does not rebuild (`instance_ok = 0`) is `grader_error = 1` and `infra_error = 1` (it was a plain 0 without a flag: the replays ran on another scene and say nothing about the trajectory), and every `grader_error = 1` (a replay process without a result or past its time limit) now has `infra_error = 1` next to it; every `reward.json` carries `infra_error`. The reward is 0 in these cases, as before; the pass rule, the frozen instance and the tooling are unchanged.
- 2026-10-14 (failure analysis of 2026-10-14): the graders' `rcb_brush_strict.py`, the same file in every RoboPaint task, gained the calligraphy families' counted strokes (their own entry, where it applies); a task without those rule keys in `target.success` (lettering and the paintings) is graded exactly as before.
