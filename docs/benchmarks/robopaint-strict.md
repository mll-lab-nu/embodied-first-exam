# RoboPaint-strict

RoboPaint's 82 brush targets (楷书 kaishu 35, 行书 xingshu 16, lettering 10, acrylic 10, oil 11; both modes, 164 tasks) with
**process rules** on top of RoboPaint's picture rule: the exemplar has to be written or painted with strokes, the way a person
does, not coloured in. Task dirs `robopaint-strict-<family>-<target>-i00-{privileged,standard}`, `[metadata].family =
"robopaint_strict_<family>_<target>"`. Everything else is RoboPaint's ([robopaint.md](robopaint.md)): the scene and frozen
instance (`instance_sha` unchanged; the rules are added to the instance's `target.success`), the picture, the tooling
(`rcb_brush.py` and `rcb_brush_score.py` byte-identical), the picture rule, the reference solution, the image, the 7200 s budget,
the agent egress allowlist and the standard service. RoboPaint's tasks and results stay as they are. A RoboPaint trajectory is
graded by the strict verifier as it is, so the two benchmarks compare one to one.

## Why
GPT-6 Astra (Codex, effort high; 112 RoboPaint trials, 2026-10-03/04) passed 109 of them, mostly without writing or painting:
it set one light press that draws a thin line, kept it for the whole episode, and filled the exemplar's area with long
back-and-forth or contour-offset paths (colouring in). RoboPaint scores only the final sheet against the picture, so this passed.
GPT-6 Luna's three acrylic successes are serpentine fills too. The rules measure the strokes themselves. They are placed so that
colouring in fails while ordinary attempts, good or poor, keep their RoboPaint verdict (Calibration).

## The rules
Only inked (painted) strokes on the main sheet count; practice-sheet strokes are free. `path_mm` = the total length of the brush
(pen) tip's path while it presses on the main sheet, summed over the 100 Hz physics samples.

| Families | Rule (each task states its own numbers) |
|---|---|
| kaishu, xingshu, lettering | **Colouring in fails:** `path_mm` > `max_path_mm` (3 × the reference solution's `path_mm`, rounded up to 10 mm) **and** `mark_width_mm` < `min_mark_width_mm` (0.3 × the reference's, rounded down to 0.01 mm). `mark_width_mm` = the area each stroke inks on its own (its own mark, coverage ≥ 0.5; overlaps between different strokes count again), summed over the strokes, / `path_mm`: the marks' average width. |
| acrylic, oil | **Path budget:** `path_mm` ≤ `max_path_mm` (3 × the reference's, rounded up to 100 mm). **Strokes are sweeps:** `scribble_share` ≤ 0.10, the share of `path_mm` in strokes longer than 2.5 × the diagonal of their bounding box (taken as at least 10 mm): zigzags, back-and-forth fills, spirals, loops (a sweep out and back along one line is about 2). |

The numbers per task: `max_path_mm` 720–5770 mm (kaishu), 500–6060 mm (xingshu), 660–1680 mm (lettering), 32300–51700 mm (acrylic),
28100–39600 mm (oil); `min_mark_width_mm` 1.20–2.44 mm (kaishu), 1.10–3.06 mm (xingshu), 0.23–1.04 mm (lettering).

`success` = RoboPaint's picture rule (`image_success`, unchanged) ∧ the process rules (`strict_ok`). `final_reward` = RoboPaint's
continuous score × min(1, `max_path_mm` / `path_mm`) when colouring in or over the path budget, × (1 − `scribble_share`) when the
sweep rule fails: rule-abiding work keeps RoboPaint's score. `reward.json` reports `image_success`, `image_final_reward`,
`strict_ok`, `path_mm`, `max_path_mm`, `mark_width_mm`, `min_mark_width_mm`, `colour_in`, `path_budget_ok`, `scribble_share`,
`scribble_max`, `scribble_ok` and `longest_stroke_mm` next to RoboPaint's metrics; the privileged `s.score()` returns them too,
and `s.strokes()` holds each stroke's samples and own mark, so an agent can check itself. The instructions state the rules in plain
words (write or paint with strokes the way a person does; colouring in, filling, zigzag, serpentine and contour-offset fills fail)
and with the task's numbers.

Where they are applied: `rcb_brush_strict.py` (graders' side only), a `Session` subclass whose `score()` adds the rules, run with
`rcb_brush.py`'s CLI. The privileged verifier replays with it (`tests/grade.py`), the privileged scoring service imports it
(`RCB_TOOL_MODULE=rcb_brush_strict`), and the standard collect hook replays with it (`RCB_TOOL=/srv/rcb_brush_strict.py`). The
agent's container is RoboPaint's.

## Calibration
2026-10-04, ws3: every trajectory was replayed with RoboPaint's graders' tooling in the base image. The populations were the 82
reference solutions; GPT-6 Astra (Codex, high; 112 trials); and GPT-6 Luna (Codex, xhigh; batches robopaint-lunaxh-0928b,
-rerun-0928, -limited-0929 and its rerun: 248 trajectories). The replays reproduce all 360 recorded verdicts. Every trial near a
threshold was inspected as a path picture.

| Population | Runs | RoboPaint successes | RoboPaint-strict successes | Flagged by the rules |
|---|---|---|---|---|
| reference solutions | 82 | 82 | 82 | 0 |
| GPT-6 Astra | 112 | 109 | 7 (its real lettering) | 105, all colour-in |
| GPT-6 Luna, successes | 53 | 53 | 49 | 4: three acrylic serpentine fills, lettering moon (zigzag fill along the strokes) |
| GPT-6 Luna, failures | 195 | 0 | 0 | 22, all colour-in (2 comb fills in xingshu, 20 painting fills) |

Margins (a value / its task's limit):
- Writing, mark width:
  - the colour-in runs reach at most 0.97 (Astra lettering omnium std, a thin multi-pass fill); every other fill is ≤ 0.88;
  - the closest normal run is at 1.15, a Luna failure (xingshu xian, standard) that retraces heavily with a 5.0× path.
- Writing, path: the colour-in runs are at ≥ 1.10. Normal runs with thin marks (a light hand) stay ≤ 0.29.
- Writing, why not a path budget alone: ten normal Luna failures retrace or wander to 3.1–5.0× the reference's path, which overlaps
  the colour-in runs from 4.5×. The mark width separates them.
- Paintings:
  - normal runs: scribble share ≤ 0.021 and path ≤ 1.44× the reference (0.48 of the limit). The closest is a Luna failure
    (acrylic bluehorses, standard) that paints many strokes out and back along one line;
  - fills: scribble share ≥ 0.143 (Astra oil bathers, a wavy meander fill); every other fill is ≥ 0.37;
  - the reference solutions: 0 and 0.33 of the limit;
  - the closest flagged attempt is a Luna failure, acrylic plumpark (standard, 0.54): long meanders that cover whole areas
    with a wide brush. Counting it as a fill is defensible but borderline; the figure below shows it next to the reference
    solution, the closest normal attempt and the closest Astra fill;
  - why 2.5 and 0.10: at a ratio of 2 the out-and-back strokes count (that Luna failure: 0.66), at 2.2 there is no gap
    (0.148 normal against 0.244), and at 3 the Astra meander fill drops to 0.055.
- The sweep rule's boundary (strokes longer than 2.5 × their bounding-box diagonal in red):

  ![sweep rule boundary](robopaint-strict-sweep-boundary.png)
- Raster rows: rows of straight strokes stay allowed in oil. The oil reference painter lays its underpainting that way, and Luna's
  four oil successes are such rows.
- Known limitation: the closest colour-in run (Astra lettering omnium, standard) sits at 0.97 of its mark-width limit, so a fill
  with a slightly wider nib could pass; the rule chooses leniency on purpose. Likewise the closest painting fill (Astra oil bathers)
  is only 1.43× the sweep limit.

## Tasks and generator
- `python3 scripts/robopaint_strict/mk_tasks.py [--check]` writes every strict pair from its committed RoboPaint pair (no
  simulator):
  - it adds the rules to every copy of the instance;
  - it adds `rcb_brush_strict.py` to `tests/`, `environment/scorer/` and `environment/sim/` and wires it in;
  - it renders the rule texts (`scripts/robopaint_strict/texts/`) into `instruction.md` (after "Target and score"), `README.md`
    and the `task.toml` description;
  - it renames the benchmark, family and keywords;
  - then `scripts/task_conventions.py` normalizes. CI runs `--check` (`ci_checks/check-generated-tasks.sh`).
- `scripts/robopaint_strict/rules.json` holds the family parameters, the oracle evidence texts, and `reference_path_mm` /
  `reference_mark_width_mm` per pair.
- `scripts/robopaint_strict/measure_reference.py` (base image, GPU) measures those references: each pair's
  `solution/oracle_qpos.npy`, replayed with `rcb_brush_strict`'s Session on the RoboPaint pair's graders' instance.
- A change to RoboPaint's tooling, texts or instance reaches RoboPaint-strict when the generator is rerun.
- CI:
  - `ci_checks/check-robopaint-tooling.sh` keeps `rcb_brush_strict.py` byte-identical across the strict tasks, and the shared
    RoboPaint files identical to RoboPaint's;
  - `check-robopaint-leak.sh` admits the rule keys in the agent's copy of the instance.

## Validation
2026-10-05, on the built task images (ws3 and an RTX 4090 laptop, the same `eai-robopaint:0.2.0` layers): each task's
`tests/Dockerfile` built into its verifier image and run as Harbor runs the separate verifier, `grade.py` called as `test.sh`
calls it but without the replay video (the video never changes the verdict).
- Reference solutions (each pair's `solution/oracle_qpos.npy` as the trajectory):
  - the privileged verifier: 82 of 82 succeed (two fresh replays, deterministic);
  - the standard path, the sim sidecar's collect hook (`finalize.sh`: two fresh replays with `rcb_brush_strict.py`, then
    `final.json`) followed by the verifier image: 82 of 82 succeed (deterministic);
  - Harbor end to end (`-a oracle`, `-a nop`) on both modes of kaishu yong, xingshu zhi, lettering minim, acrylic redfuji and
    oil cypresses: the oracle succeeds on 10 of 10, nop on 0 of 10;
  - the privileged scoring service (`RCB_TOOL_MODULE=rcb_brush_strict`) returns the rule metrics to `s.score()` (lettering
    omnium and oil cypresses: the reference passes, Astra's colouring in fails).
- Recorded runs, each graded by its pair's strict verifier image (one replay) against its RoboPaint verdict:

  | Population | Runs | RoboPaint successes | RoboPaint-strict successes | 1→0 | 0→1 |
  |---|---|---|---|---|---|
  | GPT-6 Astra | 112 | 109 | 7 | 102 | 0 |
  | GPT-6 Luna, successes | 53 | 53 | 49 | 4 | 0 |
  | GPT-6 Luna, failures | 195 | 0 | 0 | 0 | 0 |

  - The picture verdict (`image_success`) equals RoboPaint's in all 360 runs; no grader errors.
  - Astra keeps its 7 real lettering runs. Luna's 4 flips are the ones in Calibration: three acrylic serpentine fills and
    lettering moon.
  - The 109 Astra runs graded on both hosts agree to the last digit of `final_reward`.
- Both verifiers on 10 Astra colour-in successes (two per family): RoboPaint's verifier image passes all 10; RoboPaint-strict's
  fails all 10, with the picture verdict 1.
- The standard path on 8 recorded standard runs: Luna's four lettering successes (donum, nimium, nun, minimum) and Astra's
  lettering moon succeed; Astra's colouring in (kaishu yong, lettering donum, acrylic redfuji) fails with the picture verdict 1.

## Results
None yet. RoboPaint's own runs (`codex-gpt6_luna-xhigh`, `codex-gpt6_astra-high`) re-grade under the strict verifier from their
trajectories (Calibration).
