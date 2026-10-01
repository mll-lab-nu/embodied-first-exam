# RoboPaint

Brush art on ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU): a Panda holding a brush or pen copies a picture onto a paper
sheet, dipping in an ink stone or paint wells, with a practice sheet beside it. `simulator = "maniskill"`,
`robot = "franka-panda"`. Families: 楷书 kaishu (35 characters), 行书 xingshu (16), lettering (10 words), acrylic (10) and
oil (11) paintings, each as a privileged task `robopaint-<family>-<target>-i00-privileged` and its standard twin
`...-i00-standard`; the line family (9 line drawings) is excluded from the benchmark.

## Tasks and generators
- `scripts/robopaint_brush_mk_task.py` (a task pair of a brush family, from `scripts/robopaint_templates/<family>/` and a
  committed template pair of the family) and `scripts/robopaint_line_mk_task.py`. The brush model runs on the CPU (`rcb_brush.py`: the dynamic virtual brush of
  Wang et al., IROS 2020, for calligraphy; broad-nib and pointed pens for lettering; libmypaint 1.6.1 for the paintings).
- Benchmark-specific metadata: `difficulty`, `medium`, `stroke_count`, `structure`, `characters` (TAXONOMY).

## Image and host
- `images/robopaint/` (ManiSkill 3.0.1, SAPIEN 3.0.3, Spline-FRIDA, a patched libmypaint); public in the EAI registry.
  Every container needs an NVIDIA GPU: SAPIEN needs a Vulkan device to build the scene and render.
- Agent egress is an allowlist (model APIs only) on every task: the sources of some targets are public.

## Time budget (D8)
7200 s, uniform across the benchmark (the lettering family, generated with 5400 s, moves to 7200 s with its
regeneration). Longer than the default because the agent first has to learn the brush's mark from test strokes on the
practice sheet, and every stroke on the main sheet is irreversible.

## The target is only a picture
`target.png` (RGB) in both modes. Its source (glyph outlines, pen paths, the exemplar's paint coverage) stays in the
graders' copy of the instance; nothing derived from it is in the agent's container (`ci_checks/check-robopaint-leak.sh`).

## Scoring
After the best global shift of the sheet within 5 mm: calligraphy and lettering use IoU of the inked areas, boundary F,
per-stroke coverage, stray ink and a stroke cap; paintings use blurred CIELAB ΔE, SSIM of L*, edge correlation and paint
coverage. Success needs every threshold; `final_reward` is the continuous score. Privileged mode: `s.score()` asks a
`scorer` sidecar (the graders' copy), so the agent may check itself. Standard mode: no score at all; the service's episode
is replayed in two fresh processes and scored afterwards.

## Grading and determinism
- Fresh-process replays: the canvas of two replays must agree (`deterministic`); `live_matches_replay` reported.
- Crash recovery (docs/STANDARD_MODE_2_2.md §13): resume class `exact`; the adapter persists its last tip target
  (`persist=("tip_target",)`: the start of the next `ee_pose` line). Scene builds are fast (the default watchdog is enough).
- The episode has no terminal state: it always ends with the agent phase.

## Tooling (file names)
| main's convention | RoboPaint |
|---|---|
| `environment/rcb_traj.py` (privileged tooling, `Session`) | `environment/rcb_brush.py` (the brush families) or `environment/rcb_paint.py` (line) |
| `tests/rcb_traj.py` | `tests/rcb_brush.py` + `tests/rcb_brush_score.py` (or `rcb_paint.py` + `rcb_paint_score.py`) |
| — | `environment/scorer/` (privileged `s.score()`: `rcb_scorer.py` + the scoring module) |
| standard sidecar | `environment/sim/server.py` (2.2 adapter), `run.sh`, `finalize.sh`, the brush tooling and its scorer |
| `rcb_client.py`, `rcb1.py` | the same names (`scripts/eai_standard/`) |

Every copy of the tooling is byte-identical within a family and across the families of a stack
(`ci_checks/check-robopaint-tooling.sh`).

## Declarations
- **Tooling: thin wrappers only.** The robot's low-level actions (joint targets, brush-tip poses), the sheets, rendering
  and replay. No stroke planner or painting skill is added to the agent's tooling; the reference solutions keep theirs
  under `solution/`.
- **World-frame information (D7).** Standard tasks never say where things are in the world: no sheet heights or centres,
  no well positions, no pixel-to-world formula (STANDARD_MODE_2_2.md §10, `check-limited-texts.sh`). Accepted consequence:
  the calibrated `canvas_cam` above the main sheet tells roughly where the sheet is. Privileged tasks give the sheets
  through the tooling.

## Standard mode (eai-standard/2.2)
`joint_position` (7) and `ee_pose` (7, brush-tip targets `dt` apart, IK per control step, at most 0.25 m/s); four static
cameras (`canvas_cam`, `practice_cam`, `scene_cam`, `side_cam`); SAPIEN depth (geometry only: ink and paint never show);
`/kinematics` on SAPIEN's pinocchio model (7); 28 proprio columns. STANDARD_MODE_2_2.md §16.

## Licences
ManiSkill and SAPIEN: Apache-2.0; Spline-FRIDA (code and weights): GPL-3.0, its source is in the image; libmypaint: ISC
(patched), mypaint-brushes: CC0-1.0; calligraphy exemplars as stated in each task's `NOTICE-exemplar.md`.
