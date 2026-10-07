# RoboPaint

Brush art on ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU): a Panda holding a brush or pen copies a picture onto a paper
sheet, dipping in an ink stone or paint wells, with a practice sheet beside it. `simulator = "maniskill"`,
`robot = "franka-panda"`. Five families, 82 targets: 楷书 kaishu (35 characters and works), 行书 xingshu (16), lettering (10
words, broad nib and pointed pen), acrylic (10) and oil (11) paintings. Each target is a privileged task
`robopaint-<family>-<target>-i00-privileged` and its standard twin `...-i00-standard` on the same frozen instance;
`[metadata].family = "robopaint_<family>_<target>"`. The line family (9 line drawings) is excluded from the benchmark and
not in this repository: its tooling serves only rcb-limited/2.0.

Every task has **process rules** on top of the picture rule: the exemplar has to be written or painted with strokes, the way a
person does, not coloured in (Process rules). Results of the earlier version of these tasks, which scored only the final sheet
against the picture, are not comparable with this one.

## Tasks and generator
- `python3 scripts/robopaint_strict/mk_tasks.py [--check]` writes every task from the committed ones, with no docker and no GPU
  (standard library only). CI runs `--check` (`ci_checks/check-generated-tasks.sh`); rerunning it over every pair leaves
  `git diff tasks/` empty. It works in two stages:
  1. `scripts/robopaint_brush_mk_task.py --refresh`, into a temporary directory, rebuilds each pair without the process rules
     from its own frozen files (the instance and the picture, the reference plan and its records).
     - The code comes from the family's template pair: kaishu and xingshu `yong`, lettering `minim`, acrylic `redfuji`, oil
       `cypresses`. Any committed pair of the family would do. A tooling change is made in the template pair and reaches every
       task when the script is rerun. A painting's program is read from the template's `solution/programs_json/`, where a
       pair's own entry is its current program, so a painting pair is remade with itself as the template.
     - The standard twin's client and service layer come from `scripts/eai_standard/`.
     - The texts come from `scripts/robopaint_templates/<family>/`. They take their values from the frozen files
       (`derive_values`). The oil rule is calibrated at generation time on the reference solution's own execution
       (`solution/calibration.json`), and the oil texts are written with the calibrated thresholds.
  2. The script adds the process rules: the rules to every copy of the instance's `target.success`, `rcb_brush_strict.py`
     (from `scripts/robopaint_strict/`) to the graders' side, the rule texts (`scripts/robopaint_strict/texts/`) to
     `instruction.md` (after "Target and score"), `README.md` and the `task.toml` description, and the oracle evidence.
     The wiring of `rcb_brush_strict.py` (`tests/grade.py`, `tests/Dockerfile`, `environment/docker-compose.yaml`) is part of the
     template pair's code; the script checks that it is there.
- `scripts/robopaint_strict/rules.json` holds the family parameters, the oracle evidence texts, and `reference_path_mm` /
  `reference_mark_width_mm` per pair. "strict" survives in internal names only: this directory, `rcb_brush_strict.py`,
  `RCB_TOOL_MODULE=rcb_brush_strict` and the `reward.json` key `strict_ok` (the process rules).
- A new pair:
  1. `scripts/robopaint_brush_mk_task.py` (docker, GPU) makes the frozen files inside the base image: the instance and the
     picture, the reference plan, and a self-test of the scoring path. Its pair has the picture rule only.
  2. `scripts/robopaint_strict/measure_reference.py` (base image, GPU) measures the reference solution's `path_mm` and mark
     width: each pair's `solution/oracle_qpos.npy`, replayed with `rcb_brush_strict`'s Session on the graders' instance.
     They go into `rules.json`.
  3. `mk_tasks.py` writes the pair with its rules; then `cd tasks && harbor add --scan .`.
- Every generated task ends with `normalize()` of `scripts/task_conventions.py` (the repository's conventions; `--check`
  passes on every RoboPaint task).
- Benchmark-specific metadata: `difficulty`, `medium`, `stroke_count`, `structure`, `characters` (TAXONOMY).
- Every pair has a real reference solution in `solution/`.
  - The privileged `solution/solve.sh` replays the frozen reference plan.
  - The standard one streams the same joint targets through the client; it waits out a service restart and continues
    from the control step the service reports.
  - The oracle label is `partial` on all 164 tasks (see Oracle evidence).
  - The generator writes each task's `oracle_evidence` from `scripts/robopaint_strict/rules.json`.
- CI:
  - `ci_checks/check-robopaint-tooling.sh` keeps every copy of the shared files, `rcb_brush_strict.py` included,
    byte-identical within a family and across the families;
  - `ci_checks/check-robopaint-leak.sh` admits the rule keys in the agent's copy of the instance.

