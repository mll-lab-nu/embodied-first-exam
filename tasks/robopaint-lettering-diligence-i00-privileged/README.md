# robopaint-lettering-diligence-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-lettering-diligence-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_lettering_diligence` / seed 0 |
| Oracle | `partial` — Reference solution in solution/ (the lettering family redesigned on 2026-10-09: 臨摹 of engraved round hand; generated with the current tooling on the native eai-robopaint:0.2.0 runtime): the generator's self-test replayed it on the graders' copy and through the scoring service (equal metrics, success); under the process rules the verifier scores it 1 (tests/grade.py with rcb_brush_strict.py, two fresh replays): path_mm 1343 and mark_width_mm 0.36, against the colouring-in limits 4040 mm and 0.10 mm. Harbor oracle and nop runs: docs/benchmarks/robopaint.md (Lettering). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
**Process rules** (docs/benchmarks/robopaint.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: colouring in fails: a pen-tip path on the main sheet (`path_mm`) longer than 4040 mm (3 × the reference
solution's 1343 mm) made of marks narrower than 0.10 mm on average (`mark_width_mm`: each stroke's own
inked area / `path_mm`; 0.3 × the reference's 0.36 mm). They are part of the frozen instance (the rules added to its `target.success`); the graders'
`rcb_brush_strict.py` applies them (the verifier and the scoring service).

Copy the line **Diligence in youth is commendable.** (engraved English round hand, 1741) (29 letters; 臨摹 of a public-domain engraved copybook plate: Sources) shown in `environment/target.png` onto the 227 mm main sheet in at most 11 strokes (the exemplar's own pen lifts: one stroke per connected piece of its ink), with ink from an ink well and a practice sheet beside it; the pen starts dry; start pose = PandaStick's rest keyframe; the scene frozen in `environment/instance.json` (the agent's copy: scene constants, the rule, the picture).

Copy the lettering, scored against the picture: the main sheet's inked area vs the exemplar's ink. The thinnest lines are 0.4 mm,
so every term is measured after the best single shift of the sheet, at most 5 mm along each axis (the common RoboPaint registration: one translation,
whole pixels; none at the limit). Success iff IoU ≥ 0.85, boundary F (edge precision / recall within 1 mm) ≥ 0.80, every region covered ≥ 0.75 (the exemplar's ink in 59 regions of at most 30 mm along its strokes), stray ink (> 1 mm away from the exemplar's ink) ≤ 0.04 of its inked area and at most 11 strokes (inked contacts) on the
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
- **Every part counts.** The ink is divided into 59 regions of at most 30 mm along its strokes, each to be covered ≥ 0.75:
  hairline joins, loops and flourishes as much as the shades.

## Reference solution
Generated once on the graders' copy (`solution/ref_lettering.py` via `plan_oracle.py`): every contact of `solution/plans.json` (one
writing route per connected piece of the exemplar's ink, going back along a stroke where it has to, with the tines' spread at every
point) written with the pen turned to the exemplar's spread axis, the press depth of each point from the spread, one dip, a vertical
touch-down and lift, 2 cm/s (slower around sharp turns), lag feed-forward and iterative learning control, the arm parked at the end.
The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
10262 control steps, 11 strokes, IoU 0.959, boundary F 1.000, min stroke coverage 0.923, stray 0.0000.

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
George Bickham, *The Universal Penman* (London, 1741), engraved plates of English round hand after the writing masters named on each plate; scan: Getty Research Institute, Internet Archive item gri_33125008538056 (https://archive.org/details/gri_33125008538056; possible-copyright-status NOT_IN_COPYRIGHT; the same book on Wikimedia Commons as a DjVu file under {{PD-scan}}). Public domain: the plates were engraved 1733-1741 (Bickham d. 1758) and the scan is a faithful reproduction of a public-domain two-dimensional work. This exemplar: the fourth copy line of the plate 'COPIES' (page n30 of the scan, W. Clark scripsit), placed 205 mm wide on the sheet.
