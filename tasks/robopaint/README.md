# RoboPaint

## Overview

Brush art on ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU): a Franka Panda holding a brush or a pen copies a
picture onto a paper sheet, dipping in an ink stone or in paint wells, with a practice sheet beside it that is never
scored. 43 targets in six groups:

| group | targets | tool and medium | target picture |
|---|---|---|---|
| 楷书 kaishu | 2 works (永字八法, 麟鳳龜龍) | Chinese brush (30 mm tuft), ink | rendered glyph outlines |
| 行书 xingshu | 6 characters, 2 works | Chinese brush, ink | a historical scan, binarised |
| 草书 caoshu | 2 characters, 4 works | Chinese brush, ink | a historical scan, binarised |
| lettering | 2 flourished words, 4 copy lines (English round hand) | pointed dip pen, ink | an engraved plate, re-drawn with the task's pen |
| acrylic | 10 paintings | paint brush (15 mm tuft), 10 premixed paints | a painting made by the robot from a hidden stroke program |
| oil | 11 paintings | pointed paint brush, 16 premixed paints | a square crop of a public-domain painting |

Each target is a privileged task `robopaint-<group>-<target>-i<NN>-privileged` and a standard task
`...-i<NN>-standard` on the same frozen instance (`i00`; the oil paintings `i01`): 86 task directories.
`[metadata] family` is `robopaint_<group>_<target>`. Every task has **process rules** on top of the picture rule: the
exemplar has to be written or painted with strokes, the way a person does, not coloured in (Grading).

- **privileged**: the agent has the full simulator (`rcb_brush.py`, `Session`): exact sheet images, unlimited resets,
  and the grader's own score through a scoring service. It hands in one trajectory of joint targets, which the
  verifier replays open-loop.
- **standard**: the simulator runs in a `sim` sidecar the agent cannot open. The agent gets the client and the same
  service as MCP tools: camera images, proprioception, `joint_position` or `ee_pose` chunks, one episode, no reset, no
  sheet readout, no brush model and no score. Ink and paint are permanent, and the brush's mark has to be learned from
  test strokes on the practice sheet.

The task directories are the deliverable; the tooling that built them is kept outside this repository. Quick start:

```bash
harbor run -d embodied-first-exam@all -p tasks/robopaint -a <agent> -m <model>
```

Every image is public: Harbor pulls it.

## Upstream and license

RoboPaint is one of this repository's original suites (MIT License; Wang et al., 2026, the Embodied First Exam paper;
suite page <https://www.embodied-first-exam.ai/suite/robopaint/>); it has no upstream benchmark. Its components:

