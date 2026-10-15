# robopaint-caoshu-zhen-i00-privileged

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | privileged |
| Twin | `robopaint-caoshu-zhen-i00-standard` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_caoshu_zhen` / seed 0 |
| Oracle | `partial` — Reference solution in solution/ (a new family, generated on 2026-10-09 with the current tooling): the generator's self-test replayed it on the graders' copy and through the scoring service (equal metrics, success); under the process rules the verifier scores it 1 (tests/grade.py with rcb_brush_strict.py, two fresh replays): path_mm 534 and mark_width_mm 5.86, against the colouring-in limits 1610 mm and 1.75 mm. Harbor oracle and nop runs: docs/benchmarks/robopaint.md (Caoshu). |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robopaint:0.2.0` |

## Task
**Process rules** (docs/benchmarks/robopaint.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: colouring in fails: a brush-tip path on the main sheet (`path_mm`) longer than 1610 mm (3 × the reference
solution's 534 mm) made of marks narrower than 1.75 mm on average (`mark_width_mm`: each stroke's own
inked area / `path_mm`; 0.3 × the reference's 5.86 mm). The cap counts strokes as written: a contact is cut where the brush moves more than 5 mm without a mark
0.1 mm wide, and a stroke longer than 1590 mm (5 × the reference's
longest, 317 mm) counts once per started 1590 mm; at most 10 % of the
path in strokes longer than 12 × their bounding box's diagonal (sweeps). They are part of the frozen instance (the rules added to its `target.success`); the graders'
`rcb_brush_strict.py` applies them (the verifier and the scoring service).

Copy the exemplar character 真 in cursive script shown in `environment/target.png` onto the 227 mm main sheet in at most 3 strokes, with ink from an ink stone and a practice sheet beside it; the brush starts dry; start pose = PandaStick's rest keyframe; the scene frozen in `environment/instance.json` (the agent's copy: scene constants, the rule, the picture).

Copy the exemplar (臨帖), scored against the picture after the best single shift of the sheet, at most 5 mm along each axis (translation only): IoU of the inked areas ≥ 0.80, boundary F (edge precision / recall within
1 mm) ≥ 0.75, region coverage ≥ 0.80 (the exemplar's ink is divided into 12 regions; the fraction of each region covered by
your ink; the worst one counts), stray ink (> 1 mm away from the exemplar's ink) ≤ 0.04 of its inked area and at most 3 strokes
(continuous brush contacts) on the main sheet. `final_reward` = IoU (× 3 / strokes above 3). Ink precision / recall, missing
ink and the mean region coverage are reported too.

## Difficulty
The mark is not a disc under the tip: the brush model's width and drag tail grow with the press depth, the part of the tuft on the
paper stays put until the handle is up to ~11 mm away and is then dragged behind it (the mark trails the handle and cuts inside
turns), lifting releases the bend; the hairs' state carries over. Writing each stroke with the handle on the stroke's middle and
the press set by the local width (the naive plan) writes every stroke about one offset behind, loses hooks and tapers and fails the
rule by a wide margin (measured on the kaishu family, DESIGN §17). Solving it needs stroke planning against the brush dynamics and accurate tracking by a
position-controlled arm (PD lag ~0.1 s). The tooling gives only thin primitives; `s.score()`, the exact sheets and
`s.brush_state()` are privileged feedback. The stroke cap rules out filling the exemplar with many thin strokes.

Cursive (草书) adds what the regular and running families do not ask for: the cap (3) is the number of continuous brush contacts
the exemplar's ink itself shows, so wherever the ink is connected the brush has to stay on the paper, through sharp turns, loops,
crossings of the stroke over itself and the thin ligatures between strokes (and between the characters of a work), changing the
press continuously from full strokes to hairlines on the way. A contact is long (several strokes of a regular hand in one), so the
trailing of the tuft has to be planned around every turn, and an error early in a contact cannot be fixed by lifting.
The exemplar's ink is divided along each contact into 12 regions of at most about 30 mm, so every part of a long stroke has
to be covered, not only most of it.

## Reference solution
Generated once (the kaishu oracle, DESIGN §17, one plan per contact), on the graders' copy: per continuous brush contact of the
exemplar (its connected ink, written without a lift), a robot-free trajectory optimisation against the brush model (handle control
points (x, y, press) every 7 mm of path, initialised by inverting the trailing dynamics along the contact, scipy least_squares on
the rendered contact against all of its regions), then executed on the robot with lag feed-forward and iterative learning control,
a dip before every contact, the arm parked at the end. The plan is frozen at generation time (`solution/oracle_qpos.npy`); `solution/solve.sh` replays it:
1110 control steps, 3 strokes, IoU 0.941, boundary F 0.955, min stroke coverage 0.894, stray 0.0026.

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

### Change Log
- 2026-10-10: the verifier and the scoring service only (review of 2026-10-10, board 0067). The verifier's timeout is 3600 s (was 1800 s): two fresh replays of the 72,000 control steps a trajectory may have take up to 36 min at the measured 67-102 steps/s, so a long painting timed the verifier out and the trial had no reward. A file that is not a readable trajectory (not an npz, pickled arrays, no `actions`) scores 0 as `bad_trajectory` (was `grader_error`); every `reward.json` has `deterministic`. The `scorer` service restarts if its process dies (`restart: on-failure`). The verdict of a trajectory the verifier could replay before is unchanged, and so are the instance, the picture and the rules: the task keeps its name.
- 2026-10-10 (2): `task.toml` `[agent].allowed_hosts` only. The allowlist is now the one every other allowlist task has (`scripts/set_agent_egress.py`): it gains `*.openai.azure.com` and `*.cognitiveservices.azure.com`, so that an agent whose model is served by Azure OpenAI can reach it directly (without them such an agent could not reach its model and ended as a 0 without having acted). Nothing else changes: the task keeps its name.
- 2026-10-10 (review round 2, board 0067): `tests/grade.py` only. A frozen instance that the verifier's host does not rebuild (`instance_ok = 0`) is `grader_error = 1` and `infra_error = 1` (it was a plain 0 without a flag: the replays ran on another scene and say nothing about the trajectory), and every `grader_error = 1` (a replay process without a result or past its time limit) now has `infra_error = 1` next to it; every `reward.json` carries `infra_error`. The reward is 0 in these cases, as before; the pass rule, the frozen instance and the tooling are unchanged.
- 2026-10-14 (failure analysis of 2026-10-14): the graders' `rcb_brush_strict.py`, the same file in every RoboPaint task, gained the calligraphy families' counted strokes (their own entry, where it applies); a task without those rule keys in `target.success` (lettering and the paintings) is graded exactly as before.
- 2026-10-14 (failure analysis of 2026-10-14, item 9): the process rules count strokes as they are written (`rcb_brush_strict.py`; the rule numbers in every copy of the instance's `target.success`: `stroke_gap_mm`, `mark_min_width_mm`, `max_stroke_path_mm`, `max_scribble`, `max_scribble_share`, `scribble_min_mm`). A contact is cut into two strokes where the brush moves more than 5 mm along the main sheet without marking it (a mark narrower than 0.1 mm), a stroke longer than `max_stroke_path_mm` (5 x the reference solution's longest stroke) counts as several, and the paintings' sweep rule (at most 10 % of the path in strokes longer than 12 x their bounding box's diagonal) applies to these strokes. Before, the cap counted contacts: pieces written separately and joined by a press too light to ink counted as one stroke, and so did a contact held down to write over and over. The scene (`instance_sha`), the picture rule and the reference solution are unchanged, and the reference passes with each of its strokes counted once. Results graded before this change are re-graded from their recorded trajectories, nothing is re-run (scripts/robopaint_strict/regrade.py). The instruction states the rule.
