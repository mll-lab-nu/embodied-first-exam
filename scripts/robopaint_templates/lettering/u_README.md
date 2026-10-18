# {{NAME}}-privileged

## Task
Copy {{TASK_MD}} ({{NLETTERS}} letters; 臨摹 of a public-domain engraved copybook plate: Sources) shown in `environment/target.png` onto the 227 mm main sheet in at most {{N}} strokes (the exemplar's own pen lifts: one stroke per connected piece of its ink), with ink from an ink well and a practice sheet beside it; the pen starts dry; start pose = PandaStick's rest keyframe; the scene frozen in `environment/instance.json` (the agent's copy: scene constants, the rule, the picture).

Copy the lettering, scored against the picture: the main sheet's inked area vs the exemplar's ink. The thinnest lines are 0.4 mm,
so every term is measured after the best single shift of the sheet, at most 5 mm along each axis (the common RoboPaint registration: one translation,
whole pixels; none at the limit). Success iff IoU ≥ {{IOU}}, boundary F (edge precision / recall within 1 mm) ≥ 0.80, every region covered ≥ 0.75 (the exemplar's ink in {{NREG}} regions of at most 30 mm along its strokes), stray ink (> 1 mm away from the exemplar's ink) ≤ 0.04 of its inked area and at most {{N}} strokes (inked contacts) on the
main sheet. `final_reward` = the IoU (× {{N}} / strokes above {{N}}). Ink precision / recall, the plain IoU, missing ink and
the mean region coverage are reported too.

## Difficulty
臨摹 of engraved English round hand (Bickham, *The Universal Penman*, 1741), re-drawn with this pen so that every mark of the
picture is one the pen can make:
- **Pressure.** A pointed pen makes its shades from pressure: the press depth has to follow the picture's line width along every
  stroke (a light touch on the hairlines, loops and joins, a deep press on the shaded downstrokes, swelling and fading on the
  curves), while the path is tracked by a position-controlled arm (PD lag ~0.1 s, vertical as well). One constant press fails.
- **Long connected strokes.** The cap ({{N}}) is the exemplar's own pen lifts, with no margin: every connected piece of its ink
  (a whole word, a capital with its flourishes) has to be written in one contact, going back along a stroke where the route needs
  it. An extra lift fails; patching fails.
- **Every part counts.** The ink is divided into {{NREG}} regions of at most 30 mm along its strokes, each to be covered ≥ 0.75:
  hairline joins, loops and flourishes as much as the shades.

## Reference solution
Generated once on the graders' copy (`solution/ref_lettering.py` via `plan_oracle.py`): every contact of `solution/plans.json` (one
writing route per connected piece of the exemplar's ink, going back along a stroke where it has to, with the tines' spread at every
point) written with the pen turned to the exemplar's spread axis, the press depth of each point from the spread, one dip, a vertical
touch-down and lift, 2 cm/s (slower around sharp turns), lag feed-forward and iterative learning control, the arm parked at the end.
The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
ORACLE_STATS

## Verification
Oracle label `{{ORACLE}}`: the recorded oracle runs predate this version's files (task.toml `oracle_evidence`); human review in PR #3.
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
{{SOURCES}}
