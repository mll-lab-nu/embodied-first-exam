# RoboDojo

[RoboDojo](https://github.com/RoboDojo-Benchmark/RoboDojo) @ cb2a37d (MIT): the simulation part of RoboDojo's
sim-and-real benchmark for generalist manipulation policies, on its Isaac Lab 2.3 fork (@ afca7b0) and Isaac Sim 5.1.0,
with its cuRobo fork (@ d17b54c) for IK. Two ARX X5 arms (6 joints each, parallel two-finger grippers) at a table.
`simulator = "robodojo"`, `robot = "arx-x5-bimanual"`. Every task of the simulation benchmark is included: RoboDojo's 42
tasks over five capability dimensions (Generalization 12, Memory 6, Precision 8, Long-Horizon 8, Open 8) and the 12
`_random` variants of the Generalization tasks (other models, lighting, backgrounds, ~15-20 clutter objects): 54 families.

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/robodojo -a codex -m openai/gpt-6-astra
```
Some images are not on a public registry: build them first ([Getting the images](#getting-the-images)).

## Getting the images

All RoboDojo tasks (privileged and standard) need the simulator image, which is not on a public registry
(NVIDIA Isaac Sim 5.1 inside, which NVIDIA does not allow anyone to redistribute); the tooling's files image is public. Build the simulator image
locally under the tags the tasks name; the tasks then run unchanged. Run every command from the repository root on a Linux x86_64 host with Docker (BuildKit), the NVIDIA Container Toolkit and an RTX-class NVIDIA GPU.

1. Licence: building the image accepts the NVIDIA Isaac Sim / Omniverse licence and NVIDIA's terms for the isaacsim wheels
   and cuRobo (the Dockerfile sets `OMNI_KIT_ACCEPT_EULA=YES`). No account, login or token is needed: every input (Docker
   Hub `nvidia/cuda`, github.com, pypi.org, pypi.nvidia.com, download.pytorch.org, the public Hugging Face dataset
   `RoboDojo-Benchmark/RoboDojo` (~41 GB of assets), NVIDIA's extension registry and asset bucket) is anonymous. About
   120 GB of free disk and an hour.
2. Build the simulator image (the files image is public: the task builds pull it):
   ```bash
   docker build -f images/robodojo/Dockerfile -t ghcr.io/mll-lab-nu/efe-private:robodojo-$(cat images/robodojo/VERSION) .
   ```
   (With RoboDojo's `Assets/` already on disk at the pinned revision, add `--build-context robodojo-assets=<dir containing Assets/>`.)
   The build fetches the assets' ~15,000 files anonymously, and Hugging Face may answer `429 Too Many Requests`, which
   fails the build. Download them first with the `hf` CLI, which waits and retries (about 50 min anonymously; faster after
   `hf auth login`), then build from that folder:
   ```bash
   HF_HUB_DISABLE_XET=1 hf download RoboDojo-Benchmark/RoboDojo --repo-type dataset \
     --revision 35efbc7dedfdbeeb6e95fb749bd885d73d483e41 --include 'Assets/*' --local-dir ~/robodojo-assets
   docker build -f images/robodojo/Dockerfile --build-context robodojo-assets=$HOME/robodojo-assets \
     -t ghcr.io/mll-lab-nu/efe-private:robodojo-$(cat images/robodojo/VERSION) .
   ```
3. Run:
   ```bash
   harbor run -d embodied-first-exam@all -p tasks/robodojo -a codex -m openai/gpt-6-astra
   ```

One frozen instance per task, RoboDojo's own evaluation layout `Assets/Eval_Layout/RoboDojo/arx_x5/0/<task>_0.json`,
each a privileged task `robodojo-<task>-i00-privileged` and its standard twin `robodojo-<task>-i00-standard`
(`eai-standard/2.2`), except the six tasks whose physics does not replay bit for bit (Determinism, below): they are
standard only, graded by the live episode. 48 privileged + 54 standard = 102 task directories. `oracle = "none"` for every
task (below).

## Tasks
The task directories are the deliverable; the tooling that built them is kept outside this repository. Each task carries:
- in its instruction, what the task asks and exactly what its check tests (every predicate, threshold, stage and
  end-of-episode requirement), written from RoboDojo's code (`task/RoboDojo/tasks/<benchmark>/<task>.py`, its config,
  `env/reward_manager/`). The code is the reference.
- its instance's `instance.json` (`environment/sim/instance.json`): the evaluation layout verbatim (with its sha256),
  the state hash after RoboDojo's reset, RoboDojo's language instruction for the layout, and per-task fields
  (`physics`, `determinism`) from the determinism test's output (`rcb_robodojo.py make-instance --task T --seed 0
  --layout 0 [--physx key=value]`). The committed standard tasks are the list of instances.

## Success (RoboDojo's own check)
RoboDojo's reward manager for the task, unchanged: its `run_reward()` check list (registered at the start of every episode,
as RoboDojo's evaluator does), evaluated after every action; stages count in order, at most one per action; a failed
query ends the episode as a failure. The episode ends at the first action where every stage has passed. No task of the 54
registers an end-of-episode check: RoboDojo's per-task `step_lim` only ends a policy's episode in its evaluation, so it is
not applied here (no step caps); a technical cap ends an episode after 15,000 actions (10 min of simulated
time; reason `step_guard`, standard mode's `spec.max_control_steps`), the most a trajectory may hold. The instructions
give RoboDojo's limit for reference.

## Oracle
None: RoboDojo releases no expert or planner script, and its training demonstrations (Hugging Face, `data/`) record no
initial state or layout, so none replays on a frozen layout. Every task is `oracle = "none"` and needs human review
(CONTRIBUTING.md; the review is in pull request #142). Model trials gave positive examples (privileged
`general_pickup`, `deposit_coin`, `match_and_pick_from_conveyor`, `stack_blocks_by_language`; standard
`general_pickup`); the screening table below lists the bases solved by the screening runs.

## Tooling (`rcb_robodojo.py`)
`Session(task, instance=...)` builds RoboDojo's own evaluator environment (`src/eval_client/eval_env.py`: one env, the
policy-server client replaced by a stub) and resets it onto the frozen layout exactly as RoboDojo's evaluator starts an
episode. Action: RoboDojo's 14-D joint action `[left joint1..6, left gripper, right joint1..6, right gripper]` at 25 Hz
(physics dt 4 ms, 10 physics steps per action, RoboDojo's controller interpolating to the targets); grippers are RoboDojo's
normalised command (1 = open, 0 = closed). Privileged helpers: hold, joint moves, gripper ramps, RoboDojo's cuRobo IK
(`ik`, `move_ee`); object poses and bounding boxes; the three cameras (`cam_head` static, `cam_left_wrist`,
`cam_right_wrist`, 640×480, optional z-depth); proprioception; numpy FK/IK of both arms from the X5 URDF; recording,
fresh-process `replay` CLI, video. A reset right after a reset changes nothing, so the first episode in a process is
exactly the grader's; after actions RoboDojo's reset settles the scene again from where it is (same layout and start, not
bit-for-bit the same state), which the instructions say.

## Determinism (measured on Isaac Sim 5.1, RoboDojo's GPU PhysX)
RoboDojo forces PhysX GPU dynamics for every task (`overwrite_gpu_setting(1)`, needed for its cloth and liquids); kept.
Test per task (`make-instance`, then two fresh-process replays of a 120-action trajectory moving both arms and grippers):
- 47 tasks: the three resets and the two replays' end states bit-identical (including the conveyor tasks and the
  support-arm tasks);
- `fold_clothes` and `fold_clothes_random` passed that test too, but the test's trajectory moves the arms without handling
  the garment. Once the cloth is handled it does not replay bit for bit (GPU PhysX cloth: a live episode and two
  fresh-process replays from the exact frozen state ended in three different states), so both are in the class below
  (their resets are bit-identical, so `instance_exact` stays meaningful for them);
- `make_toast`: 1 of 3 fresh resets differed; with PhysX enhanced determinism (RoboDojo's own sim setting, off by default)
  all agree, so its instance records `"physics": {"enable_enhanced_determinism": true}` and every session, the service and
  the verifier run with it;
- `make_toast_random` (resets differ even with enhanced determinism) and the three liquid tasks (`pour_liquid_into_cup`,
  its random variant, `pour_by_language`: GPU PhysX particles, not bit-reproducible). Their rebuilt layout hashes
  differently in every process by design, so the tooling reports it (`instance_exact` false) and never refuses the
  instance for it (the standard service starts strict otherwise: a rebuilt layout that hashes differently from the
  recorded one is refused on every other task).

**The six tasks whose physics does not replay bit for bit** (`fold_clothes`, `fold_clothes_random`, `make_toast_random`,
`pour_liquid_into_cup`, `pour_liquid_into_cup_random`, `pour_by_language`; instance.json `"determinism": "verdict"` with
the reason) are **standard only**. An open-loop trajectory of them cannot be graded reproducibly: the same file can
succeed in one fresh replay and fail in the next, so a privileged twin, whose only evidence is replay, would score
chance. In standard mode the trusted service runs the episode and the agent never holds the simulator, so the live
result is the verdict, as for every standard task. A live success may include some luck of the physics. An episode of
the six that resumed after a service crash (resume class `approx`) is graded on its live state after the resume;
`reward.json` reports `resumes` and `resume_state_mismatch` (docs/protocol/standard_mode.md §13.1). Their privileged task names
are not used.
Frozen on one RTX 4090. Across GPU models (L40S, L40, L4) the frozen layouts rebuild to the recorded hashes and a
120-action driver trajectory ends in the same state as on the 4090; every graded trial reports `instance_exact`.

## Grading
- privileged: **one replay**. `tests/grade.py` replays `/app/output/trajectory.npz` once, in a fresh process (`test.sh`:
  `--repeat 1`); reward 1 iff that replay succeeds. `no-network`. A file that is not a trajectory of the task (not an
  npz, pickled or object arrays, another shape, NaN/inf, more than 15,000 rows) is the agent's 0 (`bad_trajectory`,
  `wrong_task`); a replay process that ends without a result or runs out of its time is the verifier's (`grader_error` =
  `infra_error` = 1, `replay_failed` / `replay_timed_out`: no verdict on the agent). Only the file's `task` and `actions`
  entries are read (their sizes checked in the archive before anything is decompressed); any other entry is ignored.
  With one replay there is no second end state: `deterministic` and `state_identical` are written as 1 (nothing
  disagreed) next to `determinism_checked` = 0 and `replays` = 1, which say that nothing was compared.
  `replay_success` = `all_success` = the replay's own result. A replay whose process rebuilt the frozen layout to
  another state than `instance.json` records (`instance_exact` = 0) did not start from the frozen state and gives no
  verdict (`instance_mismatch`, `grader_error` = `infra_error` = 1). `grade.py --repeat 2` is the two-replay check, for a
  determinism measurement by hand. What one replay gives up: a trajectory whose outcome differs between fresh
  processes is not caught; on the 48 privileged tasks the physics replays bit for bit.
- standard: graded by the **live episode**, with no grading replay (PROTOCOL H.4), the same rule for every task:
  `success = live_success`, RoboDojo's check as the service ran it after every action of the episode the agent ran (no
  end-of-episode hold: RoboDojo has none). The service writes `trajectory.npz` (the deliverable) and `episode.json` on
  the collect hook's signal and exits; `finalize.sh` writes `final.json` from it (`graded_by` "live", `replays` 0)
  before anything else. `no-network`. A missing, unreadable or unfinalized `final.json`, no `episode.json`, a give-up
  after crashes between calls and the episode never ending for the hook are `infra_error`; a crash inside the agent's
  calls and a simulator error raised by them stay its 0. The start state: before it serves, the service compares the
  rebuilt layout's state hash with `instance.json`'s `state_sha` (`instance_exact`); a mismatch is a give-up as infra
  (`instance_mismatch`, 409 to every request). The six tasks graded by verdict reset to states that are not
  bit-identical by design: their hash is recorded (`instance_checked` = 0), not compared; what is checked for them is
  only that the layout is `instance.json`'s own (the Session loads it from there).
- The video (standard) comes from the live episode (`live_video.py`, `live.mp4`). Rendering is not free here (a filmed
  replay runs at about 7 actions/s against 10 unfilmed), and RoboDojo's observation renders all three cameras with
  depth at once. So the service never renders for the video: it keeps `cam_head` (640×480, JPEG in
  `/data/live_video/`) at the actions whose observation a call of the agent already rendered (its frames at its
  `video_fps`, 5 per simulated second by default, and the proprioception at each call's end), at most one per 5
  actions; only the end state is rendered once more, at the dump. The video's rate is the agent's (at least one frame
  per call); a resume's journal replay adds none and deletes the frames of the call lost in the crash. The collect hook
  encodes it after the verdict (CPU, at most 600 s); a frame or an encode that fails costs the video only. Privileged:
  the one replay is the filmed one (`replay.mp4`); a video that cannot be written gives `video_ok` false and the replay
  stands.
- Time limits (wall clock only; the verdict rules do not depend on them). A replay process takes up to ~7 min until the
  layout is ready (a cold first start, which every privileged verifier's replay is) and runs at about 5-11 actions/s
  filmed. A replay's allowance is max(1800 s, 1200 s + rows / 2.5), so 7200 s for the 15,000 rows a trajectory may
  have; `[verifier] timeout_sec` (privileged) is **7800 s** (one replay of 15,000 rows + 600 s for the grader and the
  resource step). The standard collect hook is **3600 s** (`finalize.sh`'s `HOOK_BUDGET_S`, equal to
  `[[verifier.collect]] timeout_sec`: the episode end, up to 2700 s through a resume, + the video encode, no replay);
  the standard verifier keeps 1200 s (it only reads files).
- **Re-scoring a standard trial recorded while a grading replay still decided**: its live verdict is `final.json`
  `success` (the live result, merged from `episode.json`); `infra_error` only when the live record is missing (no or
  unfinalized `final.json`, the service never ended the episode) or the service gave up with `infra_error`;
  `replay_error`, `gpu_lost` and an `instance_mismatch` found by a replay are not the live episode's.

## Crash recovery (standard mode, docs/protocol/standard_mode.md §13)
Resume class `exact` (the resumed service is a fresh process whose journal replay is that process's first run), `approx` for
the six standard-only tasks graded by the live episode. `RCB_STARTUP_TIMEOUT_S = 1800`. Acceptance test: RoboDojo
has no oracle, so a driver client (12 joint_position chunks; not a solution) runs as Harbor's oracle on a copy of
`robodojo-general-pickup-i00-standard`, and the service is killed with SIGKILL inside the 6th call, after 5 checkpoints.
Expected: one exact resume (the checkpoint's state hash), the killed call rolled back, the driver's other chunks run,
finalized, no infrastructure error. The driver does not solve the task (success 0 is expected).

## Time budget
3600 s for every task of both modes: each task's own `[agent] timeout_sec` (PROTOCOL §2,
docs/protocol/running.md "The agent's time"). Every Python process pays ~2.5-4 min of Isaac Sim launch, scene build and RoboDojo's
settling (a trial's first start also compiles shaders and materials), and many tasks are long (RoboDojo gives policies
up to 1900 actions), so an hour holds about a dozen simulator starts at most.
Every instruction states the cutoff in the closing `## Time limit` section (written by `task_conventions.normalize`
from `[agent] timeout_sec`, like the README row and the standard service's `RCB_WALL_CLOCK_S`, which only reports the
budget: `spec["budget"]`, `meta["time_left_s"]`; the service never ends an episode on it). RoboDojo's own text adds,
right after the task's introduction and without a number: privileged, `/app/output/trajectory.npz` must be written
before the time limit is up and every `Session` start counts; standard, the task must be completed before it and the
wait for the service counts. Nothing else is derived from the agent's limit: the verifier and collect-hook limits above
come from the 15,000-action cap and the replay speed, `RCB_STARTUP_TIMEOUT_S` from the scene build.

