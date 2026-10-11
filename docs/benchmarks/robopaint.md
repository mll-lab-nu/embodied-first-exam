# RoboPaint

Brush art on ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU): a Panda holding a brush or pen copies a picture onto a paper
sheet, dipping in an ink stone or paint wells, with a practice sheet beside it. `simulator = "maniskill"`,
`robot = "franka-panda"`. Six families, 43 targets (Targets): 楷书 kaishu (2 works), 行书 xingshu (8 characters and works),
草书 caoshu (6: 2 characters and 4 works), lettering (6: 臨摹 of engraved English round hand with a pointed pen, 2 flourished
words and 4 copy lines: Lettering), acrylic (10) and oil (11) paintings. Each target is a privileged task
`robopaint-<family>-<target>-i<NN>-privileged` and its standard twin `...-i<NN>-standard` on the same frozen instance (`i00`;
the oil paintings `i01`, Targets); `[metadata].family = "robopaint_<family>_<target>"`. The line family (9 line drawings) is excluded from the benchmark and
not in this repository: its tooling serves only rcb-limited/2.0.

Every task has **process rules** on top of the picture rule: the exemplar has to be written or painted with strokes, the way a
person does, not coloured in (Process rules). Results of the earlier version of these tasks, which scored only the final sheet
against the picture, are not comparable with this one.

## Targets
This version (2026-10-08/09, owner) prunes the families that GPT-6 Astra saturated, adds harder ones and makes the oil paintings
finer:
- 楷书 kaishu keeps two works: 永字八法 (21 strokes) and 麟鳳龜龍 (71), new. The 31 single characters and the works 天道酬勤,
  厚德載物 and 寧靜致遠 are removed: GPT-6 Astra solved all four existing works in both modes.
- 行书 xingshu keeps eight: 永, 和, 風, 年, 山, 賢 and the works 惠風和暢 and 茂林脩竹. The eight that GPT-6 Astra solved in
  standard mode are removed: 春, 閒, 人, 天朗氣清, 同, 信, 宇, 之.
- The ten calligraphy pairs' reference solutions are re-made (below). Their environment/, tests/ and instruction.md are those
  of the earlier version, so the eight kept xingshu pairs and 永字八法 keep their names.
- 草书 caoshu is new: two characters and four works (Caoshu).
- Lettering is redesigned: the ten authored minim words are removed (Astra 10 of 10 in standard mode), and six copies of
  engraved English round hand are added (Lettering).
- Oil: the eleven paintings get a pointed brush, new reference solutions and a recalibrated rule (Oil: the pointed brush).
  Their frozen instances and verifiers changed, so they are new tasks (PROTOCOL §2.8): `robopaint-oil-<painting>-i01`, which
  replace `-i00`.
- Acrylic is unchanged.
- The records below (release validation, Validation, Calibration) are of the 82 targets of their time; they are not
  recomputed for the 43 of this version.

**麟鳳龜龍** (the four auspicious creatures of the 禮記) is denser than 寧靜致遠, the hardest of the works it replaces: 71
strokes against 53, an exemplar of 8036 mm² against 6730 mm², strokes about 4.2 mm wide against 4.7 mm (the exemplar's area per
stroke length), and 麟 alone has 23 strokes. It is made like the other kaishu targets: Make Me a Hanzi's `graphics.txt` @ bddc96d
(Arphic Public License), `scripts/robopaint_brush_mk_task.py --family kaishu --target linfengguilong --entry diagonal`,
`measure_reference.py`, `mk_tasks.py`.