## Oracle evidence
A task is labelled `oracle = "full"` only if a recorded oracle run scored 1 on byte-identical grader, frozen instance,
tooling and oracle code (lead, 2026-10-01). The oracle runs on record below are of the earlier version of these tasks (the
picture rule only) and all predate the current files, so every task is `partial`. Its `oracle_evidence` points to these runs
and to the validation of the process rules (Validation). Human review in PR #3.

**Release validation of the earlier version**, ws3, 2026-09-28, at each family's release commit. Every target ran Harbor's
oracle and nop in both modes (jobs `<family>-{u,l}-{oracle,nop}-final0928`):

| family | release commit | oracle (both modes) | nop (both modes) | v2 registered scoring | Harbor re-check after v2 (oracle + nop, both modes) |
|---|---|---|---|---|---|
| kaishu | 2984b847 | 70 / 70 | 0 / 70 | aaffb039 | tiandaochouqin, yong |
| xingshu | bfb0246d | 32 / 32 | 0 / 32 | a67040a8 | tianlangqiqing, zhi |
| lettering | 91ab5177 | 20 / 20 | 0 / 20 | 0c61185b | minim, nun |
| acrylic | a1643285 | 20 / 20 | 0 / 20 | 8bc4fc0c | applesoranges, redfuji |
| oil | 99b07cde | 22 / 22 | 0 / 22 | cc866ac9 (with tooling snapshot 23 and the 8 mm scoring inset) | irises, pearlearring |

**Changed since the release validation**, in every pair:
- the v2 registered scoring: the success rule in `instance.json` and the scorer `rcb_brush_score.py`. The saved oracle
  trajectories were re-scored, and all pass.
- tooling snapshot 23 (ccb213d0, the scorer, for the four non-oil families). Re-scores were bit-identical.
- the 2.2 inputs (cf95376f) and the rated limits (fe5fb9e6) in `rcb_brush.py`. Both only add tooling queries.
- for the standard twins, protocol v1.0's crash recovery: `server.py`, `finalize.sh`, `grade.py`, the 2.2 layer, the
  client and the standard oracle.

**Later runs** (earlier version):
- After the 2.2 inputs (before the rated limits), ws3, 2026-09-28: kaishu-ai, acrylic-applesoranges and oil-cypresses
  scored oracle 1 and nop 0 in both modes (jobs `p22-<pair>[-limited]-{oracle,nop}`).
- kaishu-yong's standard twin, on files identical to 9eb18edf (before crash recovery), ws3 and ws, 2026-09-29: oracle 1,
  nop 0 (`v22-ws3-oracle-kaishu-yong-0418`, `v22-ws3-nop-kaishu-yong-0419`).