- Simulator: ManiSkill 3.0.1 ([haosulab/ManiSkill](https://github.com/haosulab/ManiSkill) @ `a4a4f92`, tag v3.0.1;
  Tao et al., 2024) and SAPIEN 3.0.3, both Apache License 2.0.
- Calligraphy brush: a re-implementation of the dynamic virtual brush of Wang et al. (IROS 2020) in `rcb_brush.py`.
  The pointed pen and the broad-nib model are the repository's own.
- Paint: libmypaint 1.6.1 (ISC License) and the mypaint-brushes 2.0.2 presets (CC0-1.0).
- Spline-FRIDA (`cmubig/Frida` @ `1652973`, GPL-3.0, code and weights) is in the base image with its source. No task
  of this benchmark uses it.
- Exemplars (no non-commercial terms anywhere):
  - kaishu: Make Me a Hanzi `graphics.txt` @ `bddc96d` (derived from the fonts AR PL KaitiM GB and AR PL UKai), Arphic
    Public License; the tasks carry `ARPHICPL.TXT` and the modification notice in `NOTICE-exemplar.md`.
  - xingshu: Wikimedia Commons `File:神龍蘭亭序全.JPG`, the Shenlong hand copy (attributed to 馮承素, Tang) of Wang
    Xizhi's 蘭亭序; PD-Art / PD-old-100-1923. The scroll writes 脩 for 修.
  - caoshu: Wikimedia Commons `File:張旭 古詩四帖.jpg`, 張旭《古詩四帖》 (attributed to Zhang Xu, Tang, Liaoning
    Provincial Museum); PD-old-70.
  - lettering: George Bickham, *The Universal Penman* (London, 1741), the Getty Research Institute's scan on the
    Internet Archive (`gri_33125008538056`, NOT_IN_COPYRIGHT; on Wikimedia Commons under PD-scan).
  - acrylic: the robot's own paintings (CC0-1.0) of stroke programs made after public-domain paintings on Wikimedia
    Commons (each task's `[metadata] source_image`).
  - oil: square crops of public-domain paintings on Wikimedia Commons (each task's `[metadata] source_image`,
    `source_artist`), downscaled to the sheet.

## Changes from upstream

- **The robot**: ManiSkill's PandaStick, holding a tool: a rigid handle and a collision-free tuft or point whose tip
  is the TCP (Chinese brush 30 mm, paint brush 15 mm, dip pen 6 mm). The handle hits the paper when the tip is a tuft's
  length below the surface.
- **libmypaint, deterministic**: libmypaint 1.6.1 `malloc`s the brush, and its first `stroke_to` reads settings before
  computing them, so results depended on heap contents. The image's build patches both allocations to `calloc` and
  fails if the patch does not apply. A small shim (`images/robopaint/rcb_mypaint.c`) drives the library.
- **The oil brush made pointed**: `tanda/oil-03-paint` at `radius_log_offset` 0.6, with a pressure input on
  `offset_by_random` and `tracking_noise`, so both grow with the pressure as the dab radius does (0 at no pressure, the
  preset's value from 40 % on). Without it the preset draws no solid mark narrower than about 5 mm. The preset is frozen
  in each instance as `brush.preset_json`. Straight strokes at 40 mm/s are about 2 mm wide at a 1.25 mm press, 3 mm at
  2 mm, 6 mm at 4 mm and 11 mm from 6 mm on. The acrylic tasks use `tanda/acrylic-03-paint`.
- **Exemplars**:
  - xingshu and caoshu: the scan is thresholded (Otsu, with a hysteresis that keeps faint ligatures), whole ink
    components are kept, a ligature into a neighbouring character is cut, a dashed hairline is bridged along its own
    trace, a dry stroke (飛白) is closed within its own area, and the edge is smoothed. The ink is split into regions
    along the brush contacts (caoshu: at most 30 mm of centre path per region). A caoshu work keeps its column as
    written, its characters in one 210 mm frame.
  - lettering: the scan's ink, its centre paths and thickness, re-drawn with the task's own pointed pen (one spread axis
    for the whole exemplar, the tines' spread giving the scan's thickness at every point), placed 205 mm wide. Against
    the scan's ink its IoU is 0.86-0.88 (the pen's hairline is 0.4 mm, the engraving's about 0.2-0.3 mm). Regions are
    the centre paths cut into pieces of at most 30 mm. The heaviest shade of `virtue`'s right swash comes out a little
    thinner than the engraving.
  - kaishu: the Make Me a Hanzi outlines, unmodified, placed on the sheet; one region per stroke.

## Interface

World frame (both modes): z up, table top z = 0, the robot's base at (-0.615, 0, 0), x away from the base, y to the
robot's left; quaternions wxyz. Control runs at 20 Hz (physics 100 Hz, 5 substeps). The main sheet is a 227.18 mm
square at world (-0.100, 0.000), the practice sheet 227.18 × 99.41 mm on the robot's right of it; both have a 1024 px
raster along the 227.18 mm side (0.2219 mm per pixel). The target is only a picture: `target.png` (RGB, covering the
main sheet exactly) in both modes. Its source (glyph outlines, pen paths, the exemplar's paint coverage, the regions)
stays in the graders' copy of the instance.

### Privileged

- `/opt/tools/rcb_brush.py` (`from rcb_brush import Session`): `Session(instance="/app/instance.json")`; `reset()`
  (exact: blank sheets, a dry tool, the start pose), thin primitives (`move_tip`, `move_joints`, `hold`,
  `set_joint_targets`), IK / FK, measured state, `canvas()` and `ink()` (the exact sheet images), `strokes()` (each
  contact's 100 Hz samples and its own mark), `score()`, `record_start()` / `record_stop()`, `replay()`,
  `save_trajectory()`, `render_frame()` for the four cameras.
- An action is 7 absolute joint targets (rad) for one control step, ManiSkill's `pd_joint_pos`. The runaway guard is
  72,000 control steps (`MAX_STEPS`, 1 h of simulated time).
- `s.score()` asks the `scorer` sidecar (`environment/scorer/`, the graders' copy of the instance with the process
  rules): it replays the actions executed since the last reset and returns the grader's metrics, `success` and
  `final_reward` included. The agent's own copy of the instance holds the scene and the rule, not the truth.
- No stroke planner or painting skill is in the agent's tooling; the reference solutions keep theirs under
  `solution/`.

### Standard

The robot is a service in the `sim` sidecar (wire protocol `eai-standard/3.0`).

| | |
|---|---|
| actions | `joint_position` (7, streamed at 20 Hz, linear or hold) and `ee_pose` (7: tip targets `dt` apart, a straight line per row with one IK solve per control step, at most 0.25 m/s; at most 400 rows and 10 s per submit) |
| cameras | four static cameras: `canvas_cam` (1024², over the main sheet), `practice_cam` (512×1024), `scene_cam` (640×480), `side_cam` (640×360, a grazing view of the tool's height) |
| depth | SAPIEN depth, geometry only: ink and paint never show |
| `/kinematics` | SAPIEN's Pinocchio model (7 joints), stateless |
| proprio | 28 columns: joints, tip pose (xyz + wxyz), joint velocities, PD drive efforts |
| images per call | at most 640 |

- Standard tasks never say where things are in the world: no sheet heights or centres, no well positions, no
  pixel-to-world formula (`ci_checks/check-world-frame-texts.sh`). Accepted consequence: the
  calibrated `canvas_cam` above the main sheet tells roughly where the sheet is.
- `/finish` ends the episode; painting has no terminal state, so nothing else but the session's end, a simulator error
  or the runaway guard ends it. There is no step budget.

## Grading

Success needs the **picture rule** and the **process rules**; every task's README states its own numbers, which are in
the graders' copy of the instance (`target.success`). `final_reward` is a continuous score and does not decide success.

### The picture rule

The main sheet is first registered to the exemplar: one global whole-pixel shift, at most 5 mm along each axis (a best
shift on the window's edge counts as no shift). Every quantity is taken at that shift.

- Writing (kaishu, xingshu, caoshu, lettering; ink coverage ≥ 0.5): IoU of the inked areas, boundary F within 1 mm, the
  coverage of each region of the exemplar, stray ink (more than 1 mm from the exemplar, as a share of its area), and a
  cap on the inked contacts with the main sheet. The shift maximises the ink overlap.
  - kaishu, xingshu, caoshu: IoU ≥ 0.80, boundary F ≥ 0.75, every region ≥ 0.80, stray ≤ 0.04.
  - lettering: IoU ≥ 0.85, boundary F ≥ 0.80, every region ≥ 0.75, stray ≤ 0.04.
- Paintings (both pictures in CIELAB, blurred with σ = 1 mm; the shift minimises the mean colour difference): mean and
  90th-percentile ΔE over the painted area, SSIM of L*, the correlation of the L* gradient magnitudes, paint IoU, and a
  cap on the painted contacts. The oil paintings are scored inside the sheet's central area, 8 mm in from its edges.
  - acrylic: mean ΔE ≤ 2.0, p90 ≤ 6.0, SSIM ≥ 0.92, edge correlation ≥ 0.80, paint IoU ≥ 0.95. The exemplar is the
    robot's own execution of a stroke program, so it is reachable exactly.
  - oil: per painting (Tasks), the reference solution's execution by the robot with a margin (SSIM 0.04 below it);
    paint IoU ≥ 0.96.

### The process rules

Only inked (painted) contacts on the main sheet count; a contact is inked when the tool was loaded at its touch-down,
and the practice sheet is free. `path_mm` is the total length of the tip's path while it presses on the main sheet,
summed over the 100 Hz physics samples.

| Groups | Rule |
|---|---|
| kaishu, xingshu, caoshu, lettering | **Colouring in fails:** `path_mm` > `max_path_mm` **and** `mark_width_mm` < `min_mark_width_mm`. `mark_width_mm` = the area each contact inks on its own (coverage ≥ 0.5; overlaps between contacts count again), summed, / `path_mm`: the marks' average width. A long path with wide marks (strokes written over again) and thin marks on a short path (a light hand) both pass. |
| kaishu, xingshu, caoshu | **Strokes are counted as written:** a contact is cut where the tip moves more than 5 mm along the sheet without marking it (its mark narrower than 0.1 mm), and a piece longer than `max_stroke_path_mm` counts as ⌈length / `max_stroke_path_mm`⌉ strokes; the counted strokes must stay within the cap. **Strokes are sweeps:** at most 10 % of the pieces' length in pieces longer than 12 × their bounding-box diagonal (taken as at least 10 mm). |
| acrylic, oil | **Path budget:** `path_mm` ≤ `max_path_mm`. **Strokes are sweeps:** at most 10 % of `path_mm` in contacts longer than 2.5 × their bounding-box diagonal (taken as at least 10 mm): zigzags, back-and-forth fills, spirals, loops (a sweep out and back along one line is about 2). |

The limits come from a reference solution of each task: `max_path_mm` = 3 × its `path_mm` (rounded up to 10 mm, the
paintings to 100 mm), `min_mark_width_mm` = 0.3 × its mark width (rounded down to 0.01 mm), `max_stroke_path_mm` =
5 × its longest piece (rounded up to 10 mm). In lettering, `min_mark_width_mm` (0.10-0.13 mm) lies below the pointed
pen's 0.4 mm hairline, so the colouring-in rule never fires there for that pen. The writing groups' cap also counts
contacts (the picture rule's own count).

`success` = the picture rule (`image_success`) ∧ the process rules (`strict_ok`). `final_reward` = the picture rule's
continuous score (writing: the IoU; paintings: max(0, 1 − mean ΔE / 20)), scaled by cap / strokes above the cap, by
min(1, `max_path_mm` / `path_mm`) when colouring in or over the path budget, and by (1 − scribble share) when the sweep
rule fails. `reward.json` reports `image_success`, `image_final_reward`, `strict_ok`, `path_mm`, `max_path_mm`,
`mark_width_mm`, `min_mark_width_mm`, `colour_in`, `path_budget_ok`, `scribble_share`, `scribble_ok`,
`n_strokes_counted` and `strokes_counted_ok` next to the picture rule's metrics.

The rules are applied by `rcb_brush_strict.py` (graders' side only), a `Session` subclass whose `score()` adds them:
the privileged verifier replays with it, the privileged scoring service imports it (`RCB_TOOL_MODULE=rcb_brush_strict`)
and the standard sim service scores the live sheet with it (`RCB_TOOL=/srv/rcb_brush_strict.py`). The agent's container
holds `rcb_brush.py` only.

**Calibration.** The thresholds were set on replays of the reference solutions and of 360 recorded agent trajectories,
scored with and without the process rules; every trajectory near a threshold was inspected as a path picture.

| Population | Runs | Picture rule only | With the process rules | Flagged by the rules |
|---|---|---|---|---|
| reference solutions | 82 | 82 | 82 | 0 |
| recorded agent trajectories, picture-rule successes | 162 | 162 | 56 | 106: colouring in, serpentine and zigzag fills |
| recorded agent trajectories, picture-rule failures | 198 | 0 | 0 | 25 |

- Writing: the colouring-in trajectories reach at most 0.97 of their mark-width limit; the closest normal one is at
  1.15. Ten normal trajectories that retrace heavily reach 3.1-5.0 × the reference's path, overlapping colouring in
  from 4.5 ×, which is why the path alone is not the rule.
- Paintings: normal trajectories have a scribble share ≤ 0.021 and a path ≤ 1.44 × the reference's; fills are at
  ≥ 0.143. At a ratio of 2 the out-and-back strokes would count, at 3 a meander fill would pass. Rows of straight
  strokes stay allowed (the oil reference lays its underpainting that way).
- Counted strokes: on the references and genuine recorded calligraphy, every contact is exactly one piece (the longest
  non-marking stretch inside a contact is 2.9 mm), the longest piece is at most 2.98 × the reference's, and the
  largest scribble ratio is 9.95. Recorded colouring-in trajectories fail a counted-stroke rule too, independently.
- Accepted leniency: the closest colouring-in trajectory sits at 0.97 of its mark-width limit, and the closest painting
  fill at 1.43 × the sweep limit. A contact may still go over its own stroke a few times.

### Privileged (replay)

`tests/grade.py` replays `/app/output/trajectory.npz` once, in a fresh process (`rcb_brush_strict.py replay`), from
`tests/instance.json` (the graders' copy); success = the replayed main sheet meets the rules and the rebuilt frozen
instance matches the recorded one.

- Agent failures (0): `missing_trajectory`; `bad_trajectory` (not an npz, pickled or object arrays, no `actions`, a
  shape other than (T, 7), NaN / inf, more than 72,000 rows); `wrong_family` (the file's `task` is another task's).
- Infrastructure (`grader_error = 1`, `infra_error = 1`): a replay without a result or past its 1650 s
  (`--replay-timeout-s`), a frozen instance the verifier does not rebuild (`instance_ok = 0`).
- PhysX and the brush models (libmypaint single-threaded, with the determinism patch) run on the CPU: a live run, an
  in-process replay and a fresh-process replay end in the same state bit for bit (`rcb_brush.py selftest`); rendering
  does not change it. `replay.mp4` and `canvas.png` never affect the verdict.
- `[verifier] timeout_sec = 3600`: a replay of 72,000 control steps takes up to 18 min at the measured 67-102 steps/s.
- The `scorer` sidecar keeps no state a request needs (`restart: on-failure:6`; the next `s.score()` replays from the
  reset). It is the benchmark's own service: the resource monitor records it outside the agent's scope
  (`BENCHMARK_SERVICES` in `images/monitor/rcb_monitor/inject.py`). If the kernel kills it for memory and the trial then
  ends without success, the trial is `infra_error = 1` (`resource_service_oom`).

### Standard (live)

The verdict is the live episode's; nothing is replayed to grade it. The collect hooks stop the agent's container
(`kill -9 -1`), then `finalize.sh` signals the service, which ends the episode, commits a contact still pressed, scores
its live main sheet with `rcb_brush_strict.py` (the same scorer and rules as the privileged replay) and writes
`final.json` (`graded_by = "live"`, `replays = 0`). Then it renders the recorded trajectory once into `replay.mp4`; a
failed render never changes the verdict. The trajectory and the live sheets (`canvas_live.png`,
`canvas_live_practice.png`) are saved.

- The episode ends at `/finish`, at the session's end, at the runaway guard (reason `step_limit`, judged as the sheet
  stands) or on a simulator error (the agent's 0, `sim_error = 1`).
- Infrastructure (`infra_error = 1`): `final.json` missing, unreadable or without a verdict; a give-up the service
  caused (`sim_crashed`, `resume_failed`, `instance_mismatch`: a frozen instance that does not rebuild in the sidecar is
  refused before the agent is served); a live sheet the service could not score after a normal end (`grade_error`).
  Crashes inside the agent's own calls (`sim_crashed_on_call`) are the agent's 0.
- Crash recovery: resume class `exact` (CPU PhysX and the CPU brush models repeat bit for bit in a fresh process); the
  journal rows are the 7 joint targets of each control step, and the adapter persists its last `ee_pose` tip target.
- `RCB_STARTUP_TIMEOUT_S = 600`: in 285 measured standard trials the episode started at most 126 s after the
  environment setup began (median about 30 s), so 600 s is more than four times the slowest start.
- The collect hook has 2820 s: up to 1500 s for a service that is resuming to end its episode, then the live score and
  one render pass.

## Tasks

Writing (the cap is both the counted strokes and the inked contacts; regions = the exemplar's regions; `—`: no
counted-stroke rule):

| group | task (without mode) | exemplar | regions | cap | `max_path_mm` | `min_mark_width_mm` | `max_stroke_path_mm` |
|---|---|---|---|---|---|---|---|
| kaishu | `robopaint-kaishu-linfengguilong-i00` | 麟鳳龜龍 | 71 | 71 | 7880 | 0.99 | 920 |
| kaishu | `robopaint-kaishu-yongzibafa-i00` | 永字八法 | 21 | 21 | 3230 | 1.34 | 600 |
| xingshu | `robopaint-xingshu-feng-i00` | 風 | 9 | 6 | 2150 | 2.42 | 2240 |
| xingshu | `robopaint-xingshu-he-i00` | 和 | 7 | 6 | 1850 | 1.93 | 1770 |
| xingshu | `robopaint-xingshu-huifenghechang-i00` | 惠風和暢 | 43 | 28 | 6060 | 1.15 | 1250 |
| xingshu | `robopaint-xingshu-maolinxiuzhu-i00` | 茂林脩竹 | 35 | 21 | 3160 | 1.12 | 1220 |
| xingshu | `robopaint-xingshu-nian-i00` | 年 | 10 | 7 | 1780 | 2.2 | 1080 |
| xingshu | `robopaint-xingshu-shan-i00` | 山 | 5 | 4 | 1200 | 3.06 | 1360 |
| xingshu | `robopaint-xingshu-xian-i00` | 賢 | 15 | 7 | 2630 | 1.88 | 1930 |
| xingshu | `robopaint-xingshu-yong-i00` | 永 | 9 | 6 | 1450 | 2.25 | 1330 |
| caoshu | `robopaint-caoshu-beiquelindanshui-i00` | 北闕臨丹水 | 27 | 12 | 2680 | 0.59 | 860 |
| caoshu | `robopaint-caoshu-nangong-i00` | 南宮 | 24 | 5 | 2680 | 0.93 | 1960 |
| caoshu | `robopaint-caoshu-siwushaonian-i00` | 四五少年 | 20 | 8 | 1930 | 0.79 | 970 |
| caoshu | `robopaint-caoshu-wen-i00` | 文 | 9 | 2 | 810 | 1.37 | 720 |
| caoshu | `robopaint-caoshu-zhen-i00` | 真 | 12 | 3 | 1610 | 1.75 | 1590 |
| caoshu | `robopaint-caoshu-zhongtiangechuifen-i00` | 中天哥吹分 | 17 | 8 | 1580 | 0.57 | 880 |
| lettering | `robopaint-lettering-aim-i00` | Aim at improvement in every line. | 54 | 11 | 3000 | 0.12 | — |
| lettering | `robopaint-lettering-business-i00` | Business makes a Man respected. | 54 | 9 | 3730 | 0.1 | — |
| lettering | `robopaint-lettering-commendation-i00` | Commendation animates the mind. | 52 | 9 | 3240 | 0.12 | — |
| lettering | `robopaint-lettering-diligence-i00` | Diligence in youth is commendable. | 59 | 11 | 4040 | 0.1 | — |
| lettering | `robopaint-lettering-liberty-i00` | Liberty. | 82 | 5 | 7940 | 0.13 | — |
| lettering | `robopaint-lettering-virtue-i00` | Virtue. | 64 | 4 | 6870 | 0.12 | — |

Paintings (mean / p90 ΔE at most, SSIM of L* and edge correlation at least; paint IoU ≥ 0.95 (acrylic) or 0.96
(oil)):

| group | task (without mode) | picture | ΔE mean / p90 | SSIM | edge | cap | `max_path_mm` |
|---|---|---|---|---|---|---|---|
| acrylic | `robopaint-acrylic-applesoranges-i00` | Apples and Oranges (after Cézanne) | 2.0 / 6.0 | 0.92 | 0.80 | 390 | 33900 |
| acrylic | `robopaint-acrylic-bedroom-i00` | The Bedroom (after van Gogh) | 2.0 / 6.0 | 0.92 | 0.80 | 388 | 40300 |
| acrylic | `robopaint-acrylic-bluehorses-i00` | The Large Blue Horses (after Marc) | 2.0 / 6.0 | 0.92 | 0.80 | 390 | 35900 |
| acrylic | `robopaint-acrylic-greatwave-i00` | The Great Wave off Kanagawa (after Hokusai) | 2.0 / 6.0 | 0.92 | 0.80 | 376 | 37900 |
| acrylic | `robopaint-acrylic-kajikazawa-i00` | Kajikazawa in Kai Province (after Hokusai) | 2.0 / 6.0 | 0.92 | 0.80 | 377 | 44300 |
| acrylic | `robopaint-acrylic-plumpark-i00` | Plum Park in Kameido (after Hiroshige) | 2.0 / 6.0 | 0.92 | 0.80 | 384 | 42300 |
| acrylic | `robopaint-acrylic-redfuji-i00` | Fine Wind, Clear Morning (after Hokusai) | 2.0 / 6.0 | 0.92 | 0.80 | 407 | 51700 |
| acrylic | `robopaint-acrylic-suddenshower-i00` | Sudden Shower over Shin-Ohashi Bridge and Atake (after Hiroshige) | 2.0 / 6.0 | 0.92 | 0.80 | 380 | 40500 |
| acrylic | `robopaint-acrylic-sunflowers-i00` | Sunflowers (after van Gogh) | 2.0 / 6.0 | 0.92 | 0.80 | 380 | 41700 |
| acrylic | `robopaint-acrylic-vision-i00` | Vision after the Sermon (after Gauguin) | 2.0 / 6.0 | 0.92 | 0.80 | 390 | 32300 |
| oil | `robopaint-oil-bathers-i01` | Bathers at Asnières (after Seurat) | 5.5 / 9.0 | 0.80 | 0.74 | 2496 | 63600 |
| oil | `robopaint-oil-cafeterrace-i01` | Cafe Terrace at Night (after van Gogh) | 8.0 / 13.5 | 0.66 | 0.57 | 2507 | 68600 |
| oil | `robopaint-oil-cypresses-i01` | Wheat Field with Cypresses (after van Gogh) | 7.5 / 12.5 | 0.68 | 0.65 | 2504 | 51600 |
| oil | `robopaint-oil-irises-i01` | Irises (after van Gogh) | 10.6 / 17.5 | 0.52 | 0.35 | 2486 | 55600 |
| oil | `robopaint-oil-milkmaid-i01` | The Milkmaid (after Vermeer) | 5.0 / 9.5 | 0.81 | 0.74 | 2499 | 71900 |
| oil | `robopaint-oil-monalisa-i01` | Mona Lisa (after Leonardo) | 5.2 / 8.5 | 0.82 | 0.70 | 2507 | 69900 |
| oil | `robopaint-oil-pearlearring-i01` | Girl with a Pearl Earring (after Vermeer) | 4.4 / 8.5 | 0.84 | 0.76 | 2453 | 86500 |
| oil | `robopaint-oil-saintevictoire-i01` | Mont Sainte-Victoire (after Cézanne) | 6.9 / 11.5 | 0.70 | 0.47 | 2546 | 57700 |
| oil | `robopaint-oil-starrynight-i01` | The Starry Night (after van Gogh) | 6.5 / 11.5 | 0.68 | 0.52 | 2517 | 62300 |
| oil | `robopaint-oil-temeraire-i01` | The Fighting Temeraire (after Turner) | 3.9 / 6.5 | 0.85 | 0.59 | 2360 | 51400 |
| oil | `robopaint-oil-wanderer-i01` | Wanderer above the Sea of Fog (after Friedrich) | 3.1 / 5.5 | 0.87 | 0.78 | 1974 | 64700 |

- **Reference solutions.** Every task has one in `solution/`: a joint-target plan frozen at generation time
  (`solution/oracle_qpos.npy`). The privileged `solve.sh` replays it; the standard one streams the same targets through
  the client, waits out a service restart and continues from the control step the service reports. The oracle label is
  `partial` on all 86 tasks.
- **Oil thresholds.** Each oil rule is the reference solution's execution by the robot with a margin (SSIM 0.04 below
  it; with 0.03 the reference painted 50 % faster misses on Pearl Earring, with 0.04 no coarse painting passes). The
  references paint 1316-1697 strokes in 49.7k-62.0k control steps, 41-52 of the episode's 60 simulated minutes; their
  stroke cap is 1.5 × and the path budget 3 × the reference. Robot-free checks against the calibrated rule: the
  reference shifted by 1 or 2 mm, its press × 0.85 and × 1.15 and its speed × 0.75 and × 1.5 pass; a coarse 5 mm-mark
  painting, the plan without its two finest layers, 10 % or 25 % of the strokes dropped and the layer order reversed
  fail.

  | painting | reference strokes | reference ΔE / SSIM |
  |---|---|---|
  | wanderer | 1333 | 2.73 / 0.913 |
  | temeraire | 1580 | 3.49 / 0.894 |
  | pearlearring | 1638 | 3.98 / 0.884 |
  | milkmaid | 1677 | 4.53 / 0.852 |
  | monalisa | 1686 | 4.70 / 0.863 |
  | bathers | 1673 | 4.92 / 0.849 |
  | saintevictoire | 1691 | 6.24 / 0.741 |
  | starrynight | 1682 | 5.91 / 0.721 |
  | cypresses | 1640 | 6.77 / 0.727 |
  | cafeterrace | 1667 | 7.22 / 0.703 |
  | irises | 1630 | 9.57 / 0.567 |

- **Limits of the oil copies.** A copy remains an impressionist one, about a 33-48 px mosaic of the picture at 1 mm.
  The 16 premixed paints (k-means of the picture) cannot reach small, bright colours: 0.1 % (Wanderer) to 7.8 %
  (Irises) of the sheet is more than ΔE 12 from every paint.
- **Lettering rule checks** (robot-free, the plan drawn with the pen's ideal mark and the unchanged scorer, all six
  targets): one constant press, hairlines only, full press, the spread axis turned 90°, one lift more, one contact
  skipped and shades filled with hairline passes all fail; the press scaled by 0.8 or 1.2 passes.
- **Caoshu rule checks** (robot-free, on the reference plans): one press for the whole sheet, a lift at every region
  boundary, a missing contact, presses × 0.8 or × 1.2 fail on all six; every contact moved ± 1.5 mm relative to the
  others fails on all six.

## Others

- **Images.**
  - `images/robopaint/` (`ghcr.io/mll-lab-nu/efe:robopaint-<VERSION>`, 0.2.0, public): ManiSkill 3.0.1, SAPIEN 3.0.3,
    the patched libmypaint 1.6.1 with the presets, and Spline-FRIDA; built from the repository root
    (`docker build -f images/robopaint/Dockerfile .`).
  - `images/robopaint-files/`: the files-only image of `embodied_first_exam/benchmarks/robopaint/`
    (`rcb_brush.py`, `rcb_brush_score.py`, `rcb_brush_strict.py`, the two `grade.py`, the sim adapter), pinned by digest
    in `FILES.json`; the tasks' Dockerfiles `COPY --from` it. A change to one of these files needs a new version (bump
    `VERSION`, `python3 scripts/files_image.py build robopaint-files`, push, `pin`), then new digests in the tasks.
  - `images/robopaint-pictures-files/`: the 43 exemplar pictures (`/<task without mode>/target.png`). They are not in
    git; they are in the public Hugging Face dataset `MLL-Lab/embodied-first-exam-public` (folder `robopaint/`), pinned
    by commit and sha256 (`python3 scripts/files_image.py fetch robopaint-pictures-files`).
- **GPU.** Every simulator container needs an NVIDIA GPU: SAPIEN needs a Vulkan device to build the scene and to
  render. Physics and the brush models run on the CPU. Privileged: `main` and `scorer` hold the GPU; standard: `sim`.
- **Frozen inputs over 2 MB.** 9 of the 11 oil pictures (`target.png`, 2.0-2.5 MB) are photographic scans; they stay
  as frozen (the instance hash covers their pixels). The 2 MB limit is for results.
- **Time.** Each task's own `[agent] timeout_sec` (the time limit (Limits)). Works and paintings take tens to thousands
  of strokes at the arm's real speed: one oil reference execution streamed through the standard service takes 10-15
  minutes with `video="none"` (67-102 control steps/s), about 20 minutes with the client's defaults.
- **Tooling file names.** `/opt/tools/rcb_brush.py` (privileged agent), `/tests/rcb_brush.py`, `rcb_brush_score.py`,
  `rcb_brush_strict.py` and `grade.py` (privileged verifier), `environment/scorer/` (the privileged scoring service),
  `environment/sim/` (the standard sidecar: `server.py`, `finalize.sh` and the brush tooling, with the shared standard
  layer from `embodied_first_exam/standard/`).
- **CI.** `ci_checks/benchmarks/robopaint/advisory-tooling.sh` checks that every task takes the one pinned version of
  the shared files; `invariant-leak.sh` admits only the rule keys in the agent's copy of the instance and only
  `rcb_brush.py` from the files-only image in the agent's Dockerfile; `check-world-frame-texts.sh` (Interface).
