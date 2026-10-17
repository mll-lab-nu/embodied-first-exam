# RoboCasa-GR1

RoboCasa's [GR1 tabletop tasks](https://github.com/robocasa/robocasa-gr1-tabletop-tasks) with a Fourier GR1 humanoid
(two arms, waist and two dexterous Fourier hands; fixed base), each on one frozen instance, in both modes:
48 tasks.

| | |
|---|---|
| upstream | robocasa/robocasa-gr1-tabletop-tasks @ `4840e671596f93ca03651524b9f72ffb1aadfeff` (MIT), robosuite @ `51cc017` (1.5.1) with its whole-body mink IK controller (mink 0.0.5), MuJoCo 3.2.6 |
| tasks | `tasks/robocasa-gr1-<task>-i00-privileged` and `tasks/robocasa-gr1-<task>-i00-standard`, 24 each |
| metadata | `simulator = "robosuite"`, `robot = "fourier-gr1"` (to be added to TAXONOMY), `family = "robocasa-gr1/<Env>"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/eai-robocasa-gr1:0.1.0` (`images/robocasa-gr1/`), CPU only, ~24 GB |
| standard client | `python:3.12.14-slim` pinned by digest, pinned pip; `rcb_client.py` / `rcb1.py`: the HumanoidBench tasks' code, the client with a docstring of its own that describes this service |
| generator | `scripts/robocasa-gr1/` (`import_references.sh` -> `frozen/`, `generate.py` -> `tasks/`) |

## Scope
All 24 GR1 tabletop environments with an official demonstration whose reference PR #4 validated, one
instance each (PR #4's `i00`; its other 9 instances of the same environments are not included): PnPBottleToCabinetClose, PnPCanToDrawerClose, PnPCupToDrawerClose, PnPMilkToMicrowaveClose, PnPPotatoToMicrowaveClose, PnPWineToCabinetClose, PosttrainPnPNovelFromCuttingboardToBasketSplitA, PosttrainPnPNovelFromCuttingboardToCardboardboxSplitA, PosttrainPnPNovelFromCuttingboardToPanSplitA, PosttrainPnPNovelFromCuttingboardToPotSplitA, PosttrainPnPNovelFromCuttingboardToTieredbasketSplitA, PosttrainPnPNovelFromPlacematToBasketSplitA, PosttrainPnPNovelFromPlacematToBowlSplitA, PosttrainPnPNovelFromPlacematToPlateSplitA, PosttrainPnPNovelFromPlacematToTieredshelfSplitA, PosttrainPnPNovelFromPlateToBowlSplitA, PosttrainPnPNovelFromPlateToCardboardboxSplitA, PosttrainPnPNovelFromPlateToPanSplitA, PosttrainPnPNovelFromPlateToPlateSplitA, PosttrainPnPNovelFromTrayToCardboardboxSplitA, PosttrainPnPNovelFromTrayToPlateSplitA, PosttrainPnPNovelFromTrayToPotSplitA, PosttrainPnPNovelFromTrayToTieredbasketSplitA, PosttrainPnPNovelFromTrayToTieredshelfSplitA.

## Task definition
- **Instance.** The initial state of an official demonstration episode, frozen in `instance.npz` (~0.1 MB): the MuJoCo
  integration state, the model arrays the scene's reset rewrites, the env's Python task state (env, fixtures, robot,
  controllers, observables) and the NumPy / Python RNG states, with a SHA-256 checked on every load. Rebuilding is
  bit-exact. Copied into `environment/`, `tests/` and `environment/sim/`.
- **Actions.** The robot's native whole-body controller command, one per control step (20 Hz), in both modes: 24
  channels -- the right then the left grip site's absolute pose target in the robot's base frame (XYZ metres,
  axis-angle radians), solved by the whole-body inverse-kinematics controller (mink), then six unscaled Fourier hand
  commands per hand (`little, ring, middle, index, thumb_flexion, thumb_rotation`). This is the controller the
  demonstrations were recorded with. In standard mode the type is `ee_pose` (a planner-executed action, PROTOCOL §4.4
  MAY); a `joint_position` type is not offered (SHOULD): the references are whole-body IK commands, and the GR1's
  29 arm, waist and finger joints are driven through that controller.
- **Success.** The environment's own `_check_success` on the state after the last action (PROTOCOL §3), and not
  already at the start. Both instructions state what it requires, from the upstream source: for the 18
  `PosttrainPnPNovel*` tasks (`tabletop_24dc.py`) the object in the target container (top tier for the tiered basket
  and shelf), not touching the counter, the container upright, both grip sites more than 0.25 m from the object and
  from the container (`any_gripper_obj_far`), and, where the scene has one, the distractor object not in the
  container; for the 6 `PnP*Close` tasks the object's centre inside the cabinet / drawer / microwave and its door
  shut (opening fraction ≤ 0.005). The instructions also give the base frame's world pose (read from the frozen
  instance): the proprio's grip-site positions are in the world frame, the commands in the base frame; the check runs twice per control step and once at reset everywhere (the pattern the references
  were validated with). Every reference's success also holds for 10 more still steps.