## Validation
2026-10-05, on the built task images (ws3 and an RTX 4090 laptop, the same `eai-robopaint:0.2.0` layers; before the tasks took
their current names and texts, with the same instances, graders and tooling): each task's `tests/Dockerfile` built into its
verifier image and run as Harbor runs the separate verifier, `grade.py` called as `test.sh` calls it but without the replay
video (the video never changes the verdict).
- Reference solutions (each pair's `solution/oracle_qpos.npy` as the trajectory):
  - the privileged verifier: 82 of 82 succeed (two fresh replays, deterministic);
  - the standard path, the sim sidecar's collect hook (`finalize.sh`: two fresh replays with `rcb_brush_strict.py`, then
    `final.json`) followed by the verifier image: 82 of 82 succeed (deterministic);
  - Harbor end to end (`-a oracle`, `-a nop`) on both modes of kaishu yong, xingshu zhi, lettering minim, acrylic redfuji and
    oil cypresses: the oracle succeeds on 10 of 10, nop on 0 of 10;
  - the privileged scoring service (`RCB_TOOL_MODULE=rcb_brush_strict`) returns the rule metrics to `s.score()` (lettering
    omnium and oil cypresses: the reference passes, Astra's colouring in fails).
- Recorded runs of the earlier version, each graded by its pair's verifier image (one replay) against its picture-rule verdict:

  | Population | Runs | Picture rule only | With the process rules | 1→0 | 0→1 |
  |---|---|---|---|---|---|
  | GPT-6 Astra | 112 | 109 | 7 | 102 | 0 |
  | GPT-6 Luna, successes | 53 | 53 | 49 | 4 | 0 |
  | GPT-6 Luna, failures | 195 | 0 | 0 | 0 | 0 |

  - The picture verdict (`image_success`) equals the earlier one in all 360 runs; no grader errors.
  - Astra keeps its 7 real lettering runs. Luna's 4 flips are the ones in Calibration: three acrylic serpentine fills and
    lettering moon.
  - The 109 Astra runs graded on both hosts agree to the last digit of `final_reward`.
- Both verifiers on 10 Astra colour-in successes (two per family): the earlier verifier image (picture rule only) passes
  all 10; this version's fails all 10, with the picture verdict 1.
- The standard path on 8 recorded standard runs: Luna's four lettering successes (donum, nimium, nun, minimum) and Astra's
  lettering moon succeed; Astra's colouring in (kaishu yong, lettering donum, acrylic redfuji) fails with the picture verdict 1.
- 2026-10-07, Harbor end to end on the tasks under their current names and texts (an RTX 4090 laptop, `eai-robopaint:0.2.0`):
  `-a oracle` scores 1 and `-a nop` 0 on both modes of kaishu yong and oil cypresses (8 runs). `reward.json` carries the rule
  metrics: kaishu yong `path_mm` 474 of 1430 mm and `mark_width_mm` 6.66 mm, oil cypresses `path_mm` 9377 of 28200 mm.

## Image and host
- `images/robopaint/` holds ManiSkill 3.0.1, SAPIEN 3.0.3, a patched libmypaint 1.6.1 and Spline-FRIDA.
  - The image is `ghcr.io/mll-lab-nu/eai-robopaint:<images/robopaint/VERSION>` (0.2.0), public: a copy of
    the image first published as `rcb-robopaint:0.2.0`.
  - It is built from the repository root: `docker build -f images/robopaint/Dockerfile .`.
- Every simulator container needs an NVIDIA GPU: SAPIEN needs a Vulkan device to build the scene and to render. Physics
  and the brush models run on the CPU.
- A standard twin's agent container and verifier use the one client base of every standard task
  (`scripts/eai_standard/client.env`, pinned by digest). The agent side installs the exact pins of
  `client-requirements.txt`, inline; the generator writes both (`ci_checks/check-standard-client.sh`).
- Agent egress is an allowlist (model APIs only) on every task, because the sources of some targets are public.
- Frozen inputs over 2 MB: 9 of the 11 oil reference pictures (`target.png`, 2.0–2.5 MB, 5 copies per pair).
  - They are photographic scans, so lossless re-encoding gets only 5 of the 9 under 2 MB.
  - They stay as frozen (the instance hash covers their pixels). The 2 MB limit is for results.

## Time budget (D8)
7200 s for every task of both modes, longer than the default 3600 s:
- The agent first has to learn the brush's mark from test strokes on the practice sheet: width against press depth, the
  drag of the tuft, the paint's blending. The privileged mode gives the exact sheet but no brush model.
- Every stroke on the main sheet is irreversible in standard mode.
- Works and paintings take tens to hundreds of strokes (stroke caps up to 53 for a calligraphy work and 683 for an oil
  painting), each at the arm's real speed.

Lettering ran at 5400 s before protocol v1.0 and now has 7200 s like the rest. Results are grouped by budget (see Results).

## The target is only a picture
`target.png` (RGB) in both modes. Its source (glyph outlines, pen paths, the exemplar's paint coverage) stays in the
graders' copy of the instance. Nothing derived from it is in the agent's container (`ci_checks/check-robopaint-leak.sh`).

## Scoring
Success needs the picture rule and the process rules; `final_reward` is the continuous score.
- The picture rule: every quantity is taken after the best global shift of the sheet within 5 mm. Success needs every threshold.
  - Calligraphy and lettering: IoU of the inked areas, boundary F, per-stroke coverage, stray ink and a stroke cap.
  - Paintings: blurred CIELAB ΔE, SSIM of L*, edge correlation and paint coverage.
- The process rules (below) are measured on the strokes themselves.
- Privileged mode: `s.score()` asks a `scorer` sidecar (the graders' copy), so the agent may check itself.
- Standard mode: no score at all. The service's episode is replayed in two fresh processes and scored afterwards.

## Why process rules
GPT-6 Astra (Codex, effort high; 112 trials of the earlier version, which scored only the final sheet against the picture,
2026-10-03/04) passed 109 of them, mostly without writing or painting: it set one light press that draws a thin line, kept it
for the whole episode, and filled the exemplar's area with long back-and-forth or contour-offset paths (colouring in). The picture
rule alone passed this. GPT-6 Luna's three acrylic successes there were serpentine fills too. The rules measure the strokes
themselves. They are placed so that colouring in fails while ordinary attempts, good or poor, keep their picture verdict
(Calibration).

## Process rules
Only inked (painted) strokes on the main sheet count; practice-sheet strokes are free. `path_mm` = the total length of the brush
(pen) tip's path while it presses on the main sheet, summed over the 100 Hz physics samples.

| Families | Rule (each task states its own numbers) |
|---|---|
| kaishu, xingshu, lettering | **Colouring in fails:** `path_mm` > `max_path_mm` (3 × the reference solution's `path_mm`, rounded up to 10 mm) **and** `mark_width_mm` < `min_mark_width_mm` (0.3 × the reference's, rounded down to 0.01 mm). `mark_width_mm` = the area each stroke inks on its own (its own mark, coverage ≥ 0.5; overlaps between different strokes count again), summed over the strokes, / `path_mm`: the marks' average width. |
| acrylic, oil | **Path budget:** `path_mm` ≤ `max_path_mm` (3 × the reference's, rounded up to 100 mm). **Strokes are sweeps:** `scribble_share` ≤ 0.10, the share of `path_mm` in strokes longer than 2.5 × the diagonal of their bounding box (taken as at least 10 mm): zigzags, back-and-forth fills, spirals, loops (a sweep out and back along one line is about 2). |

The numbers per task: `max_path_mm` 720–5770 mm (kaishu), 500–6060 mm (xingshu), 660–1680 mm (lettering), 32300–51700 mm (acrylic),
28100–39600 mm (oil); `min_mark_width_mm` 1.20–2.44 mm (kaishu), 1.10–3.06 mm (xingshu), 0.23–1.04 mm (lettering).

`success` = the picture rule (`image_success`) ∧ the process rules (`strict_ok`). `final_reward` = the picture rule's
continuous score × min(1, `max_path_mm` / `path_mm`) when colouring in or over the path budget, × (1 − `scribble_share`) when the
sweep rule fails: rule-abiding work keeps the picture rule's score. `reward.json` reports `image_success`, `image_final_reward`,
`strict_ok`, `path_mm`, `max_path_mm`, `mark_width_mm`, `min_mark_width_mm`, `colour_in`, `path_budget_ok`, `scribble_share`,
`scribble_max`, `scribble_ok` and `longest_stroke_mm` next to the picture rule's metrics; the privileged `s.score()` returns them too,
and `s.strokes()` holds each stroke's samples and own mark, so an agent can check itself. The instructions state the rules in plain
words (write or paint with strokes the way a person does; colouring in, filling, zigzag, serpentine and contour-offset fills fail)
and with the task's numbers.

Where they are applied: `rcb_brush_strict.py` (graders' side only), a `Session` subclass whose `score()` adds the rules, run with
`rcb_brush.py`'s CLI. The privileged verifier replays with it (`tests/grade.py`), the privileged scoring service imports it
(`RCB_TOOL_MODULE=rcb_brush_strict`), and the standard collect hook replays with it (`RCB_TOOL=/srv/rcb_brush_strict.py`). The
agent's container holds `rcb_brush.py` only. A trajectory of the earlier version is graded by this version's verifier as it is,
so it can be re-graded one to one (Calibration), but its published result is not comparable.

## Calibration
2026-10-04, ws3: every trajectory was replayed with the graders' tooling of the earlier version (the picture rule) in the base
image. The populations were the 82 reference solutions; GPT-6 Astra (Codex, high; 112 trials); and GPT-6 Luna (Codex, xhigh;
batches robopaint-lunaxh-0928b, -rerun-0928, -limited-0929 and its rerun: 248 trajectories). The replays reproduce all 360
recorded verdicts. Every trial near a threshold was inspected as a path picture.

| Population | Runs | Picture rule only | With the process rules | Flagged by the rules |
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

  ![sweep rule boundary](robopaint-sweep-boundary.png)
- Raster rows: rows of straight strokes stay allowed in oil. The oil reference painter lays its underpainting that way, and Luna's
  four oil successes are such rows.
- Known limitation: the closest colour-in run (Astra lettering omnium, standard) sits at 0.97 of its mark-width limit, so a fill
  with a slightly wider nib could pass; the rule chooses leniency on purpose. Likewise the closest painting fill (Astra oil bathers)
  is only 1.43× the sweep limit.

## Grading and determinism
- Fresh-process replays: the final states of two replays must agree (`deterministic`), and `live_matches_replay` is
  reported.
- The episode has no terminal state. It ends with the agent phase, a simulator error, or the 72000-control-step runaway
  guard.
- Crash recovery (standard mode, docs/STANDARD_MODE_2_2.md §13):
  - Resume class `exact`: PhysX on the CPU and the CPU brush models repeat bit for bit in a fresh process, so a resumed
    episode must reach the checkpoint's state hash.
  - The journal rows are the 7 joint targets of each control step.
  - The adapter persists its last `ee_pose` tip target (the start of the next `ee_pose` line).
  - Compose: `restart: on-failure:6`, `command: sh /srv/run.sh`.
- `RCB_STARTUP_TIMEOUT_S = 600` on every standard task. In 285 standard trials of the brush families (ws, ws3, lab, up to
  50 concurrent lanes), the episode started at most 126 s after Harbor began the environment setup (median about 30 s).
  The Session build alone took at most 106 s. That makes 600 s more than four times the slowest measured start.
- The collect hook starts with `rcb_limited.py end`. A verdict the service already wrote (it gave up after crashes) is
  kept, and nothing is replayed. `reward.json` reports `sim_startups`, `resumes`, `resume_state_mismatch`, `gave_up` and
  `infra_error`.

## Tooling (file names)
| main's convention | RoboPaint |
|---|---|
| `environment/rcb_traj.py` (privileged tooling, `Session`) | `environment/rcb_brush.py` |
| `tests/rcb_traj.py` | `tests/rcb_brush.py` + `tests/rcb_brush_score.py` |
| — | `environment/scorer/` (privileged `s.score()`: `rcb_scorer.py` + the scoring module) |
| standard sidecar | `environment/sim/server.py` (the 2.2 adapter), `finalize.sh` (the collect hook), the brush tooling and its scorer, and from `scripts/eai_standard/`: `rcb_limited.py`, `rcb1.py`, `run.sh` |
| `rcb_client.py`, `rcb1.py` | the same names (`scripts/eai_standard/`) |
| — | `rcb_brush_strict.py` (the process rules, graders' side only): `tests/` and `environment/scorer/` (privileged), `environment/sim/` (standard) |

Every copy of the tooling is byte-identical within a family and across the five families
(`ci_checks/check-robopaint-tooling.sh`). The 2.2 layer is byte-identical to `scripts/eai_standard/`
(`ci_checks/check-tooling-identity.sh`).

## Declarations
- **Tooling: thin wrappers only.** The agent gets the robot's low-level actions (joint targets, brush-tip poses), the
  sheets, rendering and replay. No stroke planner or painting skill is added to the agent's tooling; the reference
  solutions keep theirs under `solution/`.
- **World-frame information (D7).** Standard tasks never say where things are in the world: no sheet heights or centres,
  no well positions, no pixel-to-world formula (STANDARD_MODE_2_2.md §10, `check-limited-texts.sh`).
  - Accepted consequence: the calibrated `canvas_cam` above the main sheet tells roughly where the sheet is.
  - Privileged tasks give the sheets through the tooling.

## Standard mode (eai-standard/2.2)
| | |
|---|---|
| actions | `joint_position` (7) and `ee_pose` (7: brush-tip targets `dt` apart, IK per control step, at most 0.25 m/s) |
| cameras | four static cameras: `canvas_cam`, `practice_cam`, `scene_cam`, `side_cam` |
| depth | SAPIEN depth, geometry only: ink and paint never show |
| `/kinematics` | SAPIEN's pinocchio model (7 joints) |
| proprio | 28 columns |

More in STANDARD_MODE_2_2.md §16.

## Results
No task directory holds results (PROTOCOL §5); they are published on the results site
(<https://embodied-agent-interface-v2-internal.github.io/runs/robopaint/>), with videos and full trials on the HF dataset
`eai-v2-internal/agent-runs`.
- This version: no runs yet.
- The runs on record are of the earlier version (picture rule only) and are not comparable with this one. Their trajectories
  re-grade under the process rules (Calibration). `codex-gpt6_luna-xhigh` (Codex CLI 0.157.0, GPT-6 Luna, reasoning xhigh):
  - they ran on pre-v1.0 versions of the tasks (privileged without a suffix, standard twins `-limited`): batch
    robopaint-lunaxh-0928b (privileged, and standard on rcb-limited/2.0) and robopaint-lunaxh-limited-0929 (standard on
    rcb-limited/2.2), 2026-09-28/29;
  - successes: privileged 49/82, standard 3/82 (2.0) and 1/82 (2.2);
  - lettering ran with a 5400 s budget, so its results form their own group; every other task ran with 7200 s.

## Licences
- ManiSkill and SAPIEN: Apache-2.0.
- Spline-FRIDA (code and weights): GPL-3.0. Only the line family used it; it stays in the image with its source.
- libmypaint: ISC (patched). mypaint-brushes: CC0-1.0.
- The calligraphy exemplars: as stated in each task's `NOTICE-exemplar.md`.
