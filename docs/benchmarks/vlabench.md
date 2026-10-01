# VLABench

[VLABench](https://github.com/OpenMOSS/VLABench)'s native manipulation tasks (Franka Panda, MuJoCo + dm_control), each
on one frozen scene instance, in both modes: 39 instances, 78 tasks.

| | |
|---|---|
| upstream | VLABench @ `cf588fe60c0c7282174fe979f5913170cfe69017` (MIT), assets `lerobot/vlabench-assets` @ `08d7a44`, MuJoCo 3.2.2, dm_control 1.0.22 |
| tasks | `tasks/vlabench-<task>-i00` (privileged) and `tasks/vlabench-<task>-i00-standard` (standard) |
| metadata | `simulator = "vlabench"`, `robot = "franka-panda"`, `family = "vlabench/<task>"`, `oracle = "full"` |
| image | `ghcr.io/embodied-agent-interface-v2-internal/eai-vlabench:0.1.0` (`images/vlabench/`), CPU only, ~15 GB (12 GB assets) |
| standard service | `rcb_service.py` (main's HumanoidBench copy, `eai-standard/2.1`) + `scripts/vlabench/shared/standard/server.py` |
| standard client | `python:3.12.14-slim` pinned by digest, pinned pip; `rcb_client.py` / `rcb1.py` as in main's HumanoidBench tasks |
| generator | `scripts/vlabench/` (`import_pr4.py` → `frozen/`, `freeze.sh` → `frozen/report.json`, `generate.py` → `tasks/`) |

## Scope
VLABench @ cf588fe has 96 native tasks that PR #4 surveyed. A task is in when it has a reference solution that this
benchmark re-verifies on its frozen instance (`scripts/vlabench/freeze.sh`): 39 tasks. Left out, with the reason per task
in `scripts/vlabench/tasks.json` (`excluded`) and `scripts/vlabench/frozen/report.json`:
- 41 with no reference: VLABench's own expert sequence does not reach the task's success on the frozen instance;
- 13 that could not be frozen (the scene does not build or does not reset bit-exactly);
- 3 whose PR #4 "reference" is a recorded failure (complex_seesaw_use, hammer_loose_nail, set_dining_table);
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
- **Length.** Privileged deliverables have 1 ≤ T ≤ 4000 control steps (400 s of robot time; PR #4's bound). Standard
  episodes have a technical cap of 9000 control steps (`spec.max_control_steps`, PROTOCOL §4.5 MAY): the fresh replay
  that grades the episode (~40 ms a step) must fit the collect hook's 900 s.
- **World frame.** Metres; the robot's base at (0, -0.4, 0.78) facing +y: x to the robot's right, y forward (across the
  table), z up; quaternions w x y z. Stated in both instructions and in `/spec` (`frames`).
- **Privileged mode.** `vlb_tool.Session`: every entity's pose, grasp keypoints and place points, the robot's state,
  VLABench's general skills (pick, place, pull, press, …) as planning primitives, inverse kinematics, unlimited resets,
  self-replay. VLABench's per-task experts are removed from the image.
- **Standard mode.** Four cameras (`forward`, `left`, `right` fixed; `wrist` on the hand), RGB 320×320, depth on
  request, intrinsics and pose in `/spec`; proprioception: joint angles and velocities, finger positions, the hand's
  pose and the last command. No object poses, no task conditions, no success signal before the end (`meta.task` is not
  used: VLABench's goals are relations between objects, not a target point).
- **Egress.** VLABench's experts are public upstream, so `task.toml` allowlists the model APIs only (as HumanoidBench and
  DexToolBench do).

## Image
`images/vlabench/Dockerfile` is the full, pinned recipe: Python 3.10.18 by digest, pinned pip
(`requirements.txt`), VLABench and rrt-algorithms at fixed commits, the assets at a fixed commit with `git lfs fsck`,
then `strip_experts.py`, which removes every `get_expert_skill_sequence`, `configs/task2code.json` (a per-task skill
sequence; no runtime code reads it), the evaluation code and configs, the source tree's `.git` and `scripts/`.
VLABench's general skills and its success predicates stay: the privileged mode offers the skills, the verifier grades
with the predicates. `images/vlabench/build_local.sh` builds the same recipe from an assets checkout already on disk.

Local evidence for this PR ran on `eai-vlabench:0.1.0` built as PR #4's `rcb-vlabench:0.1.1` (the same recipe up to
the assets, built with the local-assets variant) plus this Dockerfile's last layers verbatim: the reference machine had
about 30 GB free, less than a from-scratch build needs (~12 GB of LFS objects plus the layer). A clean
from-scratch build is the maintainers' publication step; the instance hashes are checked on every load, so a build
whose physics differs shows up as `grader_error`, never as a silent change.

## Standard-mode service
`environment/sim/rcb_service.py` is a byte copy of main's `scripts/humanoidbench/shared/standard/rcb_service.py`
(protocol `eai-standard/2.1`: four endpoints, RCB1, no reset unless `budget.reset > 0`, journal + checkpoints with at
most two resumes, startup watchdog, SIGUSR1 collect hook, `/data` evidence, verdict before video, 413 / 500 handling).
`server.py` is VLABench's adapter (the `Sim` contract): cameras, proprioception, `joint_position` clipping into the
actuators' bounds, holding the last targets while watching, and the fresh replay (`vlb_tool.Session`). The agent's
client and the verifier (`grade.py`: `success = live_success ∧ replay_success ∧ deterministic`) are main's copies too.

## Rebuilding
```bash
docker build -t ghcr.io/embodied-agent-interface-v2-internal/eai-vlabench:$(cat images/vlabench/VERSION) \
    -f images/vlabench/Dockerfile .                  # from the repository root; ~15 GB
python3 scripts/vlabench/import_pr4.py            # one-off: instances and references from PR #4 (dev/changhe @ ad3c510)
bash scripts/vlabench/freeze.sh                   # re-verify them in the image -> scripts/vlabench/frozen/report.json
python3 scripts/vlabench/generate.py              # -> tasks/vlabench-* ; re-running reproduces them exactly
cd tasks && harbor add --scan . && cd ..
bash ci_checks/run_all.sh tasks/vlabench-*
```

## Evidence
`scripts/vlabench/frozen/report.json` (written by `freeze.sh`), for all 39 tasks: the instance rebuilds with matching
model and initial-state hashes and is not solved at the start; `reset()` is bit-exact; the reference ends with the
task's success at its last step; two replays in fresh processes end in the live state's hash and succeed. The 3
candidates that failed (their PR #4 references are recorded failures) are in the same file.

Harbor runs on the generated tasks (AMD Ryzen 9 7950X, Docker, no GPU): `-a oracle` scores 1 on all 39 privileged
tasks and on 8 standard tasks (heat_food, texas_holdem, take_out_cool_drink, book_rearrange, find_unseen_object,
select_painting, friction_qa, select_fruit_common_sense; live, replay and determinism all hold); `-a nop` scores 0 on
four tasks per mode (select_fruit, heat_food, friction_qa, insert_flower). Two scripted cheat attempts score 0: in
privileged mode, tooling patched to report success, a do-nothing trajectory, a tampered instance and a
`sitecustomize.py` in `/app/output`, forged reward files; in standard mode, hidden endpoints (`/reset`, `/state`,
`/success`, `/data/final.json`: 404), a wrong action type, a `dt` that is not a multiple of 0.1 and NaN rows (400,
nothing runs), and a forged `final.json` in the agent's container (never collected). Re-running `generate.py` gives the
same tree hash.

Final-state hashes of some references (live = replay 1 = replay 2):

| task | seed | control steps | state hash |
|---|---|---|---|
| select_fruit | 0 | 138 | `b9102e6cfd86dc28…` |
| heat_food | 0 | 793 | `0f7a3aea9581b8af…` |
| friction_qa | 0 | 224 | `507033633967865c…` |
| texas_holdem | 0 | 660 | `c77b7967d5b4788f…` |
