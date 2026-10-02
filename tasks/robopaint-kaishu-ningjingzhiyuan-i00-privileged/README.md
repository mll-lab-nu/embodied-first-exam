# robopaint-kaishu-ningjingzhiyuan-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-kaishu-ningjingzhiyuan-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_kaishu_ningjingzhiyuan` / seed 0 |
| Oracle | `partial` — Reference solution in solution/. Oracle 1 and nop 0 in the release validation (ws3, 2026-09-28: kaishu-u-oracle-final0928, kaishu-u-nop-final0928), on earlier scoring and tooling. Changed since: the v2 registered scoring (aaffb039: scorer and success rule; the saved oracle trajectories re-scored, all pass; Harbor oracle and nop on tiandaochouqin and yong), tooling snapshot 23 (ccb213d0: the scorer; re-scores bit-identical), the 2.2 inputs (cf95376f) and the rated limits (fe5fb9e6), both adding tooling queries only. Not re-run on this version (static validation only). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
Copy the exemplar work 寧靜致遠 (4 characters in regular script, two columns read right to left) shown in `environment/target.png` onto the 227 mm main sheet in at most 53 strokes, with ink from an ink stone and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; the scene frozen in `environment/instance.json` (the agent's copy: scene constants, the rule, the picture).

Copy the exemplar (臨帖), scored against the picture after the best single shift of the sheet, at most 5 mm along each axis (translation only): IoU of the inked areas ≥ 0.80, boundary F (edge precision / recall within
1 mm) ≥ 0.75, every stroke of the exemplar covered ≥ 0.80, stray ink (> 1 mm away from the exemplar's ink) ≤ 0.04 of its inked
area and at most 53 strokes (inked contacts) on the main sheet. `final_reward` = IoU (× 53 / strokes above 53). Ink precision /
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
9446 control steps, 53 strokes, IoU 0.854, boundary F 0.916, min stroke coverage 0.844, stray 0.0286.

## Verification
Oracle label `partial`: the recorded oracle runs predate this version's files (task.toml `oracle_evidence`); human review in PR #3.
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