## Standard mode (eai-standard/2.2)
`joint_position` (14: RoboDojo's action, rows `dt` apart, a multiple of 1/25 s) and `ee_pose` (16: both arms' link6 targets
+ gripper commands, solved by the arms' kinematic model and executed as a joint move at most 0.25 m/s); cameras `cam_head`,
`cam_left_wrist`, `cam_right_wrist` (640×480, z-depth); `/kinematics` (FK/IK of both arms from the X5 URDF; matches the
simulator's link6 poses); 58 proprio columns. Request checks: every field of a `/submit` or `/observe` is
read and checked before the first action; a malformed request (a wrong type, a value out of range, an `ee_pose` position
more than 3 m from the world origin on any axis, a zero quaternion) is a 400 and executes nothing. Cameras are taken once
each, and one call captures at most 3000 images (cameras × frames, per-frame depth counted again; `/spec`
`max_frames_per_call`): a `joint_position` chunk or an `/observe` that would exceed it is a 400; an `ee_pose` call, whose
length is only known once its IK is solved, keeps executing and stops filming (`meta["frames_capped"]`).

## Known issues
- **Joint limits in `/spec` and `robot_spec()`** are the articulation's soft limits as Isaac Lab reports them (about
  +-10 rad for several joints). Two trials found the arm's joint4 stopping at about +-1.78 rad. Not verified in the
  simulator here, so neither the instructions nor the limits have been changed.
- **Privileged `s.reset()`** in a long-lived process is not always reliable after an articulated object moved ("articulation
  not found", or "All scene Unstable Error"); a fresh process (as the verifier uses) always builds the frozen start.
- **`pack_objects_into_box(_random)`**: "front sides facing left" is the assets' own axis convention (the checkpoint
  point's -x, the shoe's root +x), which images do not show; every standard run failed it.
- The instructions state, where RoboDojo's own text misleads (its checks unchanged): `sort_nesting_dolls_by_size(_random)`'s
  size order (the config's comments call index mod 5 = 4 the largest doll; the dolls' measured sizes say it is the
  smallest); `swap_blocks`' button rests at about 0.79 of its travel, below the 0.9 / 0.95 its stages and press counter
  need; `hang_mugs(_random)`' orientation conditions use the first functional point of each tag.

## Declarations
- **Tooling: thin wrappers only.** Joint moves, gripper commands, hold, RoboDojo's IK, plus the frozen instance, state,
  recording, replay and rendering. Task-level skills are never added.
- **World-frame information.** Instructions give the world frame (axes, the arm bases, the table, the head camera) and
  state RoboDojo's check as its code has it, including absolute coordinates where the check uses them (e.g. `make_kong`'s
  target spot); standard tasks never give object poses (privileged tasks give them through the tooling).

