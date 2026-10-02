# RoboPaint

Brush art on ManiSkill 3.0.1 (SAPIEN 3.0.3, PhysX on the CPU): a Panda holding a brush or pen copies a picture onto a paper
sheet, dipping in an ink stone or paint wells, with a practice sheet beside it. `simulator = "maniskill"`,
`robot = "franka-panda"`. Five families, 82 targets: 楷书 kaishu (35 characters and works), 行书 xingshu (16), lettering (10
words, broad nib and pointed pen), acrylic (10) and oil (11) paintings. Each target is a privileged task
`robopaint-<family>-<target>-i00-privileged` and its standard twin `...-i00-standard` on the same frozen instance;
`[metadata].family = "robopaint_<family>_<target>"`. The line family (9 line drawings) is excluded from the benchmark and
not in this repository: its tooling serves only rcb-limited/2.0.

## Tasks and generator
- `scripts/robopaint_brush_mk_task.py` writes a task pair.
  - The code comes from the family's template pair: kaishu and xingshu `yong`, lettering `minim`, acrylic `redfuji`, oil
    `cypresses`. Any committed pair of the family would do. A painting's program is read from the template's
    `solution/programs_json/`, where a pair's own entry is its current program, so a painting pair is remade with itself as
    the template.
  - The standard twin's client and service layer come from `scripts/eai_standard/`.
  - The texts come from `scripts/robopaint_templates/<family>/`.
  - The frozen files are made in the base image (docker, GPU): the instance and the picture, the reference plan, and a
    self-test of the scoring path.
- Every generated task ends with `normalize()` of `scripts/task_conventions.py` (the repository's conventions; `--check`
  passes on every RoboPaint task).
- `--refresh [pair ...]` regenerates committed pairs from their own frozen files, with no docker and no GPU. Rerunning it
  over every pair leaves `git diff tasks/` empty, which is how the generator is checked.
- The texts take their values from the frozen files (`derive_values`). The oil rule is calibrated at generation time on
  the reference solution's own execution (`solution/calibration.json`), and the oil texts are written with the calibrated
  thresholds.
- Benchmark-specific metadata: `difficulty`, `medium`, `stroke_count`, `structure`, `characters` (TAXONOMY).
- Every pair has a real reference solution in `solution/`.
  - The privileged `solution/solve.sh` replays the frozen reference plan.
  - The standard one streams the same joint targets through the client; it waits out a service restart and continues
    from the control step the service reports.
  - The oracle label is `partial` on all 164 tasks (see Oracle evidence).
  - The generator writes each task's `oracle_evidence` from `scripts/robopaint_templates/oracle_evidence.json`.

## Oracle evidence
A task is labelled `oracle = "full"` only if a recorded oracle run scored 1 on byte-identical grader, frozen instance,
tooling and oracle code (lead, 2026-10-01). The RoboPaint oracle runs on record all predate the current files, so every
task is `partial`. Its `oracle_evidence` names the runs and what changed since. This version was validated statically
only (CI, the generator's no-diff rerun, the mock checks); human review in PR #3.

**Release validation**, ws3, 2026-09-28, at each family's release commit. Every target ran Harbor's oracle and nop in
both modes (jobs `<family>-{u,l}-{oracle,nop}-final0928`):

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

**Later runs**:
- After the 2.2 inputs (before the rated limits), ws3, 2026-09-28: kaishu-ai, acrylic-applesoranges and oil-cypresses
  scored oracle 1 and nop 0 in both modes (jobs `p22-<pair>[-limited]-{oracle,nop}`).
- kaishu-yong's standard twin, on files identical to 9eb18edf (before crash recovery), ws3 and ws, 2026-09-29: oracle 1,
  nop 0 (`v22-ws3-oracle-kaishu-yong-0418`, `v22-ws3-nop-kaishu-yong-0419`).

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
Every quantity is taken after the best global shift of the sheet within 5 mm. Success needs every threshold;
`final_reward` is the continuous score.
- Calligraphy and lettering: IoU of the inked areas, boundary F, per-stroke coverage, stray ink and a stroke cap.
- Paintings: blurred CIELAB ΔE, SSIM of L*, edge correlation and paint coverage.
- Privileged mode: `s.score()` asks a `scorer` sidecar (the graders' copy), so the agent may check itself.
- Standard mode: no score at all. The service's episode is replayed in two fresh processes and scored afterwards.

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
`eai-v2-internal/agent-runs`. The runs on record, `codex-gpt6_luna-xhigh` (Codex CLI 0.157.0, GPT-6 Luna, reasoning xhigh):
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
