# robopaint-kaishu-zhong-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-kaishu-zhong-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_kaishu_zhong` / seed 0 |
| Oracle | `partial` — Reference solution in solution/, unchanged from the earlier version of this task (the picture score only; its Harbor oracle and nop runs, and what changed since: docs/benchmarks/robopaint.md, Oracle evidence). Under the process rules the verifier scores it 1 (tests/grade.py with rcb_brush_strict.py, two fresh replays, ws3, 2026-10-05): path_mm 401 and mark_width_mm 6.77, against the colouring-in limits 1210 mm and 2.03 mm. Harbor oracle and nop runs on one pair per family: docs/benchmarks/robopaint.md (Validation). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
**Process rules** (docs/benchmarks/robopaint.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: colouring in fails: a brush-tip path on the main sheet (`path_mm`) longer than 1210 mm (3 × the reference
solution's 401 mm) made of marks narrower than 2.03 mm on average (`mark_width_mm`: each stroke's own
inked area / `path_mm`; 0.3 × the reference's 6.77 mm). They are part of the frozen instance (the rules added to its `target.success`); the graders'
`rcb_brush_strict.py` applies them (the verifier and the scoring service).

Copy the exemplar character 中 in regular script shown in `environment/target.png` onto the 227 mm main sheet in at most 4 strokes, with ink from an ink stone and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; the scene frozen in `environment/instance.json` (the agent's copy: scene constants, the rule, the picture).

Copy the exemplar (臨帖), scored against the picture after the best single shift of the sheet, at most 5 mm along each axis (translation only): IoU of the inked areas ≥ 0.80, boundary F (edge precision / recall within
1 mm) ≥ 0.75, every stroke of the exemplar covered ≥ 0.80, stray ink (> 1 mm away from the exemplar's ink) ≤ 0.04 of its inked
area and at most 4 strokes (inked contacts) on the main sheet. `final_reward` = IoU (× 4 / strokes above 4). Ink precision /
recall, missing ink and the mean stroke coverage are reported too.

## Difficulty
The mark is not a disc under the tip: the brush model's width and drag tail grow with the press depth, the part of the tuft on the
paper stays put until the handle is up to ~11 mm away and is then dragged behind it (the mark trails the handle and cuts inside
turns), lifting releases the bend; the hairs' state carries over. Writing each stroke with the handle on the stroke's middle and
the press set by the local width (the naive plan) writes every stroke about one offset behind, loses hooks and tapers and fails the
rule by a wide margin (DESIGN §17). Solving it needs stroke planning against the brush dynamics and accurate tracking by a
position-controlled arm (PD lag ~0.1 s). The tooling gives only thin primitives; `s.score()`, the exact sheets and
`s.brush_state()` are privileged feedback. The stroke cap rules out filling the exemplar with many thin strokes.

## Reference solution
Generated once (DESIGN §17), on the graders' copy: per stroke, a robot-free trajectory optimisation against the brush model
(handle control points (x, y, press) initialised by inverting the trailing dynamics along the stroke, scipy least_squares on the
rendered stroke), then executed on the robot with lag feed-forward and iterative learning control, a dip before every stroke, the
arm parked at the end. The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
1053 control steps, 4 strokes, IoU 0.944, boundary F 0.960, min stroke coverage 0.966, stray 0.0034.

## Verification
"The rule" below is the picture rule and the process rules (Task); the replays run
`tests/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
Oracle label `partial`: the reference solution, scored under the process rules (task.toml `oracle_evidence`).
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes (`tests/grade.py`); pass iff
both replayed main sheets meet the rule, the final-state hashes (ink of both sheets + robot state + brush state) agree and the
rebuilt frozen instance matches the recorded one (target picture and scoring data included). Physics is PhysX on the CPU and the
brush runs in float64 on the CPU: a live run, in-process replays and fresh-process replays end in the same state bit for bit
(`rcb_brush.py selftest`); camera rendering does not change it. `/logs/verifier/replay.mp4` and `canvas.png` never affect the
verdict.

## Details
| | |
|---|---|
| Simulator, tool and robot | ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU) + the dynamic virtual brush of Wang et al. (IROS 2020, arXiv 1911.08002), re-implemented in `rcb_brush.py` (CPU) / franka-panda holding a Chinese writing brush (PandaStick's rigid stick as the handle + a 30 mm collision-free tuft; TCP = the tuft's tip) |
| Privileged access | exact sheets, brush state, reset / replay, `s.score()` from the scoring service |
| Containers | `main` (the agent: the tooling, the scene, the picture), `scorer` (`environment/scorer/`: the scoring service with the graders' copy of the instance; the agent reaches it only through `POST /score`, which returns metrics), the verifier's own sandbox (`tests/`) |
| Base image and GPU | 2.5 GB. Physics and the brush run on the CPU; SAPIEN still needs the NVIDIA GPU (Vulkan) to build the scene and render: `environment/docker-compose.yaml` |

### Scoring service (privileged mode)
`environment/scorer/` holds `rcb_scorer.py`, the tooling and the graders' copy of the instance; compose runs it as the `scorer`
service (GPU for SAPIEN, no ports published). `Session.score()` in the agent's container posts the actions executed since the last
reset; the service replays them on its copy (the same deterministic simulation) and returns the metrics of the tooling's
`agent_metrics()` (the rule's quantities and the continuous scores) — never images or target data. The agent's container holds
nothing derived from the target except `target.png` (`ci_checks/check-robopaint-leak.sh`).

### Licences
The exemplar derives from the fonts AR PL KaitiM GB / AR PL UKai via Make Me a Hanzi (Arphic Public License):
`environment/ARPHICPL.TXT`, `environment/NOTICE-exemplar.md`.