## Compute resources (scripts/task_resources.toml)
Measured on the heaviest scene (`pour_liquid_into_cup_random`: GPU PhysX liquid and 15-20 clutter objects), RTX 4090,
with the trial's monitor and a per-container sampler (docker stats, cgroup anon memory, nvidia-smi every 10 s):
one Isaac Session (privileged main container, or the standard sim sidecar) peaks at 16.0-16.1 GiB of memory and 9.0-9.5 GiB
of GPU memory and uses every core it is given while Isaac starts; a verifier replay (filmed) 15.7 GiB and 9.6 GiB. The
determinism runs over all 54 tasks used 4.6-8.4 GB of GPU memory per process. Minimum per trial: 8 CPUs, 20 GB, 10.5-11
GB of GPU memory, an RTX-class GPU. Limits (PROTOCOL §6): privileged, the whole trial 16 GiB of GPU memory and 32 GiB of
memory (the cap every past trial ran under; an agent may run a second Session); standard, the agent's container 8 GiB.
Caps: privileged main 8 CPUs / 39 GiB; standard main 8 CPUs / 16 GiB, sim sidecar 16 CPUs / 25 GiB.

## Image and host
`images/robodojo/` → `ghcr.io/mll-lab-nu/efe-private:robodojo-0.1.0` (~74 GB, with RoboDojo's 41 GB of assets). It contains Isaac
Sim: **BUILD_ONLY** (`images/robodojo/BUILD_ONLY` has the licences, the build command and the check of a build). Needs an
RTX-class GPU and ~5-10 GB of GPU memory per Isaac process; Isaac hangs instead of exiting when the GPU runs out of memory,
so a shared GPU runs few at once. Isaac keeps generated Python in its Kit cache: the verifier and the standard sidecar mount
their own `*_trusted` cache volumes, scoped to the trial's compose project.

## Licences
RoboDojo: MIT. Its assets (Hugging Face `RoboDojo-Benchmark/RoboDojo`): Apache-2.0. Isaac Lab fork: BSD-3-Clause. cuRobo
fork: NVIDIA's cuRobo licence. Isaac Sim 5.1 and its wheels: NVIDIA proprietary (no redistribution), hence BUILD_ONLY.

## Standard-mode service details

Serves `eai-standard/2.2`. Resume class `exact` (Isaac Lab, GPU PhysX: the resumed service is a fresh process, whose first run is bit-exact, measured on 48 of its 54 tasks; `make_toast` with PhysX enhanced determinism); `approx` for its six standard-only tasks graded by the live episode (`make_toast_random`, the three liquid tasks and the two cloth tasks: GPU PhysX particles and cloth do not replay bit for bit). For those six the verdict after a resume is the live state the resumed service continued from; `reward.json` reports `resumes` and `resume_state_mismatch`, at most two resumes are allowed as everywhere, and a success with `resumes > 0` is reported with those fields. `max_frames_per_call` = 3000.

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

By directory: 80 easy, 13 hard, 9 unverified, 0 pending.

| base | privileged | standard |
|---|---|---|
| `robodojo-align-blocks-i00` | easy: Astra, Opus, DeepSeek V4.1 Flash, GLM 5.3 Flash | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, GLM 5.3 Flash |
| `robodojo-arrange-largest-number-i00` | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon |
| `robodojo-arrange-largest-number-random-i00` | easy: Astra, Opus, Gemini 3.8 Flash | easy: Astra, Opus, Gemini 4 Argon |
| `robodojo-build-tower-i00` | easy: Astra, Opus, Gemini 4 Argon | easy: Opus, Gemini 4 Argon |
| `robodojo-classify-objects-by-language-i00` | easy: Astra, Opus, Gemini 4 Argon | easy: Astra, Opus, Gemini 4 Argon |
| `robodojo-classify-objects-i00` | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, GLM 5.3 Flash | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon |
| `robodojo-cover-blocks-i00` | easy: Luna | unverified |
| `robodojo-deposit-coin-i00` | easy: Astra, Opus, Gemini 4 Argon | easy: Astra, Opus |
| `robodojo-fasten-screws-i00` | easy: Luna | easy: Luna |
| `robodojo-fill-egg-holder-i00` | easy: Astra | hard |
| `robodojo-fill-pen-holder-i00` | easy: Astra | easy: Astra, Gemini 4 Argon |
| `robodojo-fold-clothes-i00` | — | easy: Astra, Gemini 3.8 Flash, Gemini 4 Argon |
| `robodojo-fold-clothes-random-i00` | — | easy: Astra, Opus, Gemini 4 Argon |
| `robodojo-general-pickup-i00` | easy: Luna | easy: Luna |
| `robodojo-hang-mugs-i00` | easy: Astra, Opus | hard |
| `robodojo-hang-mugs-random-i00` | hard | easy: Gemini 4 Argon |
| `robodojo-imitate-sorting-sequence-i00` | easy: Luna | unverified |
| `robodojo-insert-key-i00` | easy: Astra, Gemini 4 Argon | hard |
| `robodojo-insert-tubes-i00` | easy: Luna | unverified |
| `robodojo-make-kong-i00` | easy: Astra, Opus, Gemini 3.8 Flash | hard (only Astra) |
| `robodojo-make-toast-i00` | easy: Astra | hard |
| `robodojo-make-toast-random-i00` | — | easy: Opus, Gemini 4 Argon |
| `robodojo-match-and-pick-from-conveyor-i00` | easy: Luna | easy: Luna |
| `robodojo-organize-table-i00` | easy: Astra, Gemini 4 Argon | easy: Opus, Gemini 4 Argon |
| `robodojo-pack-objects-into-box-i00` | easy: Astra, Opus, Gemini 4 Argon | hard |
| `robodojo-pack-objects-into-box-random-i00` | easy: Astra, Opus, Gemini 4 Argon | easy: Gemini 4 Argon |
| `robodojo-pick-from-conveyor-by-image-i00` | easy: Astra, Opus | easy: Opus |
| `robodojo-play-stacking-toy-i00` | easy: Astra, Opus, Gemini 4 Argon | easy: Astra, Opus, Gemini 4 Argon |
| `robodojo-play-tic-tac-toe-i00` | easy: Luna | unverified |
| `robodojo-play-xylophone-i00` | unverified | easy: Luna |
| `robodojo-plug-in-charger-i00` | easy: Astra, Opus, GLM 5.3 Flash | easy: Opus, Gemini 4 Argon |
| `robodojo-pour-balls-into-vase-i00` | easy: Astra, Opus, Gemini 4 Argon | easy: Astra, Opus, Gemini 3.8 Flash |
| `robodojo-pour-by-language-i00` | — | easy: Opus |
| `robodojo-pour-liquid-into-cup-i00` | — | easy: Astra, Gemini 3.8 Flash, Gemini 4 Argon |
| `robodojo-pour-liquid-into-cup-random-i00` | — | easy: Astra, Opus, Gemini 3.8 Flash |
| `robodojo-press-by-number-i00` | easy: Luna | unverified |
| `robodojo-push-t-i00` | easy: Astra, Opus, Gemini 3.8 Flash, DeepSeek V4.1 Flash, GLM 5.3 Flash | easy: Astra, Opus |
| `robodojo-push-t-random-i00` | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash |
| `robodojo-put-bottles-into-dustbin-i00` | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon | easy: Opus, Gemini 3.8 Flash, Gemini 4 Argon |
| `robodojo-solve-equation-i00` | easy: Luna | unverified |
| `robodojo-sort-nesting-dolls-by-size-i00` | easy: Astra, Opus, Gemini 4 Argon | easy: Astra, Opus |
| `robodojo-sort-nesting-dolls-by-size-random-i00` | easy: Luna | unverified |
| `robodojo-stack-blocks-by-language-i00` | easy: Luna | easy: Luna |
| `robodojo-stack-blocks-i00` | easy: Luna | easy: Luna |
| `robodojo-stack-blocks-random-i00` | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash, GLM 5.3 Flash | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash, GLM 5.3 Flash |
| `robodojo-stack-bowls-i00` | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon |
| `robodojo-stack-bowls-random-i00` | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon | easy: Astra, Opus |
| `robodojo-store-laptop-and-headphones-i00` | easy: Astra | hard |
| `robodojo-store-laptop-and-headphones-random-i00` | hard | hard |
| `robodojo-store-tools-in-toolbox-i00` | easy: Astra | hard |
| `robodojo-swap-blocks-i00` | easy: Astra | hard |
| `robodojo-swap-t-i00` | easy: Luna | easy: Luna |
| `robodojo-sweep-blocks-i00` | easy: Luna | unverified |
| `robodojo-sweep-blocks-random-i00` | easy: Astra, Opus | hard (only Astra) |

Judgment calls: `robodojo-put-bottles-into-dustbin-i00`: the standard solves by Opus and Gemini 3.8 Flash relayed a
bottle over the table instead of the suggested handover, which the task text says is not enforced.
