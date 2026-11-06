# robopaint-xingshu-shan-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-xingshu-shan-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_xingshu_shan` / seed 0 |
| Oracle | `partial` — Reference solution in solution/, made by the calligraphy planner (README, Reference solution; tasks/robopaint/README.md, Targets). The verifier scores it 1 under the process rules (tests/grade.py with rcb_brush_strict.py, two fresh replays): path_mm 608 and mark_width_mm 6.75, against the colouring-in limits 1200 mm and 3.06 mm. Harbor oracle 1 and nop 0 on both modes of this pair on its current files (2026-10-09): tasks/robopaint/README.md (Validation). |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:robopaint-0.2.0` |

## Task
**Process rules** (tasks/robopaint/README.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: colouring in fails: a brush-tip path on the main sheet (`path_mm`) longer than 1200 mm (3 × an earlier reference solution's 399 mm) made of marks narrower than 3.06 mm on average (`mark_width_mm`: each stroke's own
inked area / `path_mm`; 0.3 × that reference's 10.21 mm; the current reference solution: 608 mm and 6.75 mm). The cap counts strokes as written: a contact is cut where the brush moves more than 5 mm without a mark
0.1 mm wide, and a stroke longer than 1360 mm (5 × the reference's
longest, 270 mm) counts once per started 1360 mm; at most 10 % of the
path in strokes longer than 12 × their bounding box's diagonal (sweeps). They are part of the frozen instance (the rules added to its `target.success`); the graders'
`rcb_brush_strict.py` applies them (the verifier and the scoring service).

Copy the exemplar character 山 in running script shown in `/app/target.png` onto the 227 mm main sheet in at most 4 strokes, with ink from an ink stone and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; the scene frozen in `environment/instance.json` (the agent's copy: scene constants, the rule, the picture).

Copy the exemplar (臨帖), scored against the picture after the best single shift of the sheet, at most 5 mm along each axis (translation only): IoU of the inked areas ≥ 0.80, boundary F (edge precision / recall within
1 mm) ≥ 0.75, region coverage ≥ 0.80 (the exemplar's ink is divided into 5 regions; the fraction of each region covered by
your ink; the worst one counts), stray ink (> 1 mm away from the exemplar's ink) ≤ 0.04 of its inked area and at most 4 strokes
(continuous brush contacts) on the main sheet. `final_reward` = IoU (× 4 / strokes above 4). Ink precision / recall, missing
ink and the mean region coverage are reported too.

## Difficulty
The mark is not a disc under the tip: the brush model's width and drag tail grow with the press depth, the part of the tuft on the
paper stays put until the handle is up to ~11 mm away and is then dragged behind it (the mark trails the handle and cuts inside
turns), lifting releases the bend; the hairs' state carries over. Writing each stroke with the handle on the stroke's middle and
the press set by the local width (the naive plan) writes every stroke about one offset behind, loses hooks and tapers and fails the
rule by a wide margin (measured on the kaishu family). Solving it needs stroke planning against the brush dynamics and accurate tracking by a
position-controlled arm (PD lag ~0.1 s). The tooling gives only thin primitives; `s.score()`, the exact sheets and
`s.brush_state()` are privileged feedback. The stroke cap rules out filling the exemplar with many thin strokes.

## Reference solution
Generated on the graders' copy (the calligraphy planner): per
brush contact (connected strokes of the exemplar, several regions of its ink each), a robot-free trajectory optimisation against
the brush model: handle control points (x, y, press) about every 6 mm along a path through the contact's ink (several paths
tried, the best kept; one of them follows each region's ink branch by branch, rings round and side branches out and back),
initialised by inverting the trailing dynamics, scipy least_squares on the rendered contact against the exemplar with stray ink
weighted up, under-covered regions optimised again. The brush enters the paper along the stroke and leaves it back onto its own
root (回锋), with a minimum press so that every contact stays one. Then executed on the robot with lag feed-forward and
iterative learning control, a dip before every contact, the arm parked at the end. The plan is frozen at generation time
(`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
1299 control steps, 4 strokes, IoU 0.970, boundary F 0.966, min stroke coverage 0.973, stray 0.0021.

## Verification
"The rule" below is the picture rule and the process rules (Task); the replays run
`/tests/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
Oracle label `partial`: the reference solution, scored under the process rules (task.toml `oracle_evidence`).
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in one fresh process (`/tests/grade.py`); pass iff
the replayed main sheet meets the rule and the
rebuilt frozen instance matches the recorded one (target picture and scoring data included). Physics is PhysX on the CPU and the
brush runs in float64 on the CPU: a live run, in-process replays and fresh-process replays end in the same state bit for bit
(`rcb_brush.py selftest`); camera rendering does not change it. `/logs/verifier/replay.mp4` and `canvas.png` never affect the
verdict.
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
| Simulator, tool and robot | ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU) + the dynamic virtual brush of Wang et al. (IROS 2020, arXiv 1911.08002), re-implemented in `rcb_brush.py` (CPU) / franka-panda holding a Chinese writing brush (PandaStick's rigid stick as the handle + a 30 mm collision-free tuft; TCP = the tuft's tip) |
| Privileged access | exact sheets, brush state, reset / replay, `s.score()` from the scoring service |
| Containers | `main` (the agent: the tooling, the scene, the picture), `scorer` (`environment/scorer/`: the scoring service with the graders' copy of the instance; the agent reaches it only through `POST /score`, which returns metrics), the verifier's own sandbox (`tests/`) |
| Base image and GPU | 2.5 GB. Physics and the brush run on the CPU; SAPIEN still needs the NVIDIA GPU (Vulkan) to build the scene and render: `environment/docker-compose.yaml` |

### Scoring service (privileged mode)
`environment/scorer/` holds `rcb_scorer.py`, the tooling and the graders' copy of the instance; compose runs it as the `scorer`
service (GPU for SAPIEN, no ports published). `Session.score()` in the agent's container posts the actions executed since the last
reset; the service replays them on its copy (the same deterministic simulation) and returns the metrics of the tooling's
`agent_metrics()` (the rule's quantities and the continuous scores) — never images or target data. The agent's container holds
nothing derived from the target except `target.png` (`ci_checks/benchmarks/robopaint/invariant-leak.sh`).

### Sources
Wikimedia Commons, File:神龍蘭亭序全.JPG (https://commons.wikimedia.org/wiki/File:%E7%A5%9E%E9%BE%8D%E8%98%AD%E4%BA%AD%E5%BA%8F%E5%85%A8.JPG): the Shenlong hand copy (馮承素, attributed, Tang, c. 627-650, ink on paper, Palace Museum, Beijing) of Wang Xizhi's 蘭亭序 (running script, c. 353). Licence on the file page: {{PD-Art|PD-old-100-1923|deathyear=672}} (public domain). The characters were cropped from this scan (downloaded unmodified on 2026-09-28), binarised and placed on the sheet; the scroll writes 脩 for 修.

### Licences
The exemplar is a public-domain rubbing/scan of a historical work of running-script calligraphy (Wikimedia Commons, PD-Art /
PD-old; Sources above); licence notices: `environment/NOTICE-exemplar.md` (the agent's), `tests/NOTICE-exemplar.md` (the graders').
