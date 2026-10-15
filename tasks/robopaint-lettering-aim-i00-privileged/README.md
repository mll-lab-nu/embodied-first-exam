# robopaint-lettering-aim-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-lettering-aim-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_lettering_aim` / seed 0 |
| Oracle | `partial` — Reference solution in solution/ (the lettering family redesigned on 2026-10-09: 臨摹 of engraved round hand; generated with the current tooling on the native eai-robopaint:0.2.0 runtime): the generator's self-test replayed it on the graders' copy and through the scoring service (equal metrics, success); under the process rules the verifier scores it 1 (tests/grade.py with rcb_brush_strict.py, two fresh replays): path_mm 998 and mark_width_mm 0.43, against the colouring-in limits 3000 mm and 0.12 mm. Harbor oracle and nop runs: docs/benchmarks/robopaint.md (Lettering). |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
**Process rules** (docs/benchmarks/robopaint.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: colouring in fails: a pen-tip path on the main sheet (`path_mm`) longer than 3000 mm (3 × the reference
solution's 998 mm) made of marks narrower than 0.12 mm on average (`mark_width_mm`: each stroke's own
inked area / `path_mm`; 0.3 × the reference's 0.43 mm). They are part of the frozen instance (the rules added to its `target.success`); the graders'
`rcb_brush_strict.py` applies them (the verifier and the scoring service).

Copy the line **Aim at improvement in every line.** (engraved English round hand, 1741) (27 letters; 臨摹 of a public-domain engraved copybook plate: Sources) shown in `environment/target.png` onto the 227 mm main sheet in at most 11 strokes (the exemplar's own pen lifts: one stroke per connected piece of its ink), with ink from an ink well and a practice sheet beside it; the pen starts dry; start pose = PandaStick's rest keyframe; the scene frozen in `environment/instance.json` (the agent's copy: scene constants, the rule, the picture).

Copy the lettering, scored against the picture: the main sheet's inked area vs the exemplar's ink. The thinnest lines are 0.4 mm,
so every term is measured after the best single shift of the sheet, at most 5 mm along each axis (the common RoboPaint registration: one translation,
whole pixels; none at the limit). Success iff IoU ≥ 0.85, boundary F (edge precision / recall within 1 mm) ≥ 0.80, every region covered ≥ 0.75 (the exemplar's ink in 54 regions of at most 30 mm along its strokes), stray ink (> 1 mm away from the exemplar's ink) ≤ 0.04 of its inked area and at most 11 strokes (inked contacts) on the
main sheet. `final_reward` = the IoU (× 11 / strokes above 11). Ink precision / recall, the plain IoU, missing ink and
the mean region coverage are reported too.

## Difficulty
臨摹 of engraved English round hand (Bickham, *The Universal Penman*, 1741), re-drawn with this pen so that every mark of the
picture is one the pen can make:
- **Pressure.** A pointed pen makes its shades from pressure: the press depth has to follow the picture's line width along every
  stroke (a light touch on the hairlines, loops and joins, a deep press on the shaded downstrokes, swelling and fading on the
  curves), while the path is tracked by a position-controlled arm (PD lag ~0.1 s, vertical as well). One constant press fails.
- **Long connected strokes.** The cap (11) is the exemplar's own pen lifts, with no margin: every connected piece of its ink
  (a whole word, a capital with its flourishes) has to be written in one contact, going back along a stroke where the route needs
  it. An extra lift fails; patching fails.
- **Every part counts.** The ink is divided into 54 regions of at most 30 mm along its strokes, each to be covered ≥ 0.75:
  hairline joins, loops and flourishes as much as the shades.

## Reference solution
Generated once on the graders' copy (`solution/ref_lettering.py` via `plan_oracle.py`): every contact of `solution/plans.json` (one
writing route per connected piece of the exemplar's ink, going back along a stroke where it has to, with the tines' spread at every
point) written with the pen turned to the exemplar's spread axis, the press depth of each point from the spread, one dip, a vertical
touch-down and lift, 2 cm/s (slower around sharp turns), lag feed-forward and iterative learning control, the arm parked at the end.
The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
7574 control steps, 11 strokes, IoU 0.956, boundary F 1.000, min stroke coverage 0.941, stray 0.0000.

## Verification
"The rule" below is the picture rule and the process rules (Task); the replays run
`tests/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
Oracle label `partial`: the reference solution, scored under the process rules (task.toml `oracle_evidence`).
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes (`tests/grade.py`); pass iff
both replayed main sheets meet the rule, the final-state hashes (ink of both sheets + robot state + pen state) agree and the
rebuilt frozen instance matches the recorded one (target picture and scoring data included). Physics is PhysX on the CPU and the pen
runs in float64 on the CPU: a live run, in-process replays and fresh-process replays end in the same state bit for bit
(`rcb_brush.py selftest`); camera rendering does not change it. `/logs/verifier/replay.mp4` and `canvas.png` never affect the
verdict.
A file that is not a readable trajectory (not an npz, no `actions`, a wrong shape, NaN, more than 72,000 rows) scores 0 as
`bad_trajectory`; `grader_error` (with `infra_error`) is left for the verifier's own failures (a replay process without a result
or past its 1650 s, a frozen instance that does not rebuild in the verifier: `instance_ok` 0).
The verifier has 3600 s: two replays of the 72,000 control steps a trajectory may have take up to 36 min at the measured
67-102 steps/s (docs/benchmarks/robopaint.md).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 0.25-0.5 GB, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: sim p90 1.7 GB, privileged container p90 2.5 GB + scorer 0.7 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial the agent drives (the benchmark's own `scorer` service is recorded only): 5 GiB GPU memory, 16 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 5 GiB GPU memory, 21 GiB memory. Limits measured: GPU: 0.5 GiB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: the [environment] cap 16 GiB, which every past trial ran under (docker peak 3.0 GiB over 73 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)); the scorer service is the benchmark's own (recorded only, not in the limits), the whole trial's expected peak adds 5 GiB for it; processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Simulator, tool and robot | ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU) + a pointed flexible pen model in `rcb_brush.py` (`PointedPenPainter`: the tines' spread along the tool's y axis grows linearly with the press depth from a 0.4 mm hairline (press ≤ 1.0 mm) to 2.0 mm (press ≥ 3.5 mm); the ink between the tines swept along the realized path; CPU) / franka-panda holding a pointed dip pen (PandaStick's rigid stick as the holder + a collision-free 6 mm steel point; TCP = the point) |
| Privileged access | exact sheets, pen state, reset / replay, `s.score()` from the scoring service |
| Containers | `main` (the agent: the tooling, the scene, the picture), `scorer` (`environment/scorer/`: the scoring service with the graders' copy of the instance; the agent reaches it only through `POST /score`, which returns metrics), the verifier's own sandbox (`tests/`) |
| Base image and GPU | 2.5 GB. Physics and the pen run on the CPU; SAPIEN still needs the NVIDIA GPU (Vulkan) to build the scene and render: `environment/docker-compose.yaml` |

### Scoring service (privileged mode)
`environment/scorer/` holds `rcb_scorer.py`, the tooling and the graders' copy of the instance; compose runs it as the `scorer`
service (GPU for SAPIEN, no ports published). `Session.score()` in the agent's container posts the actions executed since the last
reset; the service replays them on its copy (the same deterministic simulation) and returns the metrics of the tooling's
`agent_metrics()` — never images or target data. The agent's container holds nothing derived from the target except `target.png`
(`ci_checks/check-robopaint-leak.sh`).

### Licences
The exemplar is a public-domain engraved copybook plate, re-drawn by RoboPaint with the task's pen: `environment/NOTICE-exemplar.md`.

### Sources
George Bickham, *The Universal Penman* (London, 1741), engraved plates of English round hand after the writing masters named on each plate; scan: Getty Research Institute, Internet Archive item gri_33125008538056 (https://archive.org/details/gri_33125008538056; possible-copyright-status NOT_IN_COPYRIGHT; the same book on Wikimedia Commons as a DjVu file under {{PD-scan}}). Public domain: the plates were engraved 1733-1741 (Bickham d. 1758) and the scan is a faithful reproduction of a public-domain two-dimensional work. This exemplar: the first copy line of the plate 'COPIES' (page n30 of the scan, W. Clark scripsit), placed 205 mm wide on the sheet.

### Change Log
- 2026-10-10: the verifier and the scoring service only (review of 2026-10-10, board 0067). The verifier's timeout is 3600 s (was 1800 s): two fresh replays of the 72,000 control steps a trajectory may have take up to 36 min at the measured 67-102 steps/s, so a long painting timed the verifier out and the trial had no reward. A file that is not a readable trajectory (not an npz, pickled arrays, no `actions`) scores 0 as `bad_trajectory` (was `grader_error`); every `reward.json` has `deterministic`. The `scorer` service restarts if its process dies (`restart: on-failure`). The verdict of a trajectory the verifier could replay before is unchanged, and so are the instance, the picture and the rules: the task keeps its name.
- 2026-10-10 (2): `task.toml` `[agent].allowed_hosts` only. The allowlist is now the one every other allowlist task has (`scripts/set_agent_egress.py`): it gains `*.openai.azure.com` and `*.cognitiveservices.azure.com`, so that an agent whose model is served by Azure OpenAI can reach it directly (without them such an agent could not reach its model and ended as a 0 without having acted). Nothing else changes: the task keeps its name.
- 2026-10-10 (review round 2, board 0067): `tests/grade.py` only. A frozen instance that the verifier's host does not rebuild (`instance_ok = 0`) is `grader_error = 1` and `infra_error = 1` (it was a plain 0 without a flag: the replays ran on another scene and say nothing about the trajectory), and every `grader_error = 1` (a replay process without a result or past its time limit) now has `infra_error = 1` next to it; every `reward.json` carries `infra_error`. The reward is 0 in these cases, as before; the pass rule, the frozen instance and the tooling are unchanged.
- 2026-10-14 (failure analysis of 2026-10-14): the graders' `rcb_brush_strict.py`, the same file in every RoboPaint task, gained the calligraphy families' counted strokes (their own entry, where it applies); a task without those rule keys in `target.success` (lettering and the paintings) is graded exactly as before.