- **Determinism.** CPU physics, bit-exact; MuJoCo's process-wide mesh cache is turned off in `casa_tool` (a mesh
  served from the cache can differ from a cold compile of the same file, which breaks bit-exact replay across
  processes), so every build is a cold build.
- **Length.** Privileged deliverables have 1 ≤ T ≤ 3000 control steps; the references have 123–393.
  Standard episodes have no step limit (D1).
- **Standard-mode observations.** The humanoid's six cameras (`robot0_agentview_center/left/right`, `egoview`,
  `robot0_eye_in_right_hand`, `robot0_eye_in_left_hand`; RGB, depth, intrinsics and current poses), its joints
  (positions, velocities), both grip sites' positions, the last command and the instruction. No object poses, reward or
  success signal. Camera images (RGB and depth, in both modes and in replay videos) draw the visual meshes only, as
  robosuite's own cameras do; the collision geoms (geom group 0) are hidden. Watching (`/observe` with `seconds > 0`)
  holds the last command (before the first, the grip sites' current poses): the grip sites stay within a millimetre,
  while the IK's posture term may still move the waist and elbows by a few hundredths of a radian.

## Standard-mode service
`images/robocasa-gr1/standard/server_casa.py`, the same service as the RoboCasa benchmark's (PR #22, not merged
yet): derived from `images/mujoco/limited/server_mj.py`, `eai-standard/2.1`, crash recovery, collect hooks. The collect
hook is `scripts/robocasa-gr1/shared/finalize.sh`; both files are RoboCasa's byte for byte
(`docs/benchmarks/robocasa.md`: verdict final before the video, the hook's budget, request validation).
Since 2026-10-13 the calibration's `cam2world_gl` is the rendered viewpoint, not MuJoCo's left-eye camera 3.4 cm to
its left (`docs/benchmarks/robocasa.md`, service item 10): standard-mode results from before used the offset calibration.

## Egress
The demonstrations (the references) are public, so `task.toml` closes agent egress to the model APIs and the package registries. The image
contains no demonstration data.

## Image
`images/robocasa-gr1/Dockerfile` pins the base image by digest, every pip package, the GR1 tabletop and robosuite
commits, robosuite's mink controller file and every asset archive by SHA-256 (`fetch_assets.sh`). It reproduces the
content of the image the tasks were validated with (built in the PR #4 era as `rcb-robocasa-gr1:0.1.1` from the same
pins, tagged `eai-robocasa-gr1:0.1.0` on the authoring machine). **A clean rebuild from this Dockerfile has not been run
yet** (~9 GB of downloads, ~50 GB of disk): run it and re-check the hashes with `import_references.sh` before
publishing. Licences: code MIT; RoboCasa's own textures, fixtures and object archives (UT Box) CC-BY-4.0; NVIDIA
PhysicalAI-DigitalCousin-Assets (lightwheel, sketchfab meshes) **CC-BY-NC-4.0** (non-commercial; maintainers to
confirm publishing, otherwise `BUILD_ONLY`).

## Rebuilding the tasks
```bash
docker build -t ghcr.io/mll-lab-nu/eai-robocasa-gr1:$(cat images/robocasa-gr1/VERSION) images/robocasa-gr1
bash scripts/robocasa-gr1/import_references.sh <PR #4 checkout>
python3 scripts/robocasa-gr1/generate.py      # ends with scripts/task_conventions.py normalize; re-running reproduces the tasks
python3 scripts/robocasa-gr1/generate.py --check   # writes nothing; exit 1 if tasks/ differs from a fresh render
cd tasks && harbor add --scan . && cd ..
bash ci_checks/run_all.sh tasks/robocasa-gr1-*
```

## Evidence
`scripts/robocasa-gr1/frozen/report.json`, for all 24: not solved at the start; `reset()` bit-exact; the
reference (123–393 actions) succeeds on its final state without truncation; two fresh-process replays end
in the live state's hash and succeed; the success survives 10 more still steps. Same hashes with and without
MuJoCo's mesh cache.

Agent results are not kept in the repository (PROTOCOL D3).

## Easy set

The benchmark owner's screening of 2026-10-17 (results dashboard snapshot 2026-10-17T05:59:33Z; ten runs, one trial per
run and task directory). A directory is **easy** when a run solved it: a graded success within the task's time limit.
Where only one or two of the later runs solved a directory Luna had failed, their logs were checked for shortcuts and
for any access to tests, solutions or graders. It is **hard** when GPT-6 Luna and every later run that attempted it
failed, GPT-6 Astra and Claude Opus 5.5 among them; a standard directory that only Astra solved is hard as well. It is
**unverified** when only Luna attempted it and failed (the later runs only take bases Luna solved in no mode), and
**pending** without a Luna verdict. A base whose every mode is easy is in the easy set (`docs/easy_set.toml`, reason
`solved`): kept under its name and reported apart from the main table.

