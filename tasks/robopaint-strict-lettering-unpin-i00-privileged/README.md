# robopaint-strict-lettering-unpin-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint-strict |
| Mode | privileged |
| Twin | `robopaint-strict-lettering-unpin-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_strict_lettering_unpin` / seed 0 |
| Oracle | `partial` — The RoboPaint pair's reference solution, unchanged (solution/; its RoboPaint record: the oracle_evidence of robopaint-lettering-unpin-i00-privileged). Under the process rules the strict verifier scores it 1 (tests/grade.py with rcb_brush_strict.py, two fresh replays, ws3, 2026-10-05): path_mm 317 and mark_width_mm 2.59, against the colouring-in limits 960 mm and 0.77 mm. Harbor oracle and nop runs on one pair per family: docs/benchmarks/robopaint-strict.md (Validation). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
**RoboPaint-strict** (docs/benchmarks/robopaint-strict.md): the RoboPaint task `robopaint-lettering-unpin-i00-privileged` with process rules on top of
its picture rule, so that the exemplar has to be made with strokes rather than coloured in: colouring in fails: a pen-tip path on the main sheet (`path_mm`) longer than 960 mm (3 × the reference
solution's 317 mm) made of marks narrower than 0.77 mm on average (`mark_width_mm`: each stroke's own
inked area / `path_mm`; 0.3 × the reference's 2.59 mm). Same scene, frozen instance
(the rules added to its `target.success`), picture, tooling and reference solution; the rules are applied by the graders'
`rcb_brush_strict.py` (the verifier and the scoring service).

Copy the lettering (italic hand, 5 letters; letterforms authored for the benchmark, CC0) shown in `environment/target.png` onto the 227 mm main sheet in at most 8 strokes, with ink from an ink well and a practice sheet beside it; the pen starts dry; start pose = PandaStick's rest keyframe; the scene frozen in `environment/instance.json` (the agent's copy: scene constants, the rule, the picture).

Copy the lettering, scored against the picture: the main sheet's inked area vs the exemplar's ink. The thinnest lines are 0.4 mm,
so every term is measured after the best single shift of the sheet, at most 5 mm along each axis (the common RoboPaint registration: one translation,
whole pixels; none at the limit). Success iff IoU ≥ 0.86, boundary F (edge precision / recall within 1 mm) ≥ 0.80, every stroke of the exemplar covered ≥ 0.75, stray ink (> 1 mm away from the exemplar's ink) ≤ 0.04 of its inked area and at most 8 strokes (inked contacts) on the
main sheet. `final_reward` = the IoU (× 8 / strokes above 8). Ink precision / recall, the plain IoU, missing ink and
the mean stroke coverage are reported too.

## Difficulty
A broad nib makes thick and thin strokes from the direction of travel relative to its edge, so the robot has to hold the right
pen angle with its wrist (joint 7) along the whole word; the picture is the only source of it. Writing the right paths with
the pen kept at the start pose or at a guessed 45° fails the rule (measured: NOTES of the lettering family); the paths must be
read from the picture and tracked by a position-controlled arm (PD lag ~0.1 s); the stroke cap (8) rules out patching.

## Reference solution
Generated once on the graders' copy (`solution/ref_lettering.py` via `plan_oracle.py`): every stroke of the exemplar written along
its pen path with the tool turned to the stroke's pen orientation, a dip first,
a vertical touch-down, 2 cm/s, lag feed-forward and iterative learning control, the arm parked at the end. The plan is frozen at
generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
790 control steps, 8 strokes, IoU 0.907, boundary F 0.994, min stroke coverage 0.940, stray 0.0014.

## Verification
RoboPaint-strict: "the rule" below is RoboPaint's picture rule and the process rules (Task); the replays run
`tests/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
Oracle label `partial`: the RoboPaint pair's reference solution, scored under the process rules (task.toml `oracle_evidence`).
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes (`tests/grade.py`); pass iff
both replayed main sheets meet the rule, the final-state hashes (ink of both sheets + robot state + pen state) agree and the
rebuilt frozen instance matches the recorded one (target picture and scoring data included). Physics is PhysX on the CPU and the pen
runs in float64 on the CPU: a live run, in-process replays and fresh-process replays end in the same state bit for bit
(`rcb_brush.py selftest`); camera rendering does not change it. `/logs/verifier/replay.mp4` and `canvas.png` never affect the
verdict.

## Details
| | |
|---|---|
| Simulator, tool and robot | ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU) + a broad-edge nib model in `rcb_brush.py` (`NibPainter`: the contacting part of a 4 mm chisel edge, 0.4 mm thick, swept along the realized path; CPU) / franka-panda holding a dip pen (PandaStick's rigid stick as the holder + a 4 mm steel nib, collision-free, 6 mm long; TCP = the middle of the writing edge, which lies along the tool's y axis) |
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
The exemplar's letterforms were authored for this benchmark (CC0-1.0): `environment/NOTICE-exemplar.md`.
