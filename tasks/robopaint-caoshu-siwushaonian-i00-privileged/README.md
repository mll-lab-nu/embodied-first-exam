# robopaint-caoshu-siwushaonian-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-caoshu-siwushaonian-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_caoshu_siwushaonian` / seed 0 |
| Oracle | `partial` — Reference solution in solution/ (a new family, generated on 2026-10-09 with the current tooling): the generator's self-test replayed it on the graders' copy and through the scoring service (equal metrics, success); under the process rules the verifier scores it 1 (tests/grade.py with rcb_brush_strict.py, two fresh replays): path_mm 641 and mark_width_mm 2.66, against the colouring-in limits 1930 mm and 0.79 mm. Harbor oracle and nop runs: docs/benchmarks/robopaint.md (Caoshu). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
**Process rules** (docs/benchmarks/robopaint.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: colouring in fails: a brush-tip path on the main sheet (`path_mm`) longer than 1930 mm (3 × the reference
solution's 641 mm) made of marks narrower than 0.79 mm on average (`mark_width_mm`: each stroke's own
inked area / `path_mm`; 0.3 × the reference's 2.66 mm). They are part of the frozen instance (the rules added to its `target.success`); the graders'
`rcb_brush_strict.py` applies them (the verifier and the scoring service).

Copy the exemplar work 四五少年 (4 characters in cursive script, one column read top to bottom) shown in `environment/target.png` onto the 227 mm main sheet in at most 8 strokes, with ink from an ink stone and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; the scene frozen in `environment/instance.json` (the agent's copy: scene constants, the rule, the picture).

Copy the exemplar (臨帖), scored against the picture after the best single shift of the sheet, at most 5 mm along each axis (translation only): IoU of the inked areas ≥ 0.80, boundary F (edge precision / recall within
1 mm) ≥ 0.75, region coverage ≥ 0.80 (the exemplar's ink is divided into 20 regions; the fraction of each region covered by
your ink; the worst one counts), stray ink (> 1 mm away from the exemplar's ink) ≤ 0.04 of its inked area and at most 8 strokes
(continuous brush contacts) on the main sheet. `final_reward` = IoU (× 8 / strokes above 8). Ink precision / recall, missing
ink and the mean region coverage are reported too.

## Difficulty
The mark is not a disc under the tip: the brush model's width and drag tail grow with the press depth, the part of the tuft on the
paper stays put until the handle is up to ~11 mm away and is then dragged behind it (the mark trails the handle and cuts inside
turns), lifting releases the bend; the hairs' state carries over. Writing each stroke with the handle on the stroke's middle and
the press set by the local width (the naive plan) writes every stroke about one offset behind, loses hooks and tapers and fails the
rule by a wide margin (measured on the kaishu family, DESIGN §17). Solving it needs stroke planning against the brush dynamics and accurate tracking by a
position-controlled arm (PD lag ~0.1 s). The tooling gives only thin primitives; `s.score()`, the exact sheets and
`s.brush_state()` are privileged feedback. The stroke cap rules out filling the exemplar with many thin strokes.

Cursive (草书) adds what the regular and running families do not ask for: the cap (8) is the number of continuous brush contacts
the exemplar's ink itself shows, so wherever the ink is connected the brush has to stay on the paper, through sharp turns, loops,
crossings of the stroke over itself and the thin ligatures between strokes (and between the characters of a work), changing the
press continuously from full strokes to hairlines on the way. A contact is long (several strokes of a regular hand in one), so the
trailing of the tuft has to be planned around every turn, and an error early in a contact cannot be fixed by lifting.
The exemplar's ink is divided along each contact into 20 regions of at most about 30 mm, so every part of a long stroke has
to be covered, not only most of it.

## Reference solution
Generated once (the kaishu oracle, DESIGN §17, one plan per contact), on the graders' copy: per continuous brush contact of the
exemplar (its connected ink, written without a lift), a robot-free trajectory optimisation against the brush model (handle control
points (x, y, press) every 7 mm of path, initialised by inverting the trailing dynamics along the contact, scipy least_squares on
the rendered contact against all of its regions), then executed on the robot with lag feed-forward and iterative learning control,
a dip before every contact, the arm parked at the end. The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
1971 control steps, 8 strokes, IoU 0.894, boundary F 0.978, min stroke coverage 0.856, stray 0.0021.

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

### Sources
Wikimedia Commons, File:張旭 古詩四帖.jpg (https://commons.wikimedia.org/wiki/File:%E5%BC%B5%E6%97%AD_%E5%8F%A4%E8%A9%A9%E5%9B%9B%E5%B8%96.jpg): 張旭《古詩四帖》 (attributed to Zhang Xu, Tang, 8th century, cursive script, ink on coloured paper, Liaoning Provincial Museum; the text is two poems of Yu Xin's 步虛詞 and two eulogies by Xie Lingyun). Licence on the file page: {{PD-old-70}} (public domain; a faithful reproduction of a two-dimensional work more than 1200 years old). The characters were cropped from this scan (downloaded unmodified on 2026-10-08, 11787 x 1600 px, SHA-1 b2e19768317f8234c3308a91013934240bf1074f), binarised and placed on the sheet; a work keeps its column as written.

### Licences
The exemplar is a scan of a public-domain historical work of cursive-script calligraphy (Wikimedia Commons, public domain;
Sources above); licence notices: `environment/NOTICE-exemplar.md` (the agent's), `tests/NOTICE-exemplar.md` (the graders').