Runs: Luna `codex-gpt6_luna-xhigh`; Astra `codex-gpt6_astra-high`; Opus `claude_code-opus_5_5-high`; Sol 6.1
`codex-gpt6_1_sol-high`; Sol `codex-gpt6_sol-high`; Gemini 3.8 Flash `antigravity_cli-gemini_3_8_flash-high`; Gemini 4
Argon `antigravity_cli-gemini_4_argon-high`; DeepSeek V4.1 Flash `dsh-deepseek_v4_1_flash-high`; GLM 5.3 Flash
`claude_code-glm_5_3_flash-high`; Qwen3.8 27B `claude_code-qwen3_8_27b-high`.

9 of 24 bases are in the easy set; by directory: 33 easy, 1 hard, 14 unverified, 0 pending.

| base | easy set | privileged | standard |
|---|---|---|---|
| `robocasa-gr1-bottle-to-cabinet-close-i00` | yes | easy: Astra, Opus, Sol 6.1, Sol, Gemini 4 Argon | easy: Astra, Gemini 4 Argon |
| `robocasa-gr1-can-to-drawer-close-i00` |  | easy: Luna | unverified |
| `robocasa-gr1-cup-to-drawer-close-i00` |  | easy: Luna | unverified |
| `robocasa-gr1-cuttingboard-to-basket-i00` | yes | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash, GLM 5.3 Flash | easy: Astra, Opus, Gemini 4 Argon |
| `robocasa-gr1-cuttingboard-to-cardboardbox-i00` |  | easy: Luna | unverified |
| `robocasa-gr1-cuttingboard-to-pan-i00` | yes | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash, GLM 5.3 Flash | easy: Astra, Gemini 4 Argon |
| `robocasa-gr1-cuttingboard-to-pot-i00` | yes | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash, GLM 5.3 Flash | easy: Astra, Opus, Sol 6.1, Gemini 4 Argon |
| `robocasa-gr1-cuttingboard-to-tieredbasket-i00` |  | easy: Luna | unverified |
| `robocasa-gr1-milk-to-microwave-close-i00` |  | easy: Luna | unverified |
| `robocasa-gr1-placemat-to-basket-i00` | yes | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash | easy: Astra, Opus, Sol 6.1, Gemini 4 Argon |
| `robocasa-gr1-placemat-to-bowl-i00` |  | easy: Luna | unverified |
| `robocasa-gr1-placemat-to-plate-i00` |  | easy: Luna | unverified |
| `robocasa-gr1-placemat-to-tieredshelf-i00` |  | easy: Luna | unverified |
| `robocasa-gr1-plate-to-bowl-i00` |  | easy: Luna | unverified |
| `robocasa-gr1-plate-to-cardboardbox-i00` | yes | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, GLM 5.3 Flash, Qwen3.8 27B | easy: Astra, Gemini 4 Argon |
| `robocasa-gr1-plate-to-pan-i00` |  | easy: Luna | unverified |
| `robocasa-gr1-plate-to-plate-i00` |  | unverified | easy: Luna |
| `robocasa-gr1-potato-to-microwave-close-i00` |  | easy: Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon | hard |
| `robocasa-gr1-tray-to-cardboardbox-i00` | yes | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash | easy: Opus, Sol 6.1, Sol |
| `robocasa-gr1-tray-to-plate-i00` |  | easy: Luna | unverified |
| `robocasa-gr1-tray-to-pot-i00` |  | easy: Luna | unverified |
| `robocasa-gr1-tray-to-tieredbasket-i00` | yes | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, DeepSeek V4.1 Flash | easy: Sol 6.1, Gemini 4 Argon |
| `robocasa-gr1-tray-to-tieredshelf-i00` | yes | easy: Astra, Opus, Sol 6.1, Sol, Gemini 3.8 Flash, Gemini 4 Argon, GLM 5.3 Flash | easy: Gemini 4 Argon |
| `robocasa-gr1-wine-to-cabinet-close-i00` |  | easy: Luna | unverified |

Judgment calls: `robocasa-gr1-cuttingboard-to-pan-i00`: Astra's standard success is borderline (the agent doubted its
placement); Gemini 4 Argon's is clean.
