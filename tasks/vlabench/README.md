# VLABench

[VLABench](https://github.com/OpenMOSS/VLABench)'s native manipulation tasks (Franka Panda, MuJoCo + dm_control), each
on one frozen scene instance, in both modes: 36 instances, 72 tasks.

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/vlabench -a codex -m openai/gpt-6-astra
```
Some images are not on a public registry: build them first ([Getting the images](#getting-the-images)).

## Getting the images

All 72 tasks (privileged and standard) use the simulator image `ghcr.io/mll-lab-nu/efe-private:vlabench-0.1.0`, which
is not published (VLABench's asset set has no licence that allows redistributing it). Build it locally from public
sources (GitHub, PyPI and the Hugging Face dataset `lerobot/vlabench-assets` @ `08d7a44`, anonymous, ~12 GB, checked by
`git lfs fsck`); the files image `efe:vlabench-files` is public and pulled by the task builds.

```bash
docker build -f images/vlabench/Dockerfile -t ghcr.io/mll-lab-nu/efe-private:vlabench-$(cat images/vlabench/VERSION) .
harbor run -d embodied-first-exam@all -p tasks/vlabench -a codex -m openai/gpt-6-astra
```

| | |
|---|---|
| upstream | VLABench @ `cf588fe60c0c7282174fe979f5913170cfe69017` (MIT), assets `lerobot/vlabench-assets` @ `08d7a44`, MuJoCo 3.2.2, dm_control 1.0.22 |
| tasks | `tasks/vlabench/vlabench-<task>-i00-privileged` and `tasks/vlabench/vlabench-<task>-i00-standard` |
| metadata | `simulator = "vlabench"`, `robot = "franka-panda"`, `family = "vlabench/<task>"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/efe-private:vlabench-0.1.0` (`images/vlabench/`), CPU only, ~15 GB (12 GB assets) |
| standard service | `rcb_service.py` (main's HumanoidBench copy, `eai-standard/2.1`) + each standard task's `environment/sim/server.py` |
| standard client | the shared client base and exact pins of `embodied_first_exam/standard/` (`client.env`, `client-requirements.txt`); `rcb_client.py` / `rcb1.py` as in main's HumanoidBench tasks |
| instances | the instances and references, imported from PR #4 @ ad3c510, committed only in the privileged tasks (`environment/instance.json`, `solution/oracle.npy`). The task directories are the deliverable; the tooling that built them is kept outside this repository. |

## Scope
VLABench @ cf588fe has 96 native tasks that PR #4 surveyed. A task is in when it has a reference solution that this
benchmark re-verifies on its frozen instance and whose instruction identifies the task:
36 tasks. Left out:
- 41 with no reference: VLABench's own expert sequence does not reach the task's success on the frozen instance;
- 13 that could not be frozen (the scene does not build or does not reset bit-exactly);
- 3 whose PR #4 "reference" is a recorded failure (complex_seesaw_use, hammer_loose_nail, set_dining_table);
- 3 that verify but were dropped in review: select_fruit_semantic duplicates select_fruit_common_sense
  (same scene hashes, reference, instruction and check), and select_book_semantic and set_study_table carry VLABench's
  unfilled instruction template (a literal "..." where the target book's description belongs);
- PR #4's `*-sensor-only` variants, which are an access mode, not VLABench tasks.

## Task definition
- **Instance.** VLABench's own episode configuration for the task (scene, objects, conditions, instruction) and its
  seed, plus the hashes of the compiled model and of the initial state (`instance.json`, ~2 KB). `vlb_tool.Session`
  rebuilds the scene with every random source seeded and refuses to run if either hash differs. Copied into
  `environment/`, `tests/` and `environment/sim/`.
- **Actions.** VLABench's own: 9 absolute position targets per control step (0.1 s, 100 physics steps), the 7 arm
  joints (rad) and the 2 fingers (m, 0 … 0.04). In standard mode this is the `joint_position` action type (PROTOCOL
  §4.4 SHOULD). VLABench's model sets no arm joint limits; the Panda's documented limits are given as facts.
- **Success.** VLABench's own success check, the task's termination condition (`task.should_terminate_episode`). The
  native episode ends the moment it holds, so a trajectory ends there and the graded state is its final state
  (PROTOCOL §3): the privileged verifier rejects a trajectory with actions after the termination
  (`invalid_trajectory`), and the standard service ends the episode with `reason = "success"`.
- **Predicates are VLABench's.** They are graded as upstream defines them, including their looseness: e.g.
  `select_fruit`'s containment checks the fruit's root point against the plate's footprint and a 0–0.1 m height band,
  not that the fruit rests on the plate (found by the red-team trial). Changing them would make it another benchmark.
- **Instructions say what is graded.** Where VLABench's instruction does not say what its check requires, the task
  states it instead (the README's Details row quotes VLABench's own
  wording, which also stays in the instance and in privileged mode in `s.state()["instruction"]`). 24 tasks: e.g. the
  `*_qa` and `select_painting` answers are button presses; `heat_food` needs the food in the microwave, the door closed
  and the start button pressed; `hammer_nail_and_hang_picture` needs the nail driven in and the painting brought to it;
  `select_billiards*` count only VLABench's target pocket (its position is given); `texas_holdem` checks the five
  cards VLABench's own ranking picks, which are named; `select_mahjong*` and `select_fruit_common_sense` name the
  placemat or plate; `select_poker*` say grasp and lift. The checks themselves are unchanged.
- **Length.** Privileged deliverables have 1 ≤ T ≤ 4000 control steps (400 s of robot time; PR #4's bound). Standard
  episodes have a technical cap of 9000 control steps (`spec.max_control_steps`, PROTOCOL §4.5 MAY): the video's
  re-run of the episode (~40 ms a step, about 360 s at the cap, plus a scene build and rendering) must fit the collect
  hook, which waits for the verdict until 1440 s and for the video until 2880 s of its 2910 s.
- **World frame.** Metres; the robot's base at (0, -0.4, 0.78) facing +y (VLABench's default; (0, -0.4, 0.6) for
  `select_billiards*` and (0, -0.7, 0.7) for `find_unseen_object`, from VLABench's per-series robot configuration): x
  to the robot's right, y forward (across the table), z up; quaternions w x y z. Stated in both instructions and in
  `/spec` (`frames`).
- **Privileged mode.** `vlb_tool.Session`: every entity's pose, grasp keypoints and place points, the robot's state,
  VLABench's general skills (pick, place, pull, press, …) as planning primitives, inverse kinematics, unlimited resets,
  self-replay. VLABench's per-task experts are removed from the image.
- **Standard mode.** Four cameras (`forward`, `left`, `right` fixed; `wrist` on the hand), RGB 320×320, depth on
  request, intrinsics and pose in `/spec`; proprioception: joint angles and velocities, finger positions, the hand's
  pose and the last command. No object poses, no task conditions, no success signal before the end (`meta.task` is not
  used: VLABench's goals are relations between objects, not a target point).
- **Egress.** VLABench's experts are public upstream, so `task.toml` allowlists the model APIs and the package registries only (as HumanoidBench and
  DexToolBench do).

## Image
`images/vlabench/Dockerfile` is the full, pinned recipe: Python 3.10.18 by digest, pinned pip
(`requirements.txt`), VLABench and rrt-algorithms at fixed commits, the assets at a fixed commit with `git lfs fsck`,
then `strip_experts.py`, which removes every `get_expert_skill_sequence`, `configs/task2code.json` (a per-task skill
sequence; no runtime code reads it), the evaluation code and configs, the source tree's `.git` and `scripts/`.
VLABench's general skills and its success predicates stay: the privileged mode offers the skills, the verifier grades
with the predicates. `images/vlabench/build_local.sh` builds the same recipe from an assets checkout already on disk.

The instance hashes are checked on every load, so a build whose physics differs shows up as `grader_error`, never as a
silent change.

## Standard-mode service

**Grading: the live episode** (PROTOCOL H.4). The sim sidecar judges the episode it runs with VLABench's own success
check (the task's termination condition, `should_terminate_episode`, at every control step; `step()` in
`environment/sim/server.py`) and ends it there; `rcb_service.py` writes that verdict
(`graded_by = "live"`, `replays = 0`) once the agent's container is stopped. The frozen start is checked on the live
simulator: `vlb_tool.Session` refuses a scene whose initial state or compiled model hash differs from `instance.json`
(`instance_mismatch`), and `start_sha` (`initial_state_sha256`) is checked when the episode begins; both give up as
infrastructure (`infra_error = 1`) before the agent is served. The video is one render pass over `trajectory.npz` after
the verdict (`render_video`: a fresh scene, CPU physics, OSMesa rendering; median about 150 s a trial, up to about 8
minutes); it never changes the verdict. `infra_error = 1` only for no or an unfinalized `final.json`, a give-up after
crashes not all inside the agent's calls, a reset whose scene does not rebuild, and `instance_mismatch`; a simulator
error raised by the agent's call, crashes inside its calls, a timeout and a failure are the agent's 0.
`environment/sim/rcb_service.py` is a byte copy of HumanoidBench's standard tasks' `environment/sim/rcb_service.py`
(protocol `eai-standard/2.1`: four endpoints, RCB1, no reset unless `budget.reset > 0`, journal + checkpoints with at
most two resumes, startup watchdog, SIGUSR1 collect hook, `/data` evidence, verdict before video, 413 / 500 handling).
`final.json` is `finalized` the moment the verdict is written, before the video is rendered (`video_pending` while it
renders); the collect hook waits for the verdict and then, as long as its timeout allows, for the video, so a slow,
hung or killed render costs the video and never the verdict. The reset budget is pinned to 0 in the compose file (the
instruction says one episode, no reset).
`server.py` is VLABench's adapter (the `Sim` contract): cameras, proprioception, `joint_position` clipping into the
actuators' bounds, holding the last targets while watching, the frozen start's hash, and the video's re-run (`vlb_tool.Session`). The
agent's client and the verifier (`grade.py`: `success = live_success`) are main's copies too.

## Rebuilding
```bash
docker build -t ghcr.io/mll-lab-nu/efe-private:vlabench-$(cat images/vlabench/VERSION) \
    -f images/vlabench/Dockerfile .                  # from the repository root; ~15 GB
python3 scripts/task_conventions.py --check tasks/vlabench/vlabench-*
bash ci_checks/run_all.sh tasks/vlabench/vlabench-*
```

## Evidence
Measured when the instances were frozen, for the 36 tasks: the instance rebuilds with matching
model and initial-state hashes and is not solved at the start; `reset()` is bit-exact; the reference ends with the
task's success at its last step; two replays in fresh processes end in the live state's hash and succeed. The 3
tasks dropped in review verified the same way; the 3 whose PR #4 references are recorded failures did not (their
frozen inputs are not kept).

Harbor runs: `-a oracle` scores 1 on every privileged task and on 8 standard tasks (heat_food, texas_holdem,
take_out_cool_drink, book_rearrange, find_unseen_object, select_painting, friction_qa, select_fruit_common_sense);
`-a nop` scores 0 on four tasks per mode (select_fruit, heat_food, friction_qa, insert_flower). Scripted cheat attempts
score 0: in privileged mode, tooling patched to report success, a do-nothing trajectory, a tampered instance and a
`sitecustomize.py` in `/app/output`, forged reward files; in standard mode, hidden endpoints (`/reset`, `/state`,
`/success`, `/data/final.json`: 404), a wrong action type, a `dt` that is not a multiple of 0.1 and NaN rows (400,
nothing runs), and a forged `final.json` in the agent's container (never collected). Two agent red-team trials (Codex,
told to make the verifier pass without solving) score 0.

## Reference hashes
Final-state hashes of some references (live = replay 1 = replay 2):

| task | seed | control steps | state hash |
|---|---|---|---|
| select_fruit | 0 | 138 | `b9102e6cfd86dc28…` |
| heat_food | 0 | 793 | `0f7a3aea9581b8af…` |
| friction_qa | 0 | 224 | `507033633967865c…` |
| texas_holdem | 0 | 660 | `c77b7967d5b4788f…` |

## Open questions
- **The standard episode cap.** 9000 control steps (900 s of robot time) keeps the video's re-run well inside the
  collect hook (2910 s; a re-run costs ~40 ms a step on a 7950X). An agent can reach the cap before its time limit;
  raising it needs a longer collect timeout.
- **Tasks without a reference.** The 57 tasks left out could come in later with `oracle = "none"` and human review
  (PROTOCOL §2.7).
- **Privileged difficulty.** With VLABench's skills as planning primitives the privileged mode is largely solved;
  the standard twin carries the difficulty.
- **eai-standard/2.1 or 2.2.** The standard twins serve 2.1 with main's HumanoidBench layer (byte copies); moving to the
  shared 2.2 layer (`embodied_first_exam/standard/`) would add its optional capabilities (depth as uint16, `robot_spec`,
  `/kinematics`, a per-call wall-clock bound) and its CI identity check.

## Screening

The benchmark owner's screening (ten runs, one trial per run and task directory). A directory is **easy** when a run solved it: a graded success within the task's time limit.
Where only one or two of the later runs solved a directory Luna had failed, their logs were checked for shortcuts and
for any access to tests, solutions or graders. It is **hard** when GPT-6 Luna and every later run that attempted it
failed, GPT-6 Astra and Claude Opus 5.5 among them; a standard directory that only Astra solved is hard as well. It is
**unverified** when only Luna attempted it and failed (the later runs only take bases Luna solved in no mode), and
**pending** without a Luna verdict. A base whose every mode is easy, and every base Luna solved in some mode, is left out of the core set (`docs/core_set.toml`); its tasks keep their names.

Runs: Luna `codex-gpt6_luna-xhigh`; Astra `codex-gpt6_astra-high`; Opus `claude_code-opus_5_5-high`; Sol 6.1
`codex-gpt6_1_sol-high`; Sol `codex-gpt6_sol-high`; Gemini 3.8 Flash `antigravity_cli-gemini_3_8_flash-high`; Gemini 4
Argon `antigravity_cli-gemini_4_argon-high`; DeepSeek V4.1 Flash `dsh-deepseek_v4_1_flash-high`; GLM 5.3 Flash
`claude_code-glm_5_3_flash-high`; Qwen3.8 27B `claude_code-qwen3_8_27b-high`.

By directory: 51 easy, 0 hard, 21 unverified, 0 pending.

| base | privileged | standard |
|---|---|---|
| `vlabench-add-condiment-i00` | easy: Astra, Opus, DeepSeek V4.1 Flash | easy: Astra, Opus |
| `vlabench-book-rearrange-i00` | easy: Luna | unverified |
| `vlabench-find-unseen-object-i00` | easy: Luna | easy: Luna |
| `vlabench-friction-qa-i00` | easy: Luna | unverified |
| `vlabench-hammer-nail-and-hang-picture-i00` | easy: Luna | unverified |
| `vlabench-heat-food-i00` | easy: Astra, Opus, Sol 6.1 | easy: Opus |
| `vlabench-insert-bloom-flower-i00` | unverified | easy: Luna |
| `vlabench-insert-flower-i00` | easy: Luna | unverified |
| `vlabench-magnetism-qa-i00` | easy: Luna | easy: Luna |
| `vlabench-play-math-game-i00` | easy: Luna | unverified |
| `vlabench-put-box-on-painting-i00` | easy: Luna | easy: Luna |
| `vlabench-reflection-qa-i00` | easy: Luna | easy: Luna |
| `vlabench-select-billiards-common-sense-i00` | easy: Luna | unverified |
| `vlabench-select-billiards-i00` | easy: Luna | unverified |
| `vlabench-select-billiards-spatial-i00` | easy: Luna | unverified |
| `vlabench-select-book-spatial-i00` | easy: Luna | easy: Luna |
| `vlabench-select-chemistry-tube-common-sense-i00` | easy: Luna | easy: Luna |
| `vlabench-select-chemistry-tube-i00` | easy: Luna | unverified |
| `vlabench-select-chemistry-tube-semantic-i00` | easy: Luna | easy: Luna |
| `vlabench-select-chemistry-tube-spatial-i00` | easy: Luna | easy: Luna |
| `vlabench-select-drink-i00` | easy: Luna | easy: Luna |
| `vlabench-select-fruit-common-sense-i00` | easy: Luna | easy: Luna |
| `vlabench-select-fruit-i00` | easy: Luna | unverified |
| `vlabench-select-mahjong-i00` | easy: Luna | unverified |
| `vlabench-select-mahjong-semantic-i00` | easy: Luna | unverified |
| `vlabench-select-mahjong-spatial-i00` | easy: Luna | unverified |
| `vlabench-select-nth-largest-poker-i00` | easy: Luna | unverified |
| `vlabench-select-painting-i00` | easy: Luna | easy: Luna |
| `vlabench-select-poker-i00` | easy: Luna | unverified |
| `vlabench-select-poker-semantic-i00` | easy: Luna | unverified |
| `vlabench-select-poker-spatial-i00` | easy: Luna | easy: Luna |
| `vlabench-select-specific-type-book-i00` | easy: Luna | unverified |
| `vlabench-select-toy-i00` | easy: Luna | easy: Luna |
| `vlabench-select-unique-type-mahjong-i00` | easy: Luna | unverified |
| `vlabench-take-out-cool-drink-i00` | easy: Luna | unverified |
| `vlabench-texas-holdem-i00` | easy: Luna | unverified |

Judgment calls: `vlabench-select-drink-i00`: solved in the first test evaluation; repo-wide changes only since.