**The reference writer's entry (`--entry`).** Seven works of 60–71 strokes were tried (鸞翔鳳翥, 麟鳳龜龍, 鐵畫銀鉤, 鶴髮童顏,
蘭薰桂馥, 翰墨飄香, 歡聲雷動). With the reference writer as it was, every reference solution failed the picture rule on stray
ink (0.040–0.067; the limit is 0.04), although the robot-free plans had about 0.007 (measured for 鸞翔鳳翥 and 麟鳳龜龍). The
writer stops above each stroke's start, presses straight down and lifts straight up. At the stop the arm rebounds a fraction of
a millimetre, and the brush takes the rebound as its direction of travel (in the air θ follows any motion faster than 1 cm/s):
on about a quarter of the strokes the drag tail met the paper turned against the stroke and swept a disc. Dense works have many
short, thin strokes, where these discs fall outside the exemplar. With `solution/opt_calli.py --entry diagonal` (recorded in the
pair's `plans.json`) the brush enters and leaves the paper on straight 8 mm lines along the stroke, without a stop, in the
robot-free optimisation and on the robot alike. The stray ink drops to 0.016–0.019: 麟鳳龜龍 and 鐵畫銀鉤 pass; 鸞翔鳳翥 still
fails, because two strokes of 鸞 stay below 0.80 coverage, already in its robot-free plan. The default is the vertical
touch-down. With it the new code writes the same plans as the old one, and its robot step on 永字八法's frozen plans gives that
pair's frozen trajectory bit for bit. Only the solution code under 永字八法's `solution/` changed; its `environment/` and
`tests/` did not.

**The reference solutions, re-made on 2026-10-09.** The owner's review of the references: a copy should look like its exemplar,
"like a print". Strokes were missing (賢's two inner horizontals), starts had blobs and ends had needle tails. All ten
calligraphy pairs now have references from a new planner, `solution/opt_calli.py --profile print` (its `solution/README.md`
has the method; the earlier per-stroke planner stays its default):
- the brush enters the paper along the stroke and leaves it back onto its own root (回锋), with a minimum press inside a
  contact, so no disc is swept at a start, no needle is drawn at an end, and no contact splits in two;
- per contact, several paths through its ink are tried and the best is kept. One of them walks each region's ink branch by
  branch, so a region whose given centre line covers only part of it is written in full (賢's inner horizontals; 暢's 勿
  hook, merged with the next stroke, written in one pass);
- control points about every 6 mm, ink more than 1 mm from the exemplar weighted up, regions under 0.92 optimised again;
- the robot step runs with 3 and 5 passes of iterative learning control and keeps the better result (`plans.json`
  `ilc_passes`; only 年 took 5).

Only `solution/` changed, with the README's oracle line and Change Log; the instances, pictures, pass rule and process limits
did not. The limits stay those set on the first references (`rules.json` `reference_path_mm`, `reference_mark_width_mm`); the
new references' values are in `current_reference`. Their paths are longer and their marks narrower, but they stay far from
colouring in. An existing pair is re-solved with `scripts/robopaint_brush_mk_task.py --resolve tasks/<pair>-privileged --plans
<plans.json>` (the robot step and the self-test in the base image, on the frozen instance), then `mk_tasks.py`. The
reference's verifier metrics, before → after:

| target | IoU | boundary F | min stroke coverage | stray | `path_mm` | `mark_width_mm` |
|---|---|---|---|---|---|---|
| kaishu 永字八法 | 0.891 → 0.940 | 0.941 → 0.988 | 0.860 → 0.931 | 0.0123 → 0.0015 | 1075 → 1270 | 4.47 → 3.71 |
| kaishu 麟鳳龜龍 | 0.868 → 0.908 | 0.934 → 0.976 | 0.829 → 0.890 | 0.0165 → 0.0040 | 2625 → 2828 | 3.32 → 3.07 |
| xingshu 永 | 0.903 → 0.942 | 0.857 → 0.941 | 0.827 → 0.913 | 0.0177 → 0.0049 | 483 → 726 | 7.53 → 5.14 |
| xingshu 和 | 0.916 → 0.957 | 0.832 → 0.958 | 0.935 → 0.957 | 0.0114 → 0.0007 | 616 → 927 | 6.47 → 4.56 |
| xingshu 風 | 0.929 → 0.938 | 0.905 → 0.931 | 0.956 → 0.948 | 0.0100 → 0.0056 | 714 → 1181 | 8.09 → 5.00 |
| xingshu 年 | 0.936 → 0.957 | 0.909 → 0.963 | 0.918 → 0.933 | 0.0077 → 0.0021 | 591 → 1013 | 7.34 → 4.59 |
| xingshu 山 | 0.939 → 0.970 | 0.920 → 0.966 | 0.914 → 0.973 | 0.0068 → 0.0021 | 399 → 608 | 10.21 → 6.75 |
| xingshu 賢 | 0.888 → 0.934 | 0.862 → 0.938 | 0.809 → 0.944 | 0.0134 → 0.0054 | 875 → 1234 | 6.29 → 4.59 |
| xingshu 惠風和暢 | 0.875 → 0.917 | 0.902 → 0.969 | 0.903 → 0.926 | 0.0191 → 0.0026 | 2017 → 2483 | 3.85 → 3.04 |
| xingshu 茂林脩竹 | 0.844 → 0.898 | 0.896 → 0.962 | 0.863 → 0.910 | 0.0215 → 0.0054 | 1051 → 1412 | 3.76 → 2.79 |

The internal goal was IoU ≥ 0.92, boundary F ≥ 0.90, every region ≥ 0.90 and stray ≤ 0.01; seven of the ten meet it, and
惠風和暢, 茂林脩竹 and 麟鳳龜龍 miss it on IoU (麟鳳龜龍 also on one region, 0.890). What still limits the copy:
- **Spikes behind blunt starts.** The brush's mark is a flat end at the root with a parabolic drag tail behind it, and the
  root trails the handle. While the press grows after a start, the tail reaches 2–5 mm behind the start point, where the
  exemplar has a blunt end.
- **Robot tracking.** The robot's result is 0.005–0.015 IoU below the robot-free plan.
- **Dense works.** 麟鳳龜龍, 茂林脩竹 and 惠風和暢 lose most in the 1 mm band around their thin strokes.

## Tasks and generator
- `python3 scripts/robopaint_strict/mk_tasks.py [--check]` writes every task from the committed ones, with no docker and no GPU
  (standard library only). CI runs `--check` (`ci_checks/check-generated-tasks.sh`); rerunning it over every pair leaves
  `git diff tasks/` empty. It works in two stages:
  1. `scripts/robopaint_brush_mk_task.py --refresh`, into a temporary directory, rebuilds each pair without the process rules
     from its own frozen files (the instance and the picture, the reference plan and its records).
     - The code comes from the family's template pair: kaishu `yongzibafa`, xingshu `yong`, caoshu `wen`, lettering `liberty`,
       acrylic `redfuji`, oil `cypresses`. Any committed pair of the family would do. A tooling change is made in the template
       pair and reaches every task when the script is rerun. A painting's program is read from the template's
       `solution/programs_json/`, where a pair's own entry is its current program, so a painting pair is remade with itself as
       the template.
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
     picture, the reference plan, and a self-test of the scoring path. Its pair has the picture rule only. A dense kaishu work
     needs `--entry diagonal` (Targets). A reference like the current ones is planned outside with `opt_calli.py --profile
     print` and passed with `--plans`, or the pair is re-solved afterwards with `--resolve` (Targets).
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
  - The oracle label is `partial` on all 86 tasks (see Oracle evidence).
  - The generator writes each task's `oracle_evidence` from `scripts/robopaint_strict/rules.json`.
- CI:
  - `ci_checks/check-robopaint-tooling.sh` keeps every copy of the shared files, `rcb_brush_strict.py` included,
    byte-identical within a family and across the families;
  - `ci_checks/check-robopaint-leak.sh` admits the rule keys in the agent's copy of the instance.

## Oracle evidence
A task is labelled `oracle = "full"` only if a recorded oracle run scored 1 on byte-identical grader, frozen instance,
tooling and oracle code (lead, 2026-10-01). The oracle runs on record below are of the earlier version of these tasks (the
picture rule only) and all predate the current files, so every task is `partial`. Its `oracle_evidence` points to these runs
and to the validation of the process rules (Validation). Human review in PR #3. The new pair kaishu linfengguilong
(2026-10-08) has no earlier version: its `oracle_evidence` (`rules.json`, `oracle_evidence_pairs`) points to Harbor oracle and
nop runs on its current files (Validation); it is `partial` like the other pairs. The ten calligraphy pairs' reference
solutions were re-made on 2026-10-09 (Targets). Their `oracle_evidence` (`oracle_evidence_pairs`) points to Harbor oracle and
nop runs on their current files (Validation), and the nine pairs that existed before have a README Change Log entry.

**Release validation of the earlier version**, ws3, 2026-09-28, at each family's release commit. Every target ran Harbor's
oracle and nop in both modes (jobs `<family>-{u,l}-{oracle,nop}-final0928`):

| family | release commit | oracle (both modes) | nop (both modes) | v2 registered scoring | Harbor re-check after v2 (oracle + nop, both modes) |
|---|---|---|---|---|---|
| kaishu | 2984b847 | 70 / 70 | 0 / 70 | aaffb039 | tiandaochouqin, yong |
| xingshu | bfb0246d | 32 / 32 | 0 / 32 | a67040a8 | tianlangqiqing, zhi |
| lettering (the earlier ten words, replaced 2026-10-09: Lettering) | 91ab5177 | 20 / 20 | 0 / 20 | 0c61185b | minim, nun |
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
- 2026-10-08, ws3 (RTX 4090, `eai-robopaint:0.2.0`, Harbor 0.23.0), on the files of that day (before the references were
  re-made on 2026-10-09):
  - kaishu linfengguilong (new): `-a oracle` scores 1 and `-a nop` 0 in both modes. `reward.json`: IoU 0.868, boundary F
    0.934, minimum stroke coverage 0.829, stray ink 0.017; `path_mm` 2625 of 7880 mm, `mark_width_mm` 3.32 mm (limit 0.99 mm).
    Two runs of the generator wrote the same reference trajectory bit for bit, and its self-test passed (the scoring
    service's metrics equal the graders').
  - xingshu huifenghechang (unchanged), a regression check: `-a oracle` scores 1 and `-a nop` 0 in both modes (`path_mm` 2017
    of 6060 mm).
  - 永字八法 under the new planner code with its default (`--entry vertical`): `opt_calli.py` writes the same plans as the old
    code, the robot step on its frozen `plans.json` gives its frozen `oracle_qpos.npy` bit for bit, and `measure_reference.py`
    gives its `rules.json` values again (1074.71 mm, 4.4726 mm).
- 2026-10-09, the ten calligraphy pairs with their re-made references (Targets), on the current files except one sentence of
  `instruction.md` and `README.md` (the reference's path and mark width), which was restored to main's wording afterwards so
  that the instructions stay byte-identical to the earlier version; the oracle and nop runs do not read it:
  - the generator's `--resolve` (the robot step and the self-test) passed on every pair. It ran on the native
    `eai-robopaint:0.2.0` runtime of a rented host without docker; the image itself (docker on ws3) wrote the same
    trajectories bit for bit for xingshu he and nian;
  - the planner, run twice on xingshu he with 3 and with 8 workers, wrote the same plans;
  - Harbor (ws3, RTX 4090, Harbor 0.23.0): `-a oracle` scores 1 and `-a nop` 0 on both modes of all ten pairs (40 runs, jobs
    `rpp-{oracle,nop}-{priv,std}-1009`, no errors); the oracle's `reward.json` carries the metrics of the table in Targets.

## Caoshu (草书)
Cursive writes a character in a few long brush contacts: the contact cap is the exemplar's own connected contacts (1.6–3 per
character, against 6 in xingshu and 8 in kaishu, medians), each contact runs through turns, loops and crossings, and hairline
ligatures (牵丝) join strokes and characters. Six targets: `wen` 文 and `zhen` 真 (characters), and four works, each one column of
the scroll as written, its characters sharing one 210 mm frame so the ligatures between them stay on the sheet: `nangong` 南宮,
`siwushaonian` 四五少年, `zhongtiangechuifen` 中天哥吹分 and `beiquelindanshui` 北闕臨丹水.
- Exemplars: 張旭《古詩四帖》, Wikimedia Commons File:張旭 古詩四帖.jpg ({{PD-old-70}}), by
  `scripts/robopaint_caoshu/cs_exemplar.py` (spec `exemplars.json`, results `exemplars/`). The scan is thresholded (Otsu, with a
  hysteresis that keeps faint ligatures). Whole ink components are kept: the selection box only picks them, a ligature into a
  neighbouring character is cut explicitly (`cut`) and a stroke of the neighbouring column is excluded explicitly (`exclude`). A
  dashed hairline that the threshold breaks up is bridged along its own trace (`bridge_lines`), a dry stroke (飛白) is closed
  within its own area only (`close_regions`), and the edge is smoothed on the signed distance with hairlines kept at their width.
  The skeleton graph is split into trails by good continuation at junctions (one trail = one brush contact = `--max-strokes`),
  and every trail is cut into regions of at most 30 mm of centre path, so the region coverage holds along a long stroke and on
  its hairlines.
- Reference solution: `cs_plan.py`, one plan per contact (opt_calli's optimiser over the contact's regions, control points every
  4 mm, 3 mm where refined), with a press floor of 0.4 mm (`--zmin`: a contact that touches at zero press breaks into two on the
  robot) and, in the works, at most 1 mm of press at the touch-down and the lift (`--z0max`, `--zendmax`: the arm sways there
  and a deeper press leaves a blot); nangong's longest contact keeps its control points within 6 mm of their start
  (`--leash-mm`: with a press floor the optimiser otherwise parked surplus path off the sheet, outside the residual's window).
  The robot execution is the kaishu one (`ref_calli.py`; three ILC passes, more made the tracking worse). Generator:
  `robopaint_brush_mk_task.py --family caoshu` (the first pair took its code from xingshu `yong`: `--template-family xingshu
  --template yong`), then `measure_reference.py` and `mk_tasks.py` as for every pair; the pairs of 2026-10-09 were generated
  with the base image's runtime outside docker (`cs_gen_native.py`). Scoring, thresholds and process rules are those of kaishu
  and xingshu.
- Robot-free checks of the rule on the reference plans (`cs_perturb.py`): one press for the whole sheet, a lift at every region
  boundary or in the middle of every contact, a missing contact, presses ×0.8 or ×1.2 and the naive plan fail on all six; one
  press per contact fails on five (文 passes with IoU 0.83 and a worst region of 0.81); every contact moved ±0.5 mm relative to
  the others fails on the four works, ±1.5 mm on all six.
- Validation (2026-10-09, `eai-robopaint:0.2.0` runtime; Harbor on ws3, jobs `cs-<target>-<mode>-{oracle,nop}-1009`, on the
  committed files): the generator's self-test (scoring service = graders), the verifier's `grade.py` on two fresh replays, and
  Harbor `-a oracle` / `-a nop` in both modes: the oracle scores 1 on 12 of 12 (deterministic, instance exact; standard:
  live = replay), nop 0 on 12 of 12.

  | pair | contacts (cap) | regions | IoU | boundary F | min region | stray | `path_mm` / `max_path_mm` | `mark_width_mm` / min |
  |---|---|---|---|---|---|---|---|---|
  | wen 文 | 2 | 9 | 0.913 | 0.958 | 0.921 | 0.005 | 269 / 810 | 4.57 / 1.37 |
  | zhen 真 | 3 | 12 | 0.941 | 0.955 | 0.894 | 0.003 | 534 / 1610 | 5.86 / 1.75 |
  | nangong 南宮 | 5 | 24 | 0.918 | 0.984 | 0.897 | 0.003 | 890 / 2680 | 3.11 / 0.93 |
  | siwushaonian 四五少年 | 8 | 20 | 0.894 | 0.978 | 0.856 | 0.002 | 641 / 1930 | 2.66 / 0.79 |
  | zhongtiangechuifen 中天哥吹分 | 8 | 17 | 0.826 | 0.979 | 0.859 | 0.006 | 525 / 1580 | 1.91 / 0.57 |
  | beiquelindanshui 北闕臨丹水 | 12 | 27 | 0.844 | 0.972 | 0.849 | 0.005 | 891 / 2680 | 1.98 / 0.59 |

## Lettering: 臨摹 of engraved English round hand (redesigned 2026-10-09)
The family copies public-domain engraved copybook plates with the pointed pen: George Bickham, *The Universal Penman* (London,
1741), in the Getty Research Institute's scan on the Internet Archive (`gri_33125008538056`, NOT_IN_COPYRIGHT; the same book is on
Wikimedia Commons under {{PD-scan}}). It replaced the ten authored minim words (donum ... unpin), which GPT-6 Astra solved 10 of 10
in standard mode on 2026-10-08; none of them was kept, and the broad nib is no longer used. Six targets, each placed 205 mm wide
on the sheet: two flourished headings with all their flourishes, `liberty` ("Liberty.", G. Brooks) and `virtue` ("Virtue.", plate
12), and four copy lines of the plate COPIES (W. Clark): `aim` ("Aim at improvement in every line."), `business` ("Business makes
a Man respected."), `commendation` ("Commendation animates the mind.") and `diligence` ("Diligence in youth is commendable.").
`exemplars.json` also holds two alternates that are not tasks (`excess`, `friendship`).
- **The exemplar** (`scripts/robopaint_lettering/lt_exemplar.py`; spec `exemplars.json`, files `exemplars/<slug>.exemplar.json`):
  the scan's ink (darkness against the local paper level, upsampled x4, Otsu with a hysteresis; short faint gaps of a hairline
  bridged where the scan still has ink), its centre paths and thickness, re-drawn with the task's own pointed pen: one spread axis
  for the whole exemplar (the normal of the shades' mean direction, -33° to -38°) and at every point the tines' spread that gives the
  scan's thickness there; dots and ball terminals become pressed dashes across the axis, as wide as the ball. `target.png` is that
  rendering (`LetterTarget`, unchanged), so every mark of the picture is one the pen can make; against the scan's ink on the sheet
  raster its IoU is 0.86-0.88 (the pen's hairline is 0.4 mm, the engraving's about 0.2-0.3 mm), 99.8-100 % of the scan's ink lies
  within 0.5 mm of the target and all of the target within 0.5 mm of the scan's ink. One known shortfall: the heaviest shade of
  `virtue`'s right swash runs too far from square to the spread axis, so the tines at their full 2.0 mm draw it a little thinner
  than the engraving. QA: the target's outline on the scan (`lt_exemplar.py` writes it), checked for every target before generation.
- **Regions** (the strokes of the scorer's per-stroke coverage): the centre paths joined into trails by good continuation through
  the crossings, each cut into equal pieces of at most 30 mm, so every part of a long flourish counts.
- **The cap** = one contact per connected piece of the exemplar's ink (its own pen lifts, no margin): a whole word, a capital with
  its flourishes, an i's dot. A contact's route runs once over every part of its piece and twice where it has to go back.
- **Rule**: IoU ≥ 0.85, boundary F ≥ 0.80, every region covered ≥ 0.75, stray ≤ 0.04, the cap, the 5 mm registration (the
  family's rule; the copperplate words' 0.70 was dropped: at 0.70 one constant press per contact passes `commendation`), plus the
  process rules.
- **Reference solution** (`solution/plans.json`: the routes; `solution/ref_lettering.py`): the pen at the spread axis, the press
  from the spread, 5 mm/s (slower at sharp turns), lag feed-forward and eight passes of iterative learning control; the recorded
  pass is the best one (every contact one stroke, the smallest tracking error).
- **A new pair**: `lt_exemplar.py` -> `scripts/robopaint_brush_mk_task.py --family lettering --target <slug> --exemplar
  <slug>.exemplar.json` (catalogue and licence record: `scripts/robopaint_templates/lettering/targets.json`; on a host without
  docker but with the image's runtime: `lt_gen_native.py`) -> `measure_reference.py` -> `rules.json` -> `mk_tasks.py`.
- **Rule study** (`lt_perturb.py`, robot-free: the plan drawn with the pen's ideal mark and scored by the unchanged scorer), all six
  targets: the reference plan passes; one constant press (per contact or overall), hairlines only, full press, the spread axis
  turned 90°, contacts shifted alternately by ±0.5 mm, one lift more, one contact skipped, one stroke per region and the shades
  filled with hairline passes all fail. The spread axis turned 30° fails the two words but passes the four lines (their shades are
  short); the press scaled by 0.8 or 1.2 passes all (a lighter or heavier hand).
- **Reference solutions** (the verifier, two fresh replays, deterministic; stray 0 and every contact one stroke on all six):

  | target | cap (strokes) | regions | IoU | worst region | control steps | `path_mm` (longest contact) |
  |---|---|---|---|---|---|---|
  | liberty | 5 | 82 | 0.964 | 0.939 | 13282 | 2644 (1845) |
  | virtue | 4 | 64 | 0.959 | 0.942 | 11633 | 2288 (1833) |
  | aim | 11 | 54 | 0.956 | 0.941 | 7574 | 998 (400) |
  | business | 9 | 54 | 0.955 | 0.955 | 9661 | 1240 (312) |
  | commendation | 9 | 52 | 0.957 | 0.933 | 8262 | 1079 (431) |
  | diligence | 11 | 59 | 0.959 | 0.923 | 10262 | 1343 (459) |
- **Validation** (2026-10-09, on task files byte-identical to the committed ones): Harbor on ws3 (`-a oracle`, `-a nop`, both
  modes; jobs `lt-<slug>-<mode>-<agent>-1009`): the oracle scores 1 on 12 of 12 (deterministic; standard: live = replay, no infra error), nop 0 on 12 of 12. The generator's self-test (the scoring service's metrics equal the
  graders'; the agent side's actions equal the reference's) and `tests/grade.py` on the native `eai-robopaint:0.2.0` runtime
  (reference 1, empty trajectory 0, all six) agree.

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
- Agent egress is an allowlist (the model APIs and the package registries) on every task, because the sources of some targets are public.
- Frozen inputs over 2 MB: 9 of the 11 oil reference pictures (`target.png`, 2.0–2.5 MB, 5 copies per pair).
  - They are photographic scans, so lossless re-encoding gets only 5 of the 9 under 2 MB.
  - They stay as frozen (the instance hash covers their pixels). The 2 MB limit is for results.

## Time budget (D8)
7200 s for every task of both modes, longer than the default 3600 s:
- The agent first has to learn the brush's mark from test strokes on the practice sheet: width against press depth, the
  drag of the tuft, the paint's blending. The privileged mode gives the exact sheet but no brush model.
- Every stroke on the main sheet is irreversible in standard mode.
- Works and paintings take tens to thousands of strokes (stroke caps up to 71 for a calligraphy work and 2546 for an oil
  painting), each at the arm's real speed.

Lettering ran at 5400 s before protocol v1.0 and now has 7200 s like the rest. Results are grouped by budget (see Results).

## The target is only a picture
`target.png` (RGB) in both modes. Its source (glyph outlines, pen paths, the exemplar's paint coverage) stays in the
graders' copy of the instance. Nothing derived from it is in the agent's container (`ci_checks/check-robopaint-leak.sh`).

## Scoring
Success needs the picture rule and the process rules; `final_reward` is the continuous score.
- The picture rule: every quantity is taken after the best global shift of the sheet within 5 mm. Success needs every threshold.
  - Calligraphy and lettering: IoU of the inked areas, boundary F, per-stroke (lettering: per-region) coverage, stray ink and a
    stroke cap.
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
| kaishu, xingshu, caoshu, lettering | **Colouring in fails:** `path_mm` > `max_path_mm` (3 × the reference solution's `path_mm`, rounded up to 10 mm) **and** `mark_width_mm` < `min_mark_width_mm` (0.3 × the reference's, rounded down to 0.01 mm). `mark_width_mm` = the area each stroke inks on its own (its own mark, coverage ≥ 0.5; overlaps between different strokes count again), summed over the strokes, / `path_mm`: the marks' average width. |
| acrylic, oil | **Path budget:** `path_mm` ≤ `max_path_mm` (3 × the reference's, rounded up to 100 mm). **Strokes are sweeps:** `scribble_share` ≤ 0.10, the share of `path_mm` in strokes longer than 2.5 × the diagonal of their bounding box (taken as at least 10 mm): zigzags, back-and-forth fills, spirals, loops (a sweep out and back along one line is about 2). |

The numbers per task: `max_path_mm` 3230–7880 mm (kaishu), 1200–6060 mm (xingshu), 810–2680 mm (caoshu), 3000–7940 mm
(lettering), 32300–51700 mm (acrylic), 51400–86500 mm (oil); `min_mark_width_mm` 0.99–1.34 mm (kaishu), 1.12–3.06 mm (xingshu),
0.57–1.75 mm (caoshu), 0.10–0.13 mm (lettering: below the pointed pen's 0.4 mm hairline, so for the pointed pen the colouring-in
rule never fires; Lettering).

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

## Oil: the pointed brush (2026-10-09)
The oil family was saturated (GPT-6 Astra, high: 11 of 11 in both modes, 2026-10-08) and its paintings looked coarse next to the
originals. The cause was the brush, and the rule was calibrated on what that brush can do:
- **The old brush.** `tanda/oil-03-paint` at `radius_log_offset` 0.6 drew no solid mark narrower than about 5 mm. libmypaint
  scatters the dabs (`offset_by_random` 0.4, `tracking_noise` 0.2) over the brush's base radius at any pressure, so a light press
  paints a 5 mm band of small dabs, not a line. The reference solutions painted 279–456 strokes of 5–11 mm marks. At the 1 mm
  judging scale that is about a 17–29 px mosaic of the picture. target.png (1024 px) and the sheet raster (0.22 mm/px) were not
  the limit: at 1 mm, target.png matches a 3840 px copy of the original to ΔE 0.2–0.4.
- **The brush now.** The same preset made pointed: `offset_by_random` and `tracking_noise` get a pressure input, so they grow with
  the pressure as the dab radius does (0 at no pressure, the preset's value from 40 % on). It is frozen as `brush.preset_json` and
  stays CC0.
  - Straight strokes at 40 mm/s are about 2 mm wide at a 1.25 mm press, 2.5 mm at 1.5 mm, 3 mm at 2 mm, 4.2 mm at 3 mm, 6 mm at
    4 mm, 8 mm at 5 mm and 11 mm from 6 mm on. A full press makes the old marks.
  - With the same ~1650-stroke plan, the old brush scores like the old reference (Starry Night ΔE 7.6, SSIM 0.63). The new brush
    scores ΔE 5.9, SSIM 0.73.
- **The reference solutions.** Each is a new stroke program from the layered painter (`program.json` `optimiser`): a ground of
  rows at a 7 mm press, then 4 layers of curved strokes at 4, 2.5, 1.6 and 1.3 mm presses (marks of about 6, 3.6, 2.6 and 2.1 mm).
  - `solution/ref_oil.py` executes it with the program's `motion`: a 6 mm hover between strokes, quick dips and short holds.
    Without `motion`, a program moves as before. On the old Starry Night program, `motion` saves 24 % of the control steps (34159
    to 25872) with the same picture scores.
  - 1316–1697 strokes and 49.7k–62.0k control steps: 41–52 of the episode's 60 simulated minutes (the 72000-step guard is
    unchanged).
- **The rule.** It is the generator's calibration on that execution, with the SSIM margin raised to 0.04 (0.03 before). With
  0.03, the reference painted 50 % faster misses on one painting (Pearl Earring, SSIM 0.849 against 0.85); with 0.04, no coarse
  painting passes. The stroke cap is 1.5 × and the path budget 3 × the reference, as before.

| Painting | Reference strokes (old → new) | Reference ΔE / SSIM (old → new) | Rule ΔE / p90 / SSIM / edge (old → new) |
|---|---|---|---|
| wanderer | 288 → 1333 | 3.66 / 0.843 → 2.73 / 0.913 | 4.1 / 8.5 / 0.81 / 0.64 → 3.1 / 5.5 / 0.87 / 0.78 |
| temeraire | 299 → 1580 | 4.06 / 0.860 → 3.49 / 0.894 | 4.5 / 8.0 / 0.83 / 0.39 → 3.9 / 6.5 / 0.85 / 0.59 |
| pearlearring | 300 → 1638 | 5.16 / 0.802 → 3.98 / 0.884 | 5.7 / 12.5 / 0.77 / 0.61 → 4.4 / 8.5 / 0.84 / 0.76 |
| milkmaid | 300 → 1677 | 6.20 / 0.727 → 4.53 / 0.852 | 6.9 / 14.5 / 0.69 / 0.49 → 5.0 / 9.5 / 0.81 / 0.74 |
| monalisa | 290 → 1686 | 6.43 / 0.761 → 4.70 / 0.863 | 7.1 / 13.0 / 0.73 / 0.52 → 5.2 / 8.5 / 0.82 / 0.70 |
| bathers | 304 → 1673 | 6.43 / 0.743 → 4.92 / 0.849 | 7.1 / 13.0 / 0.71 / 0.50 → 5.5 / 9.0 / 0.80 / 0.74 |
| saintevictoire | 442 → 1691 | 7.60 / 0.651 → 6.24 / 0.741 | 8.4 / 14.0 / 0.62 / 0.29 → 6.9 / 11.5 / 0.70 / 0.47 |
| starrynight | 456 → 1682 | 7.64 / 0.595 → 5.91 / 0.721 | 8.4 / 15.5 / 0.56 / 0.28 → 6.5 / 11.5 / 0.68 / 0.52 |
| cypresses | 279 → 1640 | 8.77 / 0.598 → 6.77 / 0.727 | 9.7 / 17.5 / 0.56 / 0.43 → 7.5 / 12.5 / 0.68 / 0.65 |
| cafeterrace | 295 → 1667 | 9.84 / 0.538 → 7.22 / 0.703 | 10.9 / 20.0 / 0.50 / 0.27 → 8.0 / 13.5 / 0.66 / 0.57 |
| irises | 437 → 1630 | 12.09 / 0.452 → 9.57 / 0.567 | 13.4 / 23.5 / 0.42 / 0.16 → 10.6 / 17.5 / 0.52 / 0.35 |

**Study.** Robot-free, the rule calibrated on the robot reference, all 11 paintings:
- **Pass:** the reference shifted by 1 or 2 mm (also diagonally), its press × 0.85 and × 1.15, its speed × 0.75 and × 1.5, and
  the same painter with about 1150 strokes on 10 of 11 paintings (Irises fails on edge correlation).
- **Fail:** the old reference, the same painter with about 800 strokes, the plan without its two finest layers, 10 % or 25 % of
  the strokes dropped, and the layer order reversed.
- **Process rules.** An Astra colour-in fill of the earlier version passes the new Starry Night picture rule (ΔE 5.48, SSIM
  0.722), but its sweep share is 0.37, so the process rules still decide it.

**Generation and validation.** `scripts/robopaint_brush_mk_task.py` was run unchanged, outside docker, in the image's runtime
copied 1:1 to a host without docker (checked bit-identical against the docker image), then `measure_reference.py` and `mk_tasks.py`:
- The generator's self-test passed on 11 of 11 pairs (scorer equals graders; the agent's actions equal the reference's).
- The privileged pipeline (scoring service, `solution/solve.sh`'s replay, `tests/grade.py`) gives oracle 11 of 11: success,
  deterministic, instance_exact, process rules met, `s.score()` equal to the verifier. nop is 0 of 11.
- Harbor 0.23 end to end on ws3, 2026-10-09, all 11 pairs in both modes (jobs `hires1009-<painting>-<mode>-<agent>`, 44 trials):
  - `-a oracle` scores 1 on 22 of 22: deterministic, instance_exact and the process rules met; the standard twins also
    `live_matches_replay` 11 of 11, `infra_error` 0;
  - `-a nop` scores 0 on 22 of 22; no grader errors.
  - The trials ran on files identical to this commit except for text: the task.toml description and the program's text fields in
    `solution/` (the preset is named "made pointed"). The graders, the frozen instances, the tooling and the oracle trajectories are
    byte-identical.

**New names (`-i01`).** The frozen instances (the brush preset) and the verifiers (the thresholds) changed, so the eleven pairs are
new tasks (PROTOCOL §2.8): `robopaint-oil-<painting>-i01` replace `-i00`. The generator keeps each committed pair's instance index
(`--refresh`, `mk_tasks.py`). The renamed dirs differ from the validated ones above only by `-i00` → `-i01` in `task.toml`, `README.md`
and the standard twin's `solution/oracle_meta.json` (checked file by file). After the rename:
- the privileged pipeline on the `eai-robopaint:0.2.0` runtime (scoring service, `solution/solve.sh`'s replay, `tests/grade.py`
  with two fresh replays) scores 11 of 11 again: success, deterministic, instance_exact, the process rules met, `s.score()` equal
  to the verifier, and every recorded trajectory equal to `solution/oracle_qpos.npy`;
- Harbor 0.23 on ws3 (jobs `rpp-pr-{oracle,nop}-{priv,std}-1009`), wanderer and temeraire in both modes: `-a oracle` 4 of 4
  (deterministic, instance_exact, process rules met; standard: `live_matches_replay`, `infra_error` 0), `-a nop` 0 of 4.

**Standard mode.** The reference's stream through the current 2.2 server:
- Natively (the image's runtime, an idle 128-thread host): Starry Night's 60797 steps take 598 s, 102 control steps/s with
  `video="none"` (the standard oracle's setting). The client's defaults (every camera, mp4) run at 51 control steps/s.
- In the Harbor runs above (ws3, 1-min load 75–180): 645–906 s per pair, 67–88 control steps/s.

One reference execution therefore takes 9–13 % of the 7200 s budget, or about 20 min (17 %) with the client's defaults.

**Still out of reach.**
- A copy remains an impressionist one: about a 33–48 px mosaic of the picture at 1 mm.
- The 16 premixed paints (k-means of the picture) cannot reach small, bright colours. 0.1 % (Wanderer) to 7.8 % (Irises) of the
  sheet is more than ΔE 12 from every paint, for example Starry Night's star cores and white church, and Irises' bright petals.
  The palette is unchanged.

## Grading and determinism
- Fresh-process replays: the final states of two replays must agree (`deterministic`), and `live_matches_replay` is
  reported.
- The episode has no terminal state. It ends with the agent phase, a simulator error, or the 72000-control-step runaway
  guard.
- Crash recovery (standard mode, docs/STANDARD_MODE.md §13):
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
- No verdict is infrastructure, never the agent's 0 (standard mode, `tests/grade.py`, 2026-10-10): `infra_error = 1` when
  `final.json` is missing, unreadable, or without a verdict (not `finalized`, or neither the replays' `deterministic`
  nor a give-up after crashes), and when the replays could not run (`gpu_lost`, or a replay process without a result
  although the episode had actions). `sim_error = 1` marks an episode that a simulator error ended. The hook writes
  `final.json` whole (temporary file + rename).
- Malformed requests (standard mode, `environment/sim/server.py`, second review of 2026-10-10): every field of `/submit`
  and `/observe` is checked before anything is executed (`parse_submit` / `parse_observe`; `note` included, which was
  read after the chunk had run), and whatever a malformed field raises is a 400 that leaves the episode alive. Before, a
  non-string `note`, a null `dt` / `seconds` / `video_fps` and a negative or absurd `video_fps` were a 500 that ended the
  episode (`sim_error = 1`, the agent's 0). Null is the default; `video_fps` is accepted in [0, 1000]. Test:
  `scripts/robopaint_strict/tests/test_server_requests.py` (needs numpy; the checks are taken from `server.py` by `ast`).
- Instance drift (privileged mode, `tests/grade.py`, second review of 2026-10-10): a frozen instance the verifier does
  not rebuild (`instance_ok = 0`) is `grader_error = 1` + `infra_error = 1` (it was a plain 0), and `infra_error = 1`
  goes with every `grader_error = 1`.
- Verifier time (2026-10-10). A trajectory may have 72,000 control steps (`rcb_brush.MAX_STEPS`), and the oil references
  already have 49.7k-62.0k. Two fresh replays at the 67-102 steps/s measured above take 24-36 min plus two scene builds:
  - privileged: `[verifier] timeout_sec = 3600` (was 1800, which a 62k-step reference at 67 steps/s already exceeded: the
    trial had no reward); each replay process gets 1650 s (`--replay-timeout-s`), and one that runs past it is
    `grader_error = 1`. The two replays stay sequential: two sessions at once would not fit the verifier's declared
    minimum (2 CPUs, 3 GB).
  - standard: the collect hook has 5400 s (was 3600): up to 1500 s for a service that is resuming to end its episode,
    then the same two replays.
- Privileged deliverable: a file that is not a readable trajectory (not an npz, pickled or object arrays, no `actions`,
  a wrong shape, NaN/inf, more than 72,000 rows) is `bad_trajectory = 1` (was `grader_error = 1` for the unreadable
  ones); every `reward.json` has `deterministic`.
- The privileged `scorer` service has `restart: on-failure:6` (2026-10-10). It keeps no state a request needs: after a
  restart the next `s.score()` replays the posted actions from the reset. Known limit: the scorer is inside the trial's
  resource scope (PROTOCOL §2.10: in privileged mode every service is; `scripts/task_resources.toml` adds 5 GiB for it
  to the trial's memory limit and caps it at 7 GiB). With `RCB_LIMITS_ENFORCE=1` an out-of-memory kill inside the
  scorer would therefore count against the agent, which cannot enter that container but does decide how many actions
  it posts. Taking it out of the scope is a change to `scripts/rcb_monitor/inject.py` (the service class) and the
  limit rule, not to the task.

## Tooling (file names)
| main's convention | RoboPaint |
|---|---|
| `environment/rcb_traj.py` (privileged tooling, `Session`) | `environment/rcb_brush.py` |
| `tests/rcb_traj.py` | `tests/rcb_brush.py` + `tests/rcb_brush_score.py` |
| — | `environment/scorer/` (privileged `s.score()`: `rcb_scorer.py` + the scoring module) |
| standard sidecar | `environment/sim/server.py` (the 2.2 adapter), `finalize.sh` (the collect hook), the brush tooling and its scorer, and from `scripts/eai_standard/`: `rcb_limited.py`, `rcb1.py`, `run.sh` |
| `rcb_client.py`, `rcb1.py` | the same names (`scripts/eai_standard/`) |
| — | `rcb_brush_strict.py` (the process rules, graders' side only): `tests/` and `environment/scorer/` (privileged), `environment/sim/` (standard) |

Every copy of the tooling is byte-identical within a family and across the six families
(`ci_checks/check-robopaint-tooling.sh`). The 2.2 layer is byte-identical to `scripts/eai_standard/`
(`ci_checks/check-tooling-identity.sh`).

## Declarations
- **Tooling: thin wrappers only.** The agent gets the robot's low-level actions (joint targets, brush-tip poses), the
  sheets, rendering and replay. No stroke planner or painting skill is added to the agent's tooling; the reference
  solutions keep theirs under `solution/`.
- **World-frame information (D7).** Standard tasks never say where things are in the world: no sheet heights or centres,
  no well positions, no pixel-to-world formula (STANDARD_MODE.md §10, `check-standard-texts.sh`).
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

More in STANDARD_MODE.md §16.

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
